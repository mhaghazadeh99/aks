import os
import re
from io import BytesIO

from django.conf import settings
from django.core.files.base import ContentFile
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt

from ..models import AnalysisAttachment, LabAttachmentType, RadiationType
from .pdf_tools import docx_bytes_to_pdf_bytes, merge_pdfs, page_count

# ---- Gamma: three templates, one per unit, same row/column layout ----
GAMMA_TEMPLATE_PATH_KG = os.path.join(settings.BASE_DIR, "laboratory", "templates_docx", "Gamma_analysis_Report_form_kg.docx")
GAMMA_TEMPLATE_PATH_L = os.path.join(settings.BASE_DIR, "laboratory", "templates_docx", "Gamma_analysis_Report_form_l.docx")
GAMMA_TEMPLATE_PATH_SAMPLE = os.path.join(settings.BASE_DIR, "laboratory", "templates_docx", "Gamma_analysis_Report_form_sample.docx")

# ---- Alpha/Beta: three templates, one per unit, same row/column layout ----
ALPHA_BETA_TEMPLATE_PATH_KG = os.path.join(settings.BASE_DIR, "laboratory", "templates_docx", "Gross_Alpha___Beta_analysis_Report_form_kg.docx")
ALPHA_BETA_TEMPLATE_PATH_L = os.path.join(settings.BASE_DIR, "laboratory", "templates_docx", "Gross_Alpha___Beta_analysis_Report_form_l.docx")
ALPHA_BETA_TEMPLATE_PATH_SAMPLE = os.path.join(settings.BASE_DIR, "laboratory", "templates_docx", "Gross_Alpha___Beta_analysis_Report_form_sample.docx")

GAMMA_MAX_ROWS = 10
ALPHA_BETA_ROWS_PER_PAGE = 12   # the printed form's row count -- a run with MORE samples than this
                                 # gets split across multiple pages of the same template and merged
                                 # into one PDF, rather than being capped.

UNIT_CHOICES = ("KG", "L", "SAMPLE")


def _allow_row_to_grow(cell):
    tr = cell._tc.getparent()
    trPr = tr.find(qn("w:trPr"))
    if trPr is None:
        return
    trHeight = trPr.find(qn("w:trHeight"))
    if trHeight is not None and trHeight.get(qn("w:hRule")) == "exact":
        trHeight.set(qn("w:hRule"), "atLeast")


# =====================================================================
# Persian (RTL) label + value filling -- unchanged from the version that
# fixed the alpha/beta header misalignment; see earlier notes for why this
# exists (paragraph bidi, LTR-wrapped numbers).
# =====================================================================

_PPR_SUCCESSORS = {
    "adjustRightInd", "snapToGrid", "spacing", "ind", "contextualSpacing", "mirrorIndents",
    "suppressOverlap", "jc", "textDirection", "textAlignment", "textboxTightWrap",
    "outlineLvl", "divId", "cnfStyle", "rPr", "sectPr", "pPrChange",
}


def _make_paragraph_rtl(paragraph):
    """Persian form: the paragraph itself must be right-to-left, otherwise Word lays the
    runs out left-to-right and the value lands on the wrong side of the label."""
    pPr = paragraph._p.get_or_add_pPr()
    if pPr.find(qn("w:bidi")) is None:
        bidi = OxmlElement("w:bidi")
        for child in pPr:
            if child.tag.split("}")[1] in _PPR_SUCCESSORS:
                child.addprevious(bidi)
                break
        else:
            pPr.append(bidi)
    jc = pPr.find(qn("w:jc"))
    if jc is not None:          # in an RTL paragraph the default (start) is already the right edge
        pPr.remove(jc)


_LTR_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9.\-/:±_]*")


def _add_run(paragraph, text, rtl):
    run = paragraph.add_run(text)
    run.font.name = "B Nazanin"
    run.font.size = Pt(12)
    run.font.rtl = rtl
    rPr = run._r.get_or_add_rPr()
    rPr.find(qn("w:rFonts")).set(qn("w:cs"), "B Nazanin")
    szCs = OxmlElement("w:szCs")
    szCs.set(qn("w:val"), "24")
    rPr.find(qn("w:sz")).addnext(szCs)


