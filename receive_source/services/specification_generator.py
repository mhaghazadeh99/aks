"""
Fills the "فرم مشخصات چشمه‌ها/پسماندهای پرتوزا" template with data from a
ReceiveRequest and saves it as a ReceiveAttachment(SPECIFICATION).

IMPORTANT — this was built directly against the docx you attached, but
docx cell layout is fragile: if your live template differs even slightly
(extra/merged cells, reordered rows), the label-matching below may need
adjusting. Verify against a real generated file before relying on it.

Design: rather than assuming fixed row/column indices (risky — merged
cells make python-docx's row.cells indices easy to miscount), this finds
each target cell by matching a snippet of its label text and appends the
value as a new BOLD run right after the label, since the paper form has
no separate blank "answer" cell — the label cell itself is where the
value goes (originally handwritten after the colon).

Also note: your docx uses SpecificationSigner (imported in views.py) for
the actual signature stamping — that part is untouched/reused as-is. You
will need placeholder text in the template for the CONTROL and CEO
signature rows, matching whatever pattern SpecificationSigner looks for
on CREATOR/MANAGER/DEPUTY today (it works off `current_step.name`, i.e.
literally "CONTROL" / "CEO").
"""

import os
import shutil

from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext as _

from docx import Document

from ..models import ReceiveAttachment, ReceiveAttachmentType


# Configure this to wherever the blank template lives in your project,
# e.g. BASE_DIR / "receiving" / "templates_docx" / "receive_specification_template.docx"
TEMPLATE_PATH = getattr(
    settings,
    "RECEIVE_SPECIFICATION_TEMPLATE_PATH",
    os.path.join(settings.BASE_DIR, "receiving", "templates_docx", "receive_specification_template.docx"),
)


def _iter_cells(document):
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                yield table, row, cell


def _append_value(cell, value, bold=True):
    """Appends ' <value>' as a new run at the end of the cell's first
    paragraph — safe for merged cells since python-docx resolves them to
    the same underlying <w:tc>."""
    if value in (None, ""):
        return
    paragraph = cell.paragraphs[0]
    run = paragraph.add_run(f"  {value}")
    run.bold = bold


def _find_and_fill(document, label_snippet, value, seen_cells, bold=True):
    """
    Finds the FIRST cell (in document order) containing `label_snippet`
    that hasn't already been filled in this pass, and appends `value` to
    it. `seen_cells` (a set of cell `_tc` element ids) prevents filling
    the same merged cell twice when multiple duplicate-label rows exist
    (e.g. the two "تعداد پرسنل اعزامی" blocks — caller must disambiguate
    those by passing distinct, more specific snippets, e.g. including a
    row-specific neighboring word).
    """
    for _table, _row, cell in _iter_cells(document):
        tc_id = id(cell._tc)
        if tc_id in seen_cells:
            continue
        if label_snippet in cell.text:
            _append_value(cell, value, bold=bold)
            seen_cells.add(tc_id)
            return True
    return False


