"""
Fills the "فرم مشخصات چشمه‌ها/پسماندهای پرتوزا" template with data from a
ReceiveRequest and saves it as a ReceiveAttachment(SPECIFICATION).

REWRITE NOTE: the first version of this generator searched for cells by
label text and appended the answer into whatever cell it found. That was
wrong for several rows — the template actually has a SEPARATE blank
answer cell right next to the label (confirmed by dumping the raw XML:
row 1's facility-name label is a 2-column-wide cell, immediately
followed by an 8-column-wide BLANK cell, which is where the answer
belongs — not squeezed into the label cell itself). This version targets
exact (row, column) grid positions instead, derived directly from the
template's XML (gridSpan values), the same approach your license app's
specification_generator.py uses (_fill_facility / _fill_sources with
table.cell(row, col)).

Also ports, from that same license app generator:
  - Jalali (Solar Hijri) date rendering + Persian-digit numerals,
    since this form is filled out in Persian like the rest of the app.
  - Forcing font name/size on every new run (B Nazanin / 12pt) — cells
    store their Persian/RTL formatting on the paragraph mark, which a
    run added via add_run() does NOT inherit automatically.
  - Relaxing fixed-height rows (hRule="exact" -> "atLeast") before
    writing into them, since EVERY row in this template has an exact
    height sized for the original blank/dotted placeholder text; if the
    real answer is longer, it gets silently clipped instead of growing
    the row.

CELL MAP (0-indexed grid columns, out of 21 total; verified against the
attached blank template's raw XML — re-verify if the template changes):

  row 1:  facility name label cols(0-1), ANSWER cols(2-9), letter label+answer cols(10-20)
  row 2:  address label cols(0-1), ANSWER cols(2-20)
  row 3:  postal code cols(0-5) [label+answer combined],
          national id cols(6-13) [combined], economic code cols(14-20) [combined]
  row 4:  distance, single cell cols(0-20) [combined]
  rows 6-7: column headers — not filled
  rows 8-10: up to 3 data rows. Per row, ONLY these are filled from DB:
          col0 row number (pre-filled "1"/"2"/"3" — don't touch)
          col1-3 nuclide name (ANSWER)
          col4 activity (ANSWER)
          col5-6 quantity (ANSWER)
          col7 half-life (ANSWER)
          Everything else on these rows (shield/burial cols 8-14,
          storage duration cols 15-18, sale probability col19,
          description col20) is left BLANK — the creator fills those
          by hand in Word, then signs. Not modeled in the DB.

  rows 11-19 (the whole logistics section: pre-op visit, personnel,
          vehicle, route difficulty, accommodation/food days,
          peripheral equipment, other costs, notes) are likewise left
          entirely BLANK — managers fill this section by hand before
          their signatures. Not modeled in the DB.

Signature rows (20-22) are untouched here — SpecificationSigner (reused
from operations.services.signature_service) handles those separately.
"""

import os
from io import BytesIO

from django.conf import settings
from django.core.files.base import ContentFile
from docx import Document
from docx.shared import Pt
from docx.oxml.ns import qn

from ..models import ReceiveAttachment, ReceiveAttachmentType


TEMPLATE_PATH = getattr(
    settings,
    "RECEIVE_SPECIFICATION_TEMPLATE_PATH",
    os.path.join(settings.BASE_DIR, "receiving", "templates_docx", "receive_specification_template.docx"),
)

MAIN_TABLE_ROWS = 3  # only 3 data rows exist in the template; the rest go to an appendix


# =====================================================================
# Jalali date / Persian digits (ported from operations' specification_generator.py)
# =====================================================================

_PERSIAN_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def _to_persian_digits(text):
    if text is None:
        return ""
    return str(text).translate(_PERSIAN_DIGITS)


def _gregorian_to_jalali(gy, gm, gd):
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    if gy > 1600:
        jy = 979
        gy -= 1600
    else:
        jy = 0
        gy -= 621
    gy2 = gy + 1 if gm > 2 else gy
    days = (
        365 * gy
        + (gy2 + 3) // 4
        - (gy2 + 99) // 100
        + (gy2 + 399) // 400
        - 80
        + gd
        + g_d_m[gm - 1]
    )
    jy += 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm = 1 + days // 31
        jd = 1 + (days % 31)
    else:
        jm = 7 + (days - 186) // 30
        jd = 1 + ((days - 186) % 30)
    return jy, jm, jd


def _format_jalali_date(date_obj):
    if date_obj is None:
        return ""
    jy, jm, jd = _gregorian_to_jalali(date_obj.year, date_obj.month, date_obj.day)
    return _to_persian_digits(f"{jy:04d}/{jm:02d}/{jd:02d}")


