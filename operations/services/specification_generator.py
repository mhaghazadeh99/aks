from io import BytesIO
from pathlib import Path
import copy
from docx.shared import Pt
from django.conf import settings
from django.core.files.base import ContentFile
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx import Document
from docx.oxml.ns import qn

from operations.models import (
    LicenseAttachment,
    LicenseAttachmentType,
)


def generate_specification(license_request, generated_by):

    template_path = (
        Path(settings.BASE_DIR) / "templates" / "documents" / "dsrs_specification.docx"
    )

    doc = Document(template_path)

    assert len(doc.tables) == 2, (
        f"Expected 2 tables in {template_path}, found {len(doc.tables)}. "
        "The fill logic below is hard-coded to this template's structure."
    )
    assert len(doc.tables[1].rows) == 17, (
        f"Expected 17 rows in the main form table, found "
        f"{len(doc.tables[1].rows)}. Template structure may have changed."
    )

    all_sources = list(
        license_request.sources.select_related("nuclide").order_by("specification_order")
    )

    main_sources = all_sources[:MAIN_TABLE_ROWS]
    overflow_sources = all_sources[MAIN_TABLE_ROWS:]

    _fill_facility(doc, license_request)
    _fill_sources(doc, main_sources)

    overflow_note = None
    if overflow_sources:
        overflow_note = _to_persian_digits(
            f"ادامه فهرست ({len(overflow_sources)} چشمه دیگر) در پیوست شماره ۱"
        )

    _fill_description(doc, license_request.description, overflow_note=overflow_note)

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    # -------------------------------------------------
    # Delete the OLD file from storage before writing the new
    # one — otherwise Django's storage backend just renames the
    # new file to avoid a collision, leaving every prior version
    # orphaned on disk instead of actually being replaced.
    # -------------------------------------------------
    old_specification = LicenseAttachment.objects.filter(
        license=license_request,
        attachment_type=LicenseAttachmentType.SPECIFICATION,
    ).first()

    if old_specification:
        old_specification.file.delete(save=False)
        old_specification.delete()

    attachment = LicenseAttachment.objects.create(
        license=license_request,
        attachment_type=LicenseAttachmentType.SPECIFICATION,
        uploaded_by=generated_by,
    )

    attachment.file.save(
        "dsrs_specification.docx",
        ContentFile(buffer.read()),
        save=True,
    )

    # -------------------------------------------------
    # Overflow appendix — same fix
    # -------------------------------------------------
    old_appendix = LicenseAttachment.objects.filter(
        license=license_request,
        attachment_type=LicenseAttachmentType.SPECIFICATION_APPENDIX,
    ).first()

    if old_appendix:
        old_appendix.file.delete(save=False)
        old_appendix.delete()

    if overflow_sources:

        overflow_doc = _build_overflow_document(overflow_sources, license_request)

        overflow_buffer = BytesIO()
        overflow_doc.save(overflow_buffer)
        overflow_buffer.seek(0)

        overflow_attachment = LicenseAttachment.objects.create(
            license=license_request,
            attachment_type=LicenseAttachmentType.SPECIFICATION_APPENDIX,
            uploaded_by=generated_by,
        )

        overflow_attachment.file.save(
            "dsrs_specification_appendix.docx",
            ContentFile(overflow_buffer.read()),
            save=True,
        )

    return attachment


# --------------------------------------------------
# Low-level helpers
#
# The template's labels ("نام مرکز :", etc.) and the blank
# space where the answer goes live in the SAME cell/paragraph
# — there's no separate empty cell to write into. So filling
# the form means either:
#   (a) appending a run of text after the existing label text
#       in that paragraph (facility / header fields), or
#   (b) writing into an already-blank cell as-is (the 8 source
#       rows in the table body).
#
# Every cell in this template stores its Persian/RTL formatting
# on the paragraph mark (w:pPr/w:rPr) — font "B Nazanin", RTL,
# size 24 — rather than on a visible run (since there's often no
# run yet). A run added via python-docx's add_run() doesn't
# inherit that automatically, so both helpers below clone that
# paragraph-mark rPr onto the new run to keep the font/direction
# consistent with the rest of the form.
# --------------------------------------------------

_PERSIAN_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def _to_persian_digits(text):
    return text.translate(_PERSIAN_DIGITS)