def _fill_after_colon(cell, value):
    """Append `value` after the label, keeping the template's own label runs (bold, rtl, fonts) untouched.
    Latin/number chunks (dates, IDs, 12.5 ± 1) go in LTR runs so they are not mirrored;
    Persian chunks go in RTL runs."""
    if value in (None, ""):
        return
    _allow_row_to_grow(cell)
    paragraph = cell.paragraphs[0]
    _make_paragraph_rtl(paragraph)

    text = str(value)
    if not paragraph.text.endswith((" ", "\u00a0")):
        text = " " + text

    pos = 0
    for m in _LTR_TOKEN.finditer(text):
        if m.start() > pos:
            _add_run(paragraph, text[pos:m.start()], rtl=True)
        # LRM before/after: stops the bidi algorithm from treating digits after Persian letters as
        # Arabic numbers (which mirrors 2026-08-23 into 23-08-2026)
        _add_run(paragraph, "\u200e" + m.group() + "\u200e", rtl=False)
        pos = m.end()
    if pos < len(text):
        _add_run(paragraph, text[pos:], rtl=True)


def _append_value(cell, value, sep=" "):
    """Plain append for cells whose label is Latin."""
    if value in (None, ""):
        return
    _allow_row_to_grow(cell)
    paragraph = cell.paragraphs[-1] if cell.paragraphs else cell.add_paragraph()
    run = paragraph.add_run(f"{sep}{value}")
    run.font.name = "B Nazanin"
    run.font.size = Pt(12)


def _set_cell_value(cell, value):
    if value is None:
        value = ""
    _allow_row_to_grow(cell)
    paragraph = cell.paragraphs[0] if cell.paragraphs else cell.add_paragraph()
    for run in list(paragraph.runs):
        run._r.getparent().remove(run._r)
    run = paragraph.add_run(str(value))
    run.font.name = "B Nazanin"
    run.font.size = Pt(12)


def _fmt_dt(value):
    return value.strftime("%Y-%m-%d") if value else ""


def _replace_attachment(target_kwargs, attachment_type, filename, buffer, user):
    """buffer: raw bytes (PDF) or a BytesIO -- both accepted."""
    if hasattr(buffer, "read"):
        buffer.seek(0)
        content = buffer.read()
    else:
        content = buffer

    old = AnalysisAttachment.objects.filter(attachment_type=attachment_type, **target_kwargs).first()
    if old:
        old.file.delete(save=False)
        old.delete()

    attachment = AnalysisAttachment.objects.create(
        attachment_type=attachment_type, uploaded_by=user, **target_kwargs,
    )
    attachment.file.save(filename, ContentFile(content), save=True)
    return attachment


def _check_unit(unit):
    unit = (unit or "KG").upper()
    if unit not in UNIT_CHOICES:
        raise ValueError(f"unit must be one of {UNIT_CHOICES}, got {unit!r}")
    return unit


# =====================================================================
# GAMMA -- one report per Analysis. Output is now PDF (converted from
# whichever of the three templates matches the chosen unit), not an
# editable .docx.
#
# unit="KG"/"L": specific activity, MDA and uncertainty are divided by the
#   sample's recorded mass or volume (same figures as before this unit
#   choice existed). A sample missing that basis prints blank for that row
#   rather than silently falling back to a different unit within the same
#   report.
# unit="SAMPLE": no division at all -- the raw measured/decay-corrected
#   activity, MDA and uncertainty in Bq, exactly as counted on that sample.
# =====================================================================

