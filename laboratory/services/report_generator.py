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

GAMMA_TEMPLATE_PATH = os.path.join(settings.BASE_DIR, "laboratory", "templates_docx", "Gamma_analysis_Report_form.docx")
ALPHA_BETA_TEMPLATE_PATH = os.path.join(settings.BASE_DIR, "laboratory", "templates_docx", "Gross_Alpha___Beta_analysis_Report_form.docx")

GAMMA_MAX_ROWS = 5
ALPHA_BETA_MAX_SAMPLES = 12


def _allow_row_to_grow(cell):
    tr = cell._tc.getparent()
    trPr = tr.find(qn("w:trPr"))
    if trPr is None:
        return
    trHeight = trPr.find(qn("w:trHeight"))
    if trHeight is not None and trHeight.get(qn("w:hRule")) == "exact":
        trHeight.set(qn("w:hRule"), "atLeast")


# =====================================================================
# Persian (RTL) label + value filling
#
# WHY the old version put values "behind" the titles: the template's
# paragraphs are NOT right-to-left paragraphs (only their label runs are
# flagged rtl, and the paragraph is just right-aligned). A run appended
# after the label therefore lands on the RIGHT of it. Fix = make the
# paragraph itself RTL (<w:bidi/>), keep the template's own label runs,
# and add the value as new runs:
#   - Latin/number chunks (dates, IDs, 12.5 ± 1) -> LTR runs wrapped in
#     U+200E so digits after Persian letters aren't mirrored
#     (2026-08-23 would otherwise show as 23-08-2026);
#   - Persian chunks -> RTL runs.
# All value runs carry the complex-script font/size (B Nazanin, szCs) —
# that is what Word actually uses for Persian text.
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
    """Plain append for cells whose label is Latin (e.g. 'MDA α (mBq):')."""
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


def _replace_attachment(target_kwargs, attachment_type, filename, buffer, user):
    old = AnalysisAttachment.objects.filter(attachment_type=attachment_type, **target_kwargs).first()
    if old:
        old.file.delete(save=False)
        old.delete()

    attachment = AnalysisAttachment.objects.create(
        attachment_type=attachment_type, uploaded_by=user, **target_kwargs,
    )
    attachment.file.save(filename, ContentFile(buffer.read()), save=True)
    return attachment


def _fmt_dt(value):
    return value.strftime("%Y-%m-%d") if value else ""


# =====================================================================
# GAMMA — one report per Analysis
# =====================================================================

def generate_gamma_report(analysis, user):

    doc = Document(GAMMA_TEMPLATE_PATH)

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
    sample = analysis.sample

    # Same RTL problem as the alpha/beta form -> same filler.
    # (If a cell in YOUR gamma template has a Latin label, switch that one back to _append_value.)
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
        # Only the first 5 fit the printed table.
        activities = activities[:GAMMA_MAX_ROWS]

    FIRST_DATA_ROW = 6
    for i, na in enumerate(activities):
        row = FIRST_DATA_ROW + i

        total_specific = na.specific_activity_bq_per_kg(decay_corrected=True)
        as_measured_specific = na.specific_activity_bq_per_kg(decay_corrected=False)
        mdc_specific = (float(na.mda_bq) / float(sample.sample_mass_kg)) if (na.mda_bq and sample.sample_mass_kg) else None
        unc_specific = (float(na.uncertainty_bq) / float(sample.sample_mass_kg)) if (na.uncertainty_bq and sample.sample_mass_kg) else None

        _set_cell_value(table.cell(row, 0), f"{total_specific:.3f}" if total_specific is not None else "")
        _set_cell_value(table.cell(row, 1), f"{mdc_specific:.3f}" if mdc_specific is not None else "")
        _set_cell_value(table.cell(row, 2), f"{unc_specific:.3f}" if unc_specific is not None else "")
        _set_cell_value(table.cell(row, 3), f"{as_measured_specific:.3f}" if as_measured_specific is not None else "")
        _set_cell_value(table.cell(row, 4), str(na.radionuclide))
        _set_cell_value(table.cell(row, 5), str(i + 1))

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    return _replace_attachment(
        {"analysis": analysis}, LabAttachmentType.REPORT, "gamma_report.docx", buffer, user,
    )


# =====================================================================
# ALPHA/BETA — one report per CountingRun (up to 12 samples)
# =====================================================================

def generate_alpha_beta_report(counting_run, user):

    analyses = list(
        counting_run.analyses.select_related("sample").order_by("id")
    )

    if not analyses:
        raise ValueError("This counting run has no analyses attached — nothing to report.")

    if len(analyses) > ALPHA_BETA_MAX_SAMPLES:
        raise ValueError(
            f"This counting run has {len(analyses)} samples, but the printed form only "
            f"has {ALPHA_BETA_MAX_SAMPLES} rows. Split it into more than one run."
        )

    doc = Document(ALPHA_BETA_TEMPLATE_PATH)

    assert len(doc.tables) == 2, (
        f"Expected 2 tables in the Alpha/Beta template, found {len(doc.tables)}."
    )
    assert len(doc.tables[1].rows) == 23, (
        f"Expected 23 rows in the Alpha/Beta data table, found {len(doc.tables[1].rows)}."
    )

    table = doc.tables[1]

    applicant_names = sorted({a.sample.applicant_name for a in analyses if a.sample.applicant_name})
    applicant_text = "، ".join(applicant_names)

    # "نوع و کد نمونه": a run has many samples -> the run ID identifies the batch
    _fill_after_colon(table.cell(1, 0), counting_run.run_id)
    _fill_after_colon(table.cell(1, 4), applicant_text)

    _fill_after_colon(table.cell(2, 0), _fmt_dt(counting_run.run_date))

    # "زمان و محل نمونه‌برداری": one cell for up to 12 samples -> show the date range
    # and the distinct locations.
    dates = sorted({a.sample.sampling_date.date() for a in analyses if a.sample.sampling_date})
    places = sorted({a.sample.sampling_location for a in analyses if a.sample.sampling_location})
    parts = []
    if dates:
        parts.append(_fmt_dt(dates[0]) if len(dates) == 1 else f"{_fmt_dt(dates[0])} تا {_fmt_dt(dates[-1])}")
    if places:
        parts.append("، ".join(places))
    _fill_after_colon(table.cell(2, 4), " - ".join(parts))

    _fill_after_colon(table.cell(3, 0), counting_run.counting_duration_seconds)

    FIRST_DATA_ROW = 6
    for i, analysis in enumerate(analyses):
        row = FIRST_DATA_ROW + i
        sample = analysis.sample

        _set_cell_value(table.cell(row, 0), str(i + 1))
        _set_cell_value(table.cell(row, 1), sample.sample_code_barcode or sample.sample_id)
        _set_cell_value(table.cell(row, 3), str(sample.sample_volume_ml) if sample.sample_volume_ml is not None else "")

        alpha_text = ""
        if analysis.total_alpha is not None:
            alpha_text = f"{analysis.total_alpha} ± {analysis.alpha_uncertainty or 0}"
        _set_cell_value(table.cell(row, 4), alpha_text)

        beta_text = ""
        if analysis.total_beta is not None:
            beta_text = f"{analysis.total_beta} ± {analysis.beta_uncertainty or 0}"
        _set_cell_value(table.cell(row, 6), beta_text)

    _append_value(table.cell(18, 0), counting_run.alpha_mda_mbq)
    _append_value(table.cell(18, 4), counting_run.beta_mda_mbq)

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    return _replace_attachment(
        {"counting_run": counting_run}, LabAttachmentType.REPORT, "alpha_beta_report.docx", buffer, user,
    )