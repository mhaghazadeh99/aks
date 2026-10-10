"""
laboratory/services/pdf_tools.py -- DOCX -> PDF, used ONLY for the final report
once every signature is in. Until then reports stay as editable Word files.

WHY THE OLD PDF CAME OUT BROKEN (found by converting a real generated report)
  1. Every table cell paragraph in the templates carries "space after 200" and
     the No. column also a 360-twip left indent inside a 672-twip cell. In Word
     that is tolerable; in LibreOffice (and with fallback fonts) two-digit
     numbers wrapped ("1 / 3") and every row grew, so the page overflowed:
     the logo table ended up alone on page 1, the signature table split over
     the next page, and a 13-sample run became 5 pages instead of 2.
  2. The footer said "Page N of 1" -- the "of 1" is typed text in the template,
     not a field.
  3. LibreOffice mirrored the floating Alpha/Beta report + signature table (columns in reverse
     order) although Word draws it left-to-right -> pin_ltr_tables().
  4. (Gamma) a vertically merged "Code No." cell with rotated text
     (w:textDirection) is mis-drawn by LibreOffice.
  prepare_docx_for_pdf() fixes all three on a COPY; the Word file is untouched.

SERVER REQUIREMENTS
  * LibreOffice (`apt-get install libreoffice-writer`).
  * The fonts the templates use: B Nazanin, B Lotus, IPT Lotus (and B Zar for the
    footer). Copy the .ttf files to /usr/local/share/fonts and run `fc-cache -f`.
    Without them LibreOffice substitutes wider fonts; the layout fixes above keep
    the page count right, but letter shapes will differ from Word.

Each conversion uses its own throwaway LibreOffice profile
(-env:UserInstallation) so concurrent conversions don't fight over one profile.
"""

import copy
import os
import re
import shutil
import subprocess
import tempfile
from io import BytesIO

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt
from docx.text.paragraph import Paragraph


class PdfConversionError(RuntimeError):
    pass


# ---------------------------------------------------------------------
# helpers shared with report_generator (these are fine to keep in the Word file too)
# ---------------------------------------------------------------------

def tidy_cell_paragraph(paragraph, align=None):
    """Zero spacing before/after, single line spacing, no indent, no
    'contextual spacing' -- so a table row keeps the height the template set
    instead of growing, and short numbers don't wrap."""
    pf = paragraph.paragraph_format
    pf.space_before = Pt(0)
    pf.space_after = Pt(0)
    pf.line_spacing = 1.0
    pf.left_indent = Pt(0)
    pf.first_line_indent = Pt(0)
    pPr = paragraph._p.pPr
    if pPr is not None:
        for el in pPr.findall(qn("w:contextualSpacing")):
            pPr.remove(el)
    if align is not None:
        pf.alignment = align


def fix_footer_page_count(doc, total_pages=1):
    """The templates' footer reads 'Page <PAGE field> of 1' with the '1' typed in.
    Replace that typed text with a real NUMPAGES field."""
    seen = set()
    for section in doc.sections:
        footer = section.footer
        if footer.is_linked_to_previous:
            continue
        root = footer._element
        if id(root) in seen:
            continue
        seen.add(id(root))
        if any("NUMPAGES" in (e.text or "") for e in root.iter(qn("w:instrText"))):
            continue
        for t in list(root.iter(qn("w:t"))):
            if not (t.text and re.fullmatch(r"\s*of\s+\d+\s*", t.text)):
                continue
            run = t.getparent()
            t.text = " of "
            t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
            rpr = run.find(qn("w:rPr"))

            def new_run():
                r = OxmlElement("w:r")
                if rpr is not None:
                    r.append(copy.deepcopy(rpr))
                return r

            cursor = run
            for kind in ("begin", "instr", "separate", "text", "end"):
                r = new_run()
                if kind == "instr":
                    el = OxmlElement("w:instrText")
                    el.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
                    el.text = " NUMPAGES "
                elif kind == "text":
                    el = OxmlElement("w:t")
                    el.text = str(total_pages)
                else:
                    el = OxmlElement("w:fldChar")
                    el.set(qn("w:fldCharType"), kind)
                r.append(el)
                cursor.addnext(r)
                cursor = r