# =====================================================================
# Cell-writing helpers (ported: forced font, row-growth fix)
# =====================================================================

def _allow_row_to_grow(cell):
    """Every row in this template has a fixed (hRule="exact") height sized
    for the original placeholder text. Relax it to "atLeast" so appended
    real data isn't silently clipped."""
    tr = cell._tc.getparent()
    trPr = tr.find(qn("w:trPr"))
    if trPr is None:
        return
    trHeight = trPr.find(qn("w:trHeight"))
    if trHeight is not None and trHeight.get(qn("w:hRule")) == "exact":
        trHeight.set(qn("w:hRule"), "atLeast")


def _append_value(cell, value, sep="  ", bold=False):
    """Appends to the cell's existing text (label + answer share one cell)."""
    if value in (None, ""):
        return
    _allow_row_to_grow(cell)
    paragraph = cell.paragraphs[-1] if cell.paragraphs else cell.add_paragraph()
    run = paragraph.add_run(f"{sep}{value}")
    run.font.name = "B Nazanin"
    run.font.size = Pt(12)
    run.bold = bold


def _set_cell_value(cell, value, bold=False):
    """Overwrites a genuinely BLANK answer cell (no label to preserve)."""
    if value is None:
        value = ""
    _allow_row_to_grow(cell)
    paragraph = cell.paragraphs[0] if cell.paragraphs else cell.add_paragraph()
    for run in list(paragraph.runs):
        run._r.getparent().remove(run._r)
    run = paragraph.add_run(str(value))
    run.font.name = "B Nazanin"
    run.font.size = Pt(12)
    run.bold = bold


# =====================================================================
# Section fillers
# =====================================================================

def _fill_facility(table, receive_request):
    facility = receive_request.facility

    _set_cell_value(table.cell(1, 2), facility.name or "")

    letter_ref = ""
    if receive_request.inquiry_letter_number or receive_request.inquiry_letter_date:
        letter_ref = " / ".join(filter(None, [
            receive_request.inquiry_letter_number,
            _format_jalali_date(receive_request.inquiry_letter_date),
        ]))
    _append_value(table.cell(1, 10), letter_ref)

    address = " - ".join(filter(None, [facility.address1, facility.address2, facility.telephone]))
    _set_cell_value(table.cell(2, 2), address)

    _append_value(table.cell(3, 0), facility.postal_code)
    _append_value(table.cell(3, 6), facility.national_id)
    _append_value(table.cell(3, 14), facility.economic_code)

    if receive_request.distance_to_tehran_km is not None:
        _append_value(table.cell(4, 0), _to_persian_digits(receive_request.distance_to_tehran_km))


def _fill_sources(table, sources):
    """
    Only identity fields (nuclide, activity, quantity, half-life) come
    from the DB — these are needed elsewhere in the system (DSRS
    creation, license-contract checks) so they stay structured data.
    The characterization columns (needs shield/burial, storage
    duration, sale probability, description) are left BLANK here on
    purpose: per current policy the creator fills those by hand in
    Word after downloading this generated doc, then signs — none of
    that is modeled in the DB anymore.

    EXCEPTION: if the source matched an existing license-contract
    inventory record, the description cell gets a short pre-filled
    note ("دارای قرارداد مجوز") so the creator sees it at a glance and
    doesn't need to know/re-type it — they can still add to it by hand.
    """
    for i, source in enumerate(sources[:MAIN_TABLE_ROWS]):
        row = 8 + i  # data rows start at index 8

        _set_cell_value(table.cell(row, 1), str(source.nuclide) if source.nuclide else "")
        _set_cell_value(
            table.cell(row, 4),
            _to_persian_digits(source.average_activity_mci) if source.average_activity_mci is not None else "",
        )
        _set_cell_value(table.cell(row, 5), _to_persian_digits(source.quantity))
        _set_cell_value(table.cell(row, 7), _to_persian_digits(source.half_life_display) if source.half_life_display else "")

        if source.matched_license_dsrs_id:
            contract_number = getattr(getattr(source.matched_license_dsrs, "contract", None), "contract_number", None)
            note = f"دارای قرارداد مجوز ({contract_number})" if contract_number else "دارای قرارداد مجوز"
            _set_cell_value(table.cell(row, 20), note, bold=True)

        # cols 8/9 (shield), 12/13 (burial), 15 (storage duration),
        # 19 (sale probability) intentionally left untouched — blank
        # cells for the creator to fill by hand.


# =====================================================================
# Overflow appendix (>3 sources) — mirrors operations' _build_overflow_document
# =====================================================================