def generate_receive_specification(receive_request, user):

    if not os.path.exists(TEMPLATE_PATH):
        raise FileNotFoundError(
            f"Receive specification template not found at {TEMPLATE_PATH}. "
            f"Set settings.RECEIVE_SPECIFICATION_TEMPLATE_PATH."
        )

    document = Document(TEMPLATE_PATH)
    seen_cells = set()

    facility = receive_request.facility

    # ---- Section 1: facility info ----
    _find_and_fill(document, "نام مرکز تحویل دهنده", facility.name, seen_cells)
    _find_and_fill(
        document, "شماره و تاریخ نامه",
        f"{receive_request.inquiry_letter_number or '-'} / {receive_request.inquiry_letter_date or '-'}",
        seen_cells,
    )
    address = " ".join(filter(None, [facility.address1, facility.address2, facility.telephone]))
    _find_and_fill(document, "آدرس و شماره تلفن", address, seen_cells)
    _find_and_fill(document, "کد پستی", facility.postal_code, seen_cells)
    _find_and_fill(document, "شناسه ملی", facility.national_id, seen_cells)
    _find_and_fill(document, "کد اقتصادی", facility.economic_code, seen_cells)
    _find_and_fill(document, "برآورد مسافت", receive_request.distance_to_tehran_km, seen_cells)

    # ---- Section 2: sources/waste table — fill by row number cells ----
    # The template's data rows start with a bare "1", "2", "3" cell.
    sources = list(receive_request.sources.select_related("nuclide").order_by("specification_order"))

    for table in document.tables:
        for row in table.rows:
            first_cell_text = row.cells[0].text.strip()
            if first_cell_text.isdigit():
                idx = int(first_cell_text) - 1
                if 0 <= idx < len(sources):
                    source = sources[idx]
                    cells = row.cells
                    # Column order per the template: #, name(x3 merged),
                    # activity, qty(x2), half-life, shield(x4), burial(x3),
                    # storage(x4), sale prob, description
                    try:
                        cells[1].paragraphs[0].add_run(str(source.nuclide))
                        cells[4].paragraphs[0].add_run(
                            str(source.average_activity_mci) if source.average_activity_mci else ""
                        )
                        cells[5].paragraphs[0].add_run(str(source.quantity))
                        cells[7].paragraphs[0].add_run(source.half_life_display or "")
                        cells[11].paragraphs[0].add_run(_yes_no(source.needs_shield))
                        cells[14].paragraphs[0].add_run(_yes_no(source.needs_burial))
                        cells[15].paragraphs[0].add_run(source.storage_duration or "")
                        cells[19].paragraphs[0].add_run(source.sale_probability or "")
                        cells[20].paragraphs[0].add_run(source.description or "")
                    except IndexError:
                        # Template column layout differs from what was
                        # inspected — fall back to a single dumped cell so
                        # data isn't silently lost.
                        cells[-1].paragraphs[0].add_run(
                            f"{source.nuclide} | {source.average_activity_mci} mCi | "
                            f"qty {source.quantity} | {source.description or ''}"
                        )

    # ---- Section 3: logistics (both visit + operation blocks) ----
    if receive_request.pre_operation_visit_needed is not None:
        _find_and_fill(
            document, "بازدید قبل از عملیات",
            _("لازم است") if receive_request.pre_operation_visit_needed else _("لازم نیست"),
            seen_cells,
        )

    # These two blocks share identical label text in the template, so we
    # rely on fill order: first occurrence = visit team, second = operation
    # team, matching the template's top-to-bottom layout.
    visit_personnel = (
        f"کارشناس: {receive_request.visit_expert_count or 0}  "
        f"تکنسین: {receive_request.visit_technician_count or 0}  "
        f"راننده: {receive_request.visit_driver_count or 0}"
    )
    _find_and_fill(document, "تعداد پرسنل اعزامی", visit_personnel, seen_cells)

    operation_personnel = (
        f"کارشناس: {receive_request.operation_expert_count}  "
        f"تکنسین: {receive_request.operation_technician_count}  "
        f"راننده: {receive_request.operation_driver_count}"
    )
    _find_and_fill(document, "تعداد پرسنل اعزامی", operation_personnel, seen_cells)

    if receive_request.route_difficulty:
        _find_and_fill(document, "سختی مسیر", receive_request.get_route_difficulty_display(), seen_cells)

    _find_and_fill(document, "تعداد روز اسکان", receive_request.accommodation_days, seen_cells)
    _find_and_fill(document, "هزینه غذا", receive_request.food_cost_days, seen_cells)
    _find_and_fill(document, "وسایل جانبی مورد استفاده", receive_request.peripheral_equipment, seen_cells)
    _find_and_fill(document, "سایر هزینه", receive_request.other_costs, seen_cells)
    _find_and_fill(document, "توضیحات", receive_request.logistics_notes, seen_cells)

    # ---- Save as a new attachment ----
    tmp_dir = os.path.join(settings.MEDIA_ROOT if hasattr(settings, "MEDIA_ROOT") else "/tmp", "tmp_receive_spec")
    os.makedirs(tmp_dir, exist_ok=True)
    tmp_path = os.path.join(tmp_dir, f"receive_spec_{receive_request.pk}_{int(timezone.now().timestamp())}.docx")
    document.save(tmp_path)

    with open(tmp_path, "rb") as f:
        attachment = ReceiveAttachment.objects.create(
            receive_request=receive_request,
            attachment_type=ReceiveAttachmentType.SPECIFICATION,
            uploaded_by=user,
        )
        attachment.file.save(os.path.basename(tmp_path), f, save=True)

    os.remove(tmp_path)
    return attachment


def _yes_no(value):
    if value is True:
        return "دارد"
    if value is False:
        return "ندارد"
    return ""