_TBLPR_AFTER_BIDI = (
    "tblStyleRowBandSize", "tblStyleColBandSize", "tblW", "jc", "tblCellSpacing", "tblInd",
    "tblBorders", "shd", "tblLayout", "tblCellMar", "tblLook", "tblCaption", "tblDescription",
)


def pin_ltr_tables(doc):
    """A table with no <w:bidiVisual> is a left-to-right table in Word: first cell on the LEFT.
    LibreOffice mirrors some of these (the floating report/signature table in the Alpha/Beta
    form: "No." jumped to the right edge and the signature columns came out reversed). Writing
    <w:bidiVisual w:val="0"/> removes the ambiguity. Tables that already say bidiVisual (the
    right-to-left Gamma tables) are left exactly as they are."""
    for tbl in doc.element.body.iter(qn("w:tbl")):
        tblPr = tbl.tblPr
        if tblPr is None or tblPr.find(qn("w:bidiVisual")) is not None:
            continue
        el = OxmlElement("w:bidiVisual")
        el.set(qn("w:val"), "0")
        for child in tblPr:
            if child.tag.split("}")[1] in _TBLPR_AFTER_BIDI:
                child.addprevious(el)
                break
        else:
            tblPr.append(el)


# ---------------------------------------------------------------------
# PDF preparation + conversion
# ---------------------------------------------------------------------

def prepare_docx_for_pdf(docx_bytes):
    """Returns docx bytes adjusted for LibreOffice (see module docstring).
    The input is not modified."""
    doc = Document(BytesIO(docx_bytes))
    body = doc.element.body

    for tc in body.iter(qn("w:tc")):
        pr = tc.tcPr
        if pr is not None:
            td = pr.find(qn("w:textDirection"))
            if td is not None:
                pr.remove(td)
        for p in tc.iter(qn("w:p")):
            tidy_cell_paragraph(Paragraph(p, None))

    # reports made before the footer fix, or edited by hand, still get a real page count
    pin_ltr_tables(doc)
    fix_footer_page_count(doc)      # LibreOffice recomputes the field, so the cached value doesn't matter
    out = BytesIO()
    doc.save(out)
    return out.getvalue()


def docx_bytes_to_pdf_bytes(docx_bytes, timeout=90):
    """Converts one in-memory .docx to PDF with headless LibreOffice. Raises
    PdfConversionError (with LibreOffice's own stderr) on any failure; never
    returns a partial or empty PDF."""
    docx_bytes = prepare_docx_for_pdf(docx_bytes)

    workdir = tempfile.mkdtemp(prefix="docx2pdf_")
    profile = tempfile.mkdtemp(prefix="lo_profile_")
    try:
        docx_path = os.path.join(workdir, "input.docx")
        with open(docx_path, "wb") as f:
            f.write(docx_bytes)

        cmd = [
            "soffice", "--headless", "--norestore", "--nologo",
            f"-env:UserInstallation=file://{profile}",
            "--convert-to", "pdf", "--outdir", workdir, docx_path,
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=timeout)
        except FileNotFoundError:
            raise PdfConversionError(
                "LibreOffice ('soffice') isn't installed on this server. "
                "Install it (e.g. `apt-get install libreoffice-writer`) to produce the final PDF."
            )
        except subprocess.TimeoutExpired:
            raise PdfConversionError(f"PDF conversion timed out after {timeout}s.")

        pdf_path = os.path.join(workdir, "input.pdf")
        if not os.path.exists(pdf_path):
            raise PdfConversionError(
                f"PDF conversion failed (exit {result.returncode}): "
                f"{result.stderr.decode(errors='replace').strip()}"
            )
        with open(pdf_path, "rb") as f:
            return f.read()
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
        shutil.rmtree(profile, ignore_errors=True)