def _gregorian_to_jalali(gy, gm, gd):
    """Convert a Gregorian (y, m, d) to Jalali (Solar Hijri / Shamsi). Pure
    Python, no dependency — same standard algorithm used by most Jalali
    calendar libraries (e.g. jalaali-js), verified against known reference
    dates (Nowruz 2000-03-20 -> 1379/01/01, etc.)."""

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
    """Render a Gregorian `date` as a Jalali date string in Persian digits
    (e.g. ۱۴۰۳/۰۲/۱۲), since the form is filled out in Persian."""

    if date_obj is None:
        return ""
    jy, jm, jd = _gregorian_to_jalali(date_obj.year, date_obj.month, date_obj.day)
    return _to_persian_digits(f"{jy:04d}/{jm:02d}/{jd:02d}")


def _allow_row_to_grow(cell):
    """Several rows in this template use a fixed w:trHeight (hRule="exact")
    sized for exactly the one line of label text the template ships with.
    Appending a second line of real data doesn't grow the row — it just
    gets silently clipped by Word/LibreOffice. Relaxing hRule to "atLeast"
    keeps that as a minimum height but lets the row grow if we write more
    text into it than the template anticipated."""

    tr = cell._tc.getparent()
    trPr = tr.find(qn("w:trPr"))
    if trPr is None:
        return
    trHeight = trPr.find(qn("w:trHeight"))
    if trHeight is not None and trHeight.get(qn("w:hRule")) == "exact":
        trHeight.set(qn("w:hRule"), "atLeast")


def _append_value(cell, value, sep=" "):
    if value is None:
        value = ""

    value = str(value)

    _allow_row_to_grow(cell)

    paragraph = cell.paragraphs[-1] if cell.paragraphs else cell.add_paragraph()

    run = paragraph.add_run(
        f"{sep}{value}"
    )

    # force visible text
    run.font.name = "B Nazanin"
    run.font.size = Pt(12)
    

    run.font.hidden = False

    

def _set_cell_value(cell, value):

    if value is None:
        value = ""

    paragraph = cell.paragraphs[0]

    for run in list(paragraph.runs):
        run._r.getparent().remove(run._r)

    run = paragraph.add_run(str(value))

    run.font.name = "B Nazanin"
    run.font.size = Pt(12)
    run.font.hidden = False
# --------------------------------------------------
# Section fillers
#
# doc.tables[0] is the small header block (date / number / form
# code) at the very top — nothing to fill there.
# doc.tables[1] is the actual form. Grid layout (0-indexed, 9
# grid columns wide due to merged cells):
#
#   row 0        : section title "مشخصات مرکز متقاضی مجوز" (spans all)
#   row 1        : col0 "نام مرکز :"            (span 0-4)
#                  col5 "شماره و تاریخ نامه:"    (span 5-8)
#   row 2        : col0 "آدرس و شماره تلفن:"    (spans all)
#   row 3        : col0 "کد پستی:"       (span 0-2)
#                  col3 "شناسه ملی:"     (span 3-6)
#                  col7 "کد اقتصادی:"    (span 7-8)
#   row 4        : section title "مشخصات چشمه‌های پرتوزا" (spans all)
#   rows 5-6     : column headers (ردیف / نام چشمه / اکتیویته / ...)
#   rows 7-14    : 8 blank source rows, pre-numbered 1-8 in col0
#                  col1 name, col2 activity (mCi), col4 serial no.,
#                  col6 half-life, col8 description
#   row 15       : col0 "توضیحات" note field (span 0-7),
#                  col8 signature/staff field — left blank, filled by hand
#   row 16       : fixed footer instructions — leave untouched
# --------------------------------------------------

def _fill_facility(doc, license_request):
    table = doc.tables[1]
    facility = license_request.facility

    # "شماره و تاریخ نامه" (letter number & date) lives on LicenseRequest,
    # not Facility. Date is rendered in Jalali since the form is Persian.
    letter_ref = ""
    if license_request.letter_number or license_request.letter_date:
        letter_ref = " - ".join(
            filter(
                None,
                [
                    license_request.letter_number,
                    _format_jalali_date(license_request.letter_date),
                ],
            )
        )

    address = " - ".join(filter(None, [facility.address1, facility.address2]))

    _append_value(table.cell(1, 0), facility.name)
    _append_value(table.cell(1, 5), letter_ref)
    _append_value(table.cell(2, 0), f"{address} - {facility.telephone}".strip(" -"))
    _append_value(table.cell(3, 0), facility.postal_code)
    _append_value(table.cell(3, 3), facility.national_id)
    _append_value(table.cell(3, 7), facility.economic_code)


