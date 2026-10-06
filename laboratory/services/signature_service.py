# import copy

# from docx import Document
# from docx.shared import Mm
# from docx.oxml.ns import qn
# from docx.oxml import OxmlElement
# from django.utils import timezone

# from operations.services.specification_generator import _format_jalali_date

# from docx.table import _Cell


# def _cell_at(table, row_idx, grid_col):
#     """Row-aware replacement for table.cell(): python-docx's version breaks
#     when rows have different grid widths (e.g. the 7-wide signature rows in an 8-column grid)."""
#     tr = table.rows[row_idx]._tr
#     pos = tr.grid_before
#     for tc in tr.tc_lst:
#         span = tc.grid_span
#         if pos <= grid_col < pos + span:
#             return _Cell(tc, table)
#         pos += span
#     raise IndexError(f"row {row_idx} has no cell at grid column {grid_col}")

# class LabReportSigner:
#     """Handles BOTH report templates — they use different table indices
#     and (for Alpha/Beta) different gridSpans, but the same 3-role
#     ANALYST/LAB_MANAGER/OPS_MANAGER sequence and the same floating-
#     picture technique as the license/receive signers."""

#     def __init__(self, document_path, report_kind):
#         self.document = Document(document_path)
#         if report_kind not in ("GAMMA", "ALPHA_BETA"):
#             raise ValueError("report_kind must be 'GAMMA' or 'ALPHA_BETA'")
#         self.report_kind = report_kind

#     def _add_floating_picture(self, paragraph, image_path, width, top_offset=Mm(0), left_offset=Mm(0)):
#         run = paragraph.add_run()
#         run.add_picture(image_path, width=width)

#         drawing = run._element.find(qn('w:drawing'))
#         inline = drawing.find(qn('wp:inline'))

#         extent = inline.find(qn('wp:extent'))
#         doc_pr = inline.find(qn('wp:docPr'))
#         cnv_graphic_frame_pr = inline.find(qn('wp:cNvGraphicFramePr'))
#         graphic = inline.find(qn('a:graphic'))

#         anchor = OxmlElement('wp:anchor')
#         anchor.set('distT', '0'); anchor.set('distB', '0')
#         anchor.set('distL', '0'); anchor.set('distR', '0')
#         anchor.set('simplePos', '0')
#         anchor.set('relativeHeight', '251659264')
#         anchor.set('behindDoc', '0')
#         anchor.set('locked', '0')
#         anchor.set('layoutInCell', '1')
#         anchor.set('allowOverlap', '1')

#         simple_pos = OxmlElement('wp:simplePos')
#         simple_pos.set('x', '0'); simple_pos.set('y', '0')
#         anchor.append(simple_pos)

#         position_h = OxmlElement('wp:positionH')
#         position_h.set('relativeFrom', 'column')
#         h_offset = OxmlElement('wp:posOffset')
#         h_offset.text = str(int(left_offset))
#         position_h.append(h_offset)
#         anchor.append(position_h)

#         position_v = OxmlElement('wp:positionV')
#         position_v.set('relativeFrom', 'paragraph')
#         v_offset = OxmlElement('wp:posOffset')
#         v_offset.text = str(int(top_offset))
#         position_v.append(v_offset)
#         anchor.append(position_v)

#         anchor.append(copy.deepcopy(extent))

#         effect_extent = OxmlElement('wp:effectExtent')
#         for side in ('l', 't', 'r', 'b'):
#             effect_extent.set(side, '0')
#         anchor.append(effect_extent)

#         anchor.append(OxmlElement('wp:wrapNone'))
#         anchor.append(copy.deepcopy(doc_pr))
#         anchor.append(copy.deepcopy(cnv_graphic_frame_pr))
#         anchor.append(copy.deepcopy(graphic))

#         drawing.replace(inline, anchor)
#         return run

#     # ----- row index maps, verified against the templates' raw XML -----

#     _GAMMA_ROW_BY_ROLE = {"ANALYST": 1, "LAB_MANAGER": 2, "OPS_MANAGER": 3}
#     _ALPHA_BETA_ROW_BY_ROLE = {"ANALYST": 20, "LAB_MANAGER": 21, "OPS_MANAGER": 22}

#     def _sign_gamma(self, row_index, profile):
#         table = self.document.tables[2]
       
#         name_cell = _cell_at(table, row_index, 1)   # gamma
#         date_cell = _cell_at(table, row_index, 2)
#         signature_cell = _cell_at(table, row_index, 3)
    

#         name_cell.paragraphs[0].add_run(profile.full_name)
#         date_cell.paragraphs[0].add_run(_format_jalali_date(timezone.localdate()))
#         signature_path = (
#             profile.signature_clean.path if profile.signature_clean else profile.signature_image.path
#         )
#         self._add_floating_picture(
#             signature_cell.paragraphs[0], signature_path,
#             width=Mm(28), top_offset=Mm(-8), left_offset=Mm(0),
#         )

