import copy

from docx import Document
from docx.shared import Mm
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from django.utils import timezone

from operations.services.specification_generator import _format_jalali_date

from docx.table import _Cell


def _cell_at(table, row_idx, grid_col):
    """Row-aware replacement for table.cell(): python-docx's version breaks
    when rows have different grid widths (e.g. the 7-wide signature rows in an 8-column grid)."""
    tr = table.rows[row_idx]._tr
    pos = tr.grid_before
    for tc in tr.tc_lst:
        span = tc.grid_span
        if pos <= grid_col < pos + span:
            return _Cell(tc, table)
        pos += span
    raise IndexError(f"row {row_idx} has no cell at grid column {grid_col}")

class LabReportSigner:
    """Handles BOTH report templates — they use different table indices
    and (for Alpha/Beta) different gridSpans, but the same 3-role
    ANALYST/LAB_MANAGER/OPS_MANAGER sequence and the same floating-
    picture technique as the license/receive signers."""

    def __init__(self, document_path, report_kind):
        self.document = Document(document_path)
        if report_kind not in ("GAMMA", "ALPHA_BETA"):
            raise ValueError("report_kind must be 'GAMMA' or 'ALPHA_BETA'")
        self.report_kind = report_kind

    def _add_floating_picture(self, paragraph, image_path, width, top_offset=Mm(0), left_offset=Mm(0)):
        run = paragraph.add_run()
        run.add_picture(image_path, width=width)

        drawing = run._element.find(qn('w:drawing'))
        inline = drawing.find(qn('wp:inline'))

        extent = inline.find(qn('wp:extent'))
        doc_pr = inline.find(qn('wp:docPr'))
        cnv_graphic_frame_pr = inline.find(qn('wp:cNvGraphicFramePr'))
        graphic = inline.find(qn('a:graphic'))

        anchor = OxmlElement('wp:anchor')
        anchor.set('distT', '0'); anchor.set('distB', '0')
        anchor.set('distL', '0'); anchor.set('distR', '0')
        anchor.set('simplePos', '0')
        anchor.set('relativeHeight', '251659264')
        anchor.set('behindDoc', '0')
        anchor.set('locked', '0')
        anchor.set('layoutInCell', '1')
        anchor.set('allowOverlap', '1')

        simple_pos = OxmlElement('wp:simplePos')
        simple_pos.set('x', '0'); simple_pos.set('y', '0')
        anchor.append(simple_pos)

        position_h = OxmlElement('wp:positionH')
        position_h.set('relativeFrom', 'column')
        h_offset = OxmlElement('wp:posOffset')
        h_offset.text = str(int(left_offset))
        position_h.append(h_offset)
        anchor.append(position_h)

        position_v = OxmlElement('wp:positionV')
        position_v.set('relativeFrom', 'paragraph')
        v_offset = OxmlElement('wp:posOffset')
        v_offset.text = str(int(top_offset))
        position_v.append(v_offset)
        anchor.append(position_v)

        anchor.append(copy.deepcopy(extent))

        effect_extent = OxmlElement('wp:effectExtent')
        for side in ('l', 't', 'r', 'b'):
            effect_extent.set(side, '0')
        anchor.append(effect_extent)

        anchor.append(OxmlElement('wp:wrapNone'))
        anchor.append(copy.deepcopy(doc_pr))
        anchor.append(copy.deepcopy(cnv_graphic_frame_pr))
        anchor.append(copy.deepcopy(graphic))

        drawing.replace(inline, anchor)
        return run

    # ----- row index maps, verified against the templates' raw XML -----

    _GAMMA_ROW_BY_ROLE = {"ANALYST": 1, "LAB_MANAGER": 2, "OPS_MANAGER": 3}
    _ALPHA_BETA_ROW_BY_ROLE = {"ANALYST": 20, "LAB_MANAGER": 21, "OPS_MANAGER": 22}

    def _sign_gamma(self, row_index, profile):
        table = self.document.tables[2]
       
        name_cell = _cell_at(table, row_index, 1)   # gamma
        date_cell = _cell_at(table, row_index, 2)
        signature_cell = _cell_at(table, row_index, 3)
    

        name_cell.paragraphs[0].add_run(profile.full_name)
        date_cell.paragraphs[0].add_run(_format_jalali_date(timezone.localdate()))
        signature_path = (
            profile.signature_clean.path if profile.signature_clean else profile.signature_image.path
        )
        self._add_floating_picture(
            signature_cell.paragraphs[0], signature_path,
            width=Mm(28), top_offset=Mm(-8), left_offset=Mm(0),
        )

    def _sign_alpha_beta(self, row_index, profile):
        table = self.document.tables[1]
       
        # verified gridSpans: col0-1=signature, col2-3=date, col4=name, col5-6=role(static)
        signature_cell = _cell_at(table, row_index, 0)   # alpha/beta
        date_cell = _cell_at(table, row_index, 2)
        name_cell = _cell_at(table, row_index, 4)

        name_cell.paragraphs[0].add_run(profile.full_name)
        date_cell.paragraphs[0].add_run(_format_jalali_date(timezone.localdate()))
        signature_path = (
            profile.signature_clean.path if profile.signature_clean else profile.signature_image.path
        )
        self._add_floating_picture(
            signature_cell.paragraphs[0], signature_path,
            width=Mm(28), top_offset=Mm(-8), left_offset=Mm(0),
        )

    def sign(self, profile, role):
        if not profile.signature_image:
            raise ValueError("User does not have a signature image.")

        if self.report_kind == "GAMMA":
            row_index = self._GAMMA_ROW_BY_ROLE.get(role)
            if row_index is None:
                raise ValueError(f"Unknown role: {role}")
            self._sign_gamma(row_index, profile)
        else:
            row_index = self._ALPHA_BETA_ROW_BY_ROLE.get(role)
            if row_index is None:
                raise ValueError(f"Unknown role: {role}")
            self._sign_alpha_beta(row_index, profile)

    def save(self, filename):
        self.document.save(filename)