def _format_half_life(seconds):
    """Nuclides.half_life is stored in seconds — render it in whatever unit
    reads most naturally (matches how half-lives are normally quoted)."""

    if seconds is None:
        return ""

    seconds = float(seconds)
    MINUTE, HOUR, DAY, YEAR = 60, 3600, 86400, 365.25 * 86400

    if seconds < MINUTE:
        return f"{seconds:.2f} s"
    if seconds < HOUR:
        return f"{seconds / MINUTE:.2f} min"
    if seconds < DAY:
        return f"{seconds / HOUR:.2f} h"
    if seconds < YEAR:
        return f"{seconds / DAY:.2f} d"
    return f"{seconds / YEAR:.2f} y"


MAIN_TABLE_ROWS = 7   # real source data; the 8th slot is reserved for an
                       # overflow note when there are more than 7 sources
def _fill_sources(doc, sources):
    table = doc.tables[1]
    FIRST_DATA_ROW = 7

    for i, source in enumerate(sources[:MAIN_TABLE_ROWS]):
        row = FIRST_DATA_ROW + i

        if source.nuclide is None:
            _set_cell_value(table.cell(row, 1), "—")
        else:
            _set_cell_value(table.cell(row, 1), source.nuclide.name)

        activity = ""
        if source.activity is not None:
            activity = f"{source.activity} {source.get_activity_unit_display()}"

        type_label = source.get_source_type_display()
        description = source.description or ""
        combined_description = f"{type_label} - {description}" if description else type_label

        _set_cell_value(table.cell(row, 1), source.nuclide.name)
        _set_cell_value(table.cell(row, 2), activity)
        _set_cell_value(table.cell(row, 4), source.serial_number)
        _set_cell_value(table.cell(row, 6), _format_half_life(source.nuclide.half_life))
        _set_cell_value(table.cell(row, 8), combined_description)




def _fill_description(doc, description, overflow_note=None):
    table = doc.tables[1]

    combined = description or ""

    if overflow_note:
        combined = f"{combined}\n{overflow_note}".strip() if combined else overflow_note

    _append_value(table.cell(15, 0), combined)


def _build_overflow_document(overflow_sources, license_request):
    """Builds a standalone docx listing sources beyond the main form's 7
    slots, using the same column structure (ردیف/نام چشمه/اکتیویته/
    شماره سریال/نیمه‌عمر/توضیحات) as the main specification table's source
    rows — but as a simple single table rather than cloning the original
    template's merged-cell layout, since this is an appendix, not a
    second copy of the official form."""

    doc = Document()

    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = title.add_run(
        _to_persian_digits(
            f"پیوست شماره ۱ - ادامه فهرست چشمه‌های درخواستی ({license_request.facility})"
        )
    )
    run.font.name = "B Nazanin"
    run.font.size = Pt(14)
    run.bold = True

    doc.add_paragraph()  # spacer

    headers = ["ردیف", "نام چشمه", "اکتیویته میانگین (mCi)", "شماره سریال", "نیمه عمر", "توضیحات"]

    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"

    for col, text in enumerate(headers):
        cell = table.rows[0].cells[col]
        _set_cell_value(cell, text)
        for p in cell.paragraphs:
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    for i, source in enumerate(overflow_sources):

        row_cells = table.add_row().cells

        activity = ""
        if source.activity is not None:
            activity = f"{source.activity} {source.get_activity_unit_display()}"

        type_label = source.get_source_type_display()
        description = source.description or ""
        combined_description = f"{type_label} - {description}" if description else type_label

        # Row numbering continues from where the main form left off (8, 9, ...)
        row_number = _to_persian_digits(str(i + MAIN_TABLE_ROWS + 1))

        values = [
            row_number,
            source.nuclide.name,
            activity,
            source.serial_number,
            _format_half_life(source.nuclide.half_life),
            combined_description,
        ]

        for col, value in enumerate(values):
            _set_cell_value(row_cells[col], value)

    return doc