def _build_overflow_document(overflow_sources, receive_request):
    """Same blank-characterization-columns policy as _fill_sources above
    — only identity fields are pre-filled; the rest is left for the
    creator to write in by hand."""
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    doc = Document()

    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = title.add_run(
        _to_persian_digits(f"پیوست - ادامه فهرست چشمه‌ها/پسماندها ({receive_request.facility})")
    )
    run.font.name = "B Nazanin"
    run.font.size = Pt(14)
    run.bold = True

    doc.add_paragraph()

    headers = ["ردیف", "نام چشمه/پسماند", "اکتیویته (mCi)", "تعداد", "نیمه عمر", "نیاز به شیلد", "نیاز به دفن", "مدت نگهداری", "احتمال فروش", "توضیحات"]
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"

    for col, text in enumerate(headers):
        cell = table.rows[0].cells[col]
        _set_cell_value(cell, text, bold=True)
        for p in cell.paragraphs:
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    for i, source in enumerate(overflow_sources):
        row_cells = table.add_row().cells

        description = ""
        if source.matched_license_dsrs_id:
            contract_number = getattr(getattr(source.matched_license_dsrs, "contract", None), "contract_number", None)
            description = f"دارای قرارداد مجوز ({contract_number})" if contract_number else "دارای قرارداد مجوز"

        values = [
            _to_persian_digits(i + MAIN_TABLE_ROWS + 1),
            str(source.nuclide) if source.nuclide else "",
            _to_persian_digits(source.average_activity_mci) if source.average_activity_mci is not None else "",
            _to_persian_digits(source.quantity),
            source.half_life_display or "",
            "",  # needs shield — fill by hand
            "",  # needs burial — fill by hand
            "",  # storage duration — fill by hand
            "",  # sale probability — fill by hand
            description,  # pre-filled only if matched; otherwise fill by hand
        ]
        for col, value in enumerate(values):
            _set_cell_value(row_cells[col], value)

    return doc


# =====================================================================
# Entry point
# =====================================================================

def generate_receive_specification(receive_request, user):

    if not os.path.exists(TEMPLATE_PATH):
        raise FileNotFoundError(
            f"Receive specification template not found at {TEMPLATE_PATH}. "
            f"Set settings.RECEIVE_SPECIFICATION_TEMPLATE_PATH."
        )

    document = Document(TEMPLATE_PATH)
    table = document.tables[1]

    _fill_facility(table, receive_request)

    all_sources = list(
        receive_request.sources
        .select_related("nuclide", "matched_license_dsrs", "matched_license_dsrs__contract")
        .order_by("specification_order")
    )
    main_sources = all_sources[:MAIN_TABLE_ROWS]
    overflow_sources = all_sources[MAIN_TABLE_ROWS:]

    _fill_sources(table, main_sources)
    # Logistics section intentionally left blank — filled by hand.

    # -------------------------------------------------
    # Replace any previous SPECIFICATION attachment rather than leaving
    # orphaned old versions around (same fix as the license app's generator).
    # -------------------------------------------------
    old_specification = ReceiveAttachment.objects.filter(
        receive_request=receive_request,
        attachment_type=ReceiveAttachmentType.SPECIFICATION,
    ).first()
    if old_specification:
        old_specification.file.delete(save=False)
        old_specification.delete()

    buffer = BytesIO()
    document.save(buffer)
    buffer.seek(0)

    attachment = ReceiveAttachment.objects.create(
        receive_request=receive_request,
        attachment_type=ReceiveAttachmentType.SPECIFICATION,
        uploaded_by=user,
    )
    attachment.file.save("receive_specification.docx", ContentFile(buffer.read()), save=True)

    # -------------------------------------------------
    # Overflow appendix
    # -------------------------------------------------
    old_appendix = ReceiveAttachment.objects.filter(
        receive_request=receive_request,
        attachment_type=ReceiveAttachmentType.SPECIFICATION_APPENDIX,
    ).first()
    if old_appendix:
        old_appendix.file.delete(save=False)
        old_appendix.delete()

    if overflow_sources:
        overflow_doc = _build_overflow_document(overflow_sources, receive_request)
        overflow_buffer = BytesIO()
        overflow_doc.save(overflow_buffer)
        overflow_buffer.seek(0)

        overflow_attachment = ReceiveAttachment.objects.create(
            receive_request=receive_request,
            attachment_type=ReceiveAttachmentType.SPECIFICATION_APPENDIX,
            uploaded_by=user,
        )
        overflow_attachment.file.save(
            "receive_specification_appendix.docx", ContentFile(overflow_buffer.read()), save=True,
        )

    return attachment