def generate_gamma_report(analysis, user, unit="KG"):

    unit = _check_unit(unit)
    sample = analysis.sample

    template_path = {
        "KG": GAMMA_TEMPLATE_PATH_KG,
        "L": GAMMA_TEMPLATE_PATH_L,
        "SAMPLE": GAMMA_TEMPLATE_PATH_SAMPLE,
    }[unit]

    if unit == "KG":
        denom = float(sample.sample_mass_kg) if sample.sample_mass_kg else None
    elif unit == "L":
        denom = float(sample.sample_volume_ml) / 1000.0 if sample.sample_volume_ml else None
    else:
        denom = 1.0   # SAMPLE: raw Bq, no division

    doc = Document(template_path)

    assert len(doc.tables) == 3, (
        f"Expected 3 tables in the Gamma template, found {len(doc.tables)}."
    )
    assert len(doc.tables[1].rows) == 12, (
        f"Expected 12 rows in the Gamma data table, found {len(doc.tables[1].rows)}."
    )
    assert len(doc.tables[2].rows) == 4, (
        f"Expected 4 rows in the Gamma signature table, found {len(doc.tables[2].rows)}."
    )

    table = doc.tables[1]

    _fill_after_colon(table.cell(1, 0), sample.applicant_name)
    code_bits = " / ".join(filter(None, [sample.sample_type, sample.sample_code_barcode or sample.sample_id]))
    _fill_after_colon(table.cell(1, 3), code_bits)

    location_bits = " - ".join(filter(None, [_fmt_dt(sample.sampling_date), sample.sampling_location]))
    _fill_after_colon(table.cell(2, 0), location_bits)
    _fill_after_colon(table.cell(2, 3), _fmt_dt(analysis.analysis_date))

    _fill_after_colon(table.cell(3, 3), analysis.counting_duration_seconds)

    activities = list(
        analysis.nuclide_activities.filter(radiation_type=RadiationType.GAMMA).select_related("radionuclide")
    )
    if len(activities) > GAMMA_MAX_ROWS:
        activities = activities[:GAMMA_MAX_ROWS]   # only 5 fit the printed table

    FIRST_DATA_ROW = 6
    for i, na in enumerate(activities):
        row = FIRST_DATA_ROW + i

        if unit == "L":
            total_specific = na.specific_activity_bq_per_l(decay_corrected=True)
            as_measured_specific = na.specific_activity_bq_per_l(decay_corrected=False)
        elif unit == "KG":
            total_specific = na.specific_activity_bq_per_kg(decay_corrected=True)
            as_measured_specific = na.specific_activity_bq_per_kg(decay_corrected=False)
        else:
            total_specific = na.current_activity_bq()
            as_measured_specific = float(na.activity_bq) if na.activity_bq is not None else None

        mdc_specific = (float(na.mda_bq) / denom) if (na.mda_bq and denom) else None
        unc_specific = (float(na.uncertainty_bq) / denom) if (na.uncertainty_bq and denom) else None

        _set_cell_value(table.cell(row, 0), f"{total_specific:.3f}" if total_specific is not None else "")
        _set_cell_value(table.cell(row, 1), f"{mdc_specific:.3f}" if mdc_specific is not None else "")
        _set_cell_value(table.cell(row, 2), f"{unc_specific:.3f}" if unc_specific is not None else "")
        _set_cell_value(table.cell(row, 3), f"{as_measured_specific:.3f}" if as_measured_specific is not None else "")
        _set_cell_value(table.cell(row, 4), str(na.radionuclide))
        _set_cell_value(table.cell(row, 5), str(i + 1))

    docx_buffer = BytesIO()
    doc.save(docx_buffer)
    pdf_bytes = docx_bytes_to_pdf_bytes(docx_buffer.getvalue())

    attachment = _replace_attachment(
        {"analysis": analysis}, LabAttachmentType.REPORT, "gamma_report.pdf", pdf_bytes, user,
    )
    # Recorded BEFORE any signature page exists, so signing later knows exactly
    # where the real content ends and a (re)appended signature page begins.
    attachment.content_page_count = page_count(pdf_bytes)
    attachment.save(update_fields=["content_page_count"])
    return attachment


# =====================================================================
# ALPHA/BETA -- one report per CountingRun, any number of samples.
#
# The "first table" (applicant, sampling time/location, run id, counting
# duration) comes from the counting run's own fields -- set once, not
# re-derived per sample (see LAB_REPORT_UNITS.md from the previous round).
#
# More than ALPHA_BETA_ROWS_PER_PAGE (12) samples: the run is split into
# chunks of 12, each rendered as its own copy of the page (full header
# repeated on every page, so each page is independently readable), every
# chunk converted to PDF, then all chunks merged into ONE final PDF in
# sample order. This is what "added as attachments to the report form"
# becomes once the output is PDF rather than a fixed-size printed form --
# there's no 12-sample ceiling on the run any more, only on how many rows
# fit one page of output.
# =====================================================================

def _alpha_beta_template_path(unit):
    return {
        "KG": ALPHA_BETA_TEMPLATE_PATH_KG,
        "L": ALPHA_BETA_TEMPLATE_PATH_L,
        "SAMPLE": ALPHA_BETA_TEMPLATE_PATH_SAMPLE,
    }[unit]


def _alpha_beta_denom(sample, unit):
    if unit == "KG":
        return float(sample.sample_mass_kg) if sample.sample_mass_kg else None
    if unit == "L":
        return float(sample.sample_volume_ml) / 1000.0 if sample.sample_volume_ml else None
    return 1.0   # SAMPLE