#     def _sign_alpha_beta(self, row_index, profile):
#         table = self.document.tables[1]
       
#         # verified gridSpans: col0-1=signature, col2-3=date, col4=name, col5-6=role(static)
#         signature_cell = _cell_at(table, row_index, 0)   # alpha/beta
#         date_cell = _cell_at(table, row_index, 2)
#         name_cell = _cell_at(table, row_index, 4)

#         name_cell.paragraphs[0].add_run(profile.full_name)
#         date_cell.paragraphs[0].add_run(_format_jalali_date(timezone.localdate()))
#         signature_path = (
#             profile.signature_clean.path if profile.signature_clean else profile.signature_image.path
#         )
#         self._add_floating_picture(
#             signature_cell.paragraphs[0], signature_path,
#             width=Mm(28), top_offset=Mm(-8), left_offset=Mm(0),
#         )

#     def sign(self, profile, role):
#         if not profile.signature_image:
#             raise ValueError("User does not have a signature image.")

#         if self.report_kind == "GAMMA":
#             row_index = self._GAMMA_ROW_BY_ROLE.get(role)
#             if row_index is None:
#                 raise ValueError(f"Unknown role: {role}")
#             self._sign_gamma(row_index, profile)
#         else:
#             row_index = self._ALPHA_BETA_ROW_BY_ROLE.get(role)
#             if row_index is None:
#                 raise ValueError(f"Unknown role: {role}")
#             self._sign_alpha_beta(row_index, profile)

#     def save(self, filename):
#         self.document.save(filename)

"""
laboratory/services/signature_service.py

Replaces the old .docx-cell-stamping LabReportSigner (which opened the report
with python-docx, dropped a floating signature image into a specific table
row/column, and re-saved as .docx). That approach stops working once the
final report is a PDF -- there's no equivalent "cell" to write into once
LibreOffice has paginated and flattened the content, especially now that a
report can be more than one page (chunked for >12 samples).

Instead: the report's CONTENT pages are generated once (report_generator.py)
and never touched again by signing. Every signature action rebuilds a single
SIGNATURE PAGE from the full current list of approval steps (via
pdf_tools.build_signature_page) and replaces whatever signature page was
appended last time with the freshly rebuilt one -- so the signature page
always reflects every step's current status, not just the one just signed.

This needs to know where the content ends and the (possibly already-present)
signature page begins. AnalysisAttachment gets one new field for that --
see BIG_WORKFLOW_CHANGE.md:
    content_page_count = models.PositiveSmallIntegerField(null=True, blank=True)
set once, by report_generator.py, right after it generates the content (before
any signature page exists) -- see the note at the bottom of this file for the
one extra line that needs adding there.
"""

from .pdf_tools import build_signature_page, merge_pdfs, page_count, strip_trailing_pages


class PdfReportSigner:

    def __init__(self, attachment):
        """attachment: the AnalysisAttachment (LabAttachmentType.REPORT) being signed."""
        self.attachment = attachment

    def _report_title(self):
        target = self.attachment.analysis or self.attachment.counting_run
        if self.attachment.analysis_id:
            return f"Gamma Report — {target.sample.sample_id}"
        return f"Alpha/Beta Counting Report — {target.run_id}"

    def _steps_payload(self, approvals):
        steps = []
        for step in approvals.order_by("order"):
            steps.append({
                "role": step.get_role_display(),
                "name": str(step.user) if step.user else None,
                "date": step.signed_date.isoformat() if step.signed_date else None,
                "status": step.get_status_display(),
                "comments": step.comments,
            })
        return steps

    def sign(self, approvals):
        """
        Rebuilds the signature page from the CURRENT state of every approval
        step (call this AFTER approve_step()/reject_step() has already updated
        the step being actioned, so the new page reflects it) and replaces the
        attachment's file in place.

        `approvals`: the queryset/list of every AnalysisApproval for this
        analysis or counting run (same thing current_step_for() is given).
        """
        with self.attachment.file.open("rb") as f:
            current_bytes = f.read()

        content_pages = self.attachment.content_page_count
        if content_pages is None:
            # Should always be set by report_generator.py -- fall back to "no
            # signature page exists yet" rather than guessing wrong and
            # cutting into real content.
            content_pages = page_count(current_bytes)

        content_only = strip_trailing_pages(current_bytes, content_pages)

        sig_page = build_signature_page(self._report_title(), self._steps_payload(approvals))
        final_bytes = merge_pdfs([content_only, sig_page])

        filename = self.attachment.file.name.rsplit("/", 1)[-1]
        self.attachment.file.delete(save=False)
        from django.core.files.base import ContentFile
        self.attachment.file.save(filename, ContentFile(final_bytes), save=True)