def _render_alpha_beta_page(counting_run, analyses_chunk, unit, applicant_text, sampling_text):
    """Renders ONE page's worth (<= ALPHA_BETA_ROWS_PER_PAGE samples) of the
    Alpha/Beta report as a .docx, returns its raw bytes. The header/MDA rows
    are filled on every page so each one stands alone if printed separately."""

    doc = Document(_alpha_beta_template_path(unit))

    assert len(doc.tables) == 2, (
        f"Expected 2 tables in the Alpha/Beta template, found {len(doc.tables)}."
    )
    assert len(doc.tables[1].rows) == 23, (
        f"Expected 23 rows in the Alpha/Beta data table, found {len(doc.tables[1].rows)}."
    )

    table = doc.tables[1]

    _fill_after_colon(table.cell(1, 0), counting_run.run_id)
    _fill_after_colon(table.cell(1, 4), applicant_text)
    _fill_after_colon(table.cell(2, 0), _fmt_dt(counting_run.run_date))
    _fill_after_colon(table.cell(2, 4), sampling_text)
    _fill_after_colon(table.cell(3, 0), counting_run.counting_duration_seconds)

    FIRST_DATA_ROW = 6
    for i, analysis in enumerate(analyses_chunk):
        row = FIRST_DATA_ROW + i
        sample = analysis.sample
        denom = _alpha_beta_denom(sample, unit)

        _set_cell_value(table.cell(row, 0), str(i + 1))
        _set_cell_value(table.cell(row, 1), sample.sample_code_barcode or sample.sample_id)
        _set_cell_value(table.cell(row, 3), str(sample.sample_volume_ml) if sample.sample_volume_ml is not None else "")

        alpha_text = ""
        if analysis.total_alpha is not None:
            if denom:
                value = float(analysis.total_alpha) / denom
                unc = (float(analysis.alpha_uncertainty) / denom) if analysis.alpha_uncertainty else 0
                alpha_text = f"{value:.3f} ± {unc:.3f}"
            # denom is None only for KG/L when this sample has no recorded mass/volume --
            # left blank rather than silently printing a different unit on this row.
        _set_cell_value(table.cell(row, 4), alpha_text)

        beta_text = ""
        if analysis.total_beta is not None:
            if denom:
                value = float(analysis.total_beta) / denom
                unc = (float(analysis.beta_uncertainty) / denom) if analysis.beta_uncertainty else 0
                beta_text = f"{value:.3f} ± {unc:.3f}"
        _set_cell_value(table.cell(row, 6), beta_text)

    if unit == "SAMPLE":
        _append_value(table.cell(18, 0), counting_run.alpha_mda_mbq)
        _append_value(table.cell(18, 4), counting_run.beta_mda_mbq)
    else:
        # alpha/beta_mda_mbq are counter-level mBq figures (see the model's own
        # comment) -- not sample-normalized, so they're only meaningful as-is
        # on the SAMPLE-unit report. Printed blank on KG/L pages rather than a
        # number whose unit wouldn't match the rest of that page.
        pass

    buffer = BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def generate_alpha_beta_report(counting_run, user, unit="KG"):

    unit = _check_unit(unit)

    analyses = list(
        counting_run.analyses.select_related("sample").order_by("id")
    )
    if not analyses:
        raise ValueError("This counting run has no analyses attached — nothing to report.")

    if counting_run.applicant_name:
        applicant_text = counting_run.applicant_name
    else:
        applicant_names = sorted({a.sample.applicant_name for a in analyses if a.sample.applicant_name})
        applicant_text = "، ".join(applicant_names)

    if counting_run.sampling_location or counting_run.sampling_date_from:
        parts = []
        if counting_run.sampling_date_from:
            if counting_run.sampling_date_to and counting_run.sampling_date_to != counting_run.sampling_date_from:
                parts.append(f"{_fmt_dt(counting_run.sampling_date_from)} تا {_fmt_dt(counting_run.sampling_date_to)}")
            else:
                parts.append(_fmt_dt(counting_run.sampling_date_from))
        if counting_run.sampling_location:
            parts.append(counting_run.sampling_location)
        sampling_text = " - ".join(parts)
    else:
        dates = sorted({a.sample.sampling_date.date() for a in analyses if a.sample.sampling_date})
        places = sorted({a.sample.sampling_location for a in analyses if a.sample.sampling_location})
        parts = []
        if dates:
            parts.append(_fmt_dt(dates[0]) if len(dates) == 1 else f"{_fmt_dt(dates[0])} تا {_fmt_dt(dates[-1])}")
        if places:
            parts.append("، ".join(places))
        sampling_text = " - ".join(parts)

    chunks = [analyses[i:i + ALPHA_BETA_ROWS_PER_PAGE] for i in range(0, len(analyses), ALPHA_BETA_ROWS_PER_PAGE)]

    pdf_chunks = []
    for chunk in chunks:
        docx_bytes = _render_alpha_beta_page(counting_run, chunk, unit, applicant_text, sampling_text)
        pdf_chunks.append(docx_bytes_to_pdf_bytes(docx_bytes))

    final_pdf = pdf_chunks[0] if len(pdf_chunks) == 1 else merge_pdfs(pdf_chunks)

    attachment = _replace_attachment(
        {"counting_run": counting_run}, LabAttachmentType.REPORT, "alpha_beta_report.pdf", final_pdf, user,
    )
    attachment.content_page_count = page_count(final_pdf)
    attachment.save(update_fields=["content_page_count"])
    return attachment
