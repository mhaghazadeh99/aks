"""
laboratory/services/pdf_tools.py -- DOCX -> PDF conversion, PDF merging, and a
generated signature page. New file; used by report_generator.py (final output
is now PDF, not an editable .docx) and signature_service.py (signatures are
stamped onto an appended page, not into cells of the original document --
see the long comment in signature_service.py for why).

SERVER REQUIREMENT: LibreOffice must be installed (`apt-get install
libreoffice` on Debian/Ubuntu, or `libreoffice-writer` for a smaller
install). This shells out to `soffice --headless`. Tested end-to-end in a
Linux sandbox against the actual Alpha/Beta template — conversion, a 2-file
merge, and a reportlab-generated signature page all round-tripped correctly.

Each conversion runs with an ISOLATED user profile (`-env:UserInstallation`)
and is cleaned up afterward. This matters under a real web server: LibreOffice
headless has known lock/crash issues when two conversions share a profile at
the same time, which WILL happen the moment two reports generate concurrently
across worker processes. Without this, expect intermittent failures under load.
"""

import os
import shutil
import subprocess
import tempfile
from io import BytesIO

from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas


class PdfConversionError(RuntimeError):
    pass


def docx_bytes_to_pdf_bytes(docx_bytes, timeout=60):
    """Converts one in-memory .docx to PDF via a headless LibreOffice
    subprocess with its own throwaway profile. Raises PdfConversionError
    with LibreOffice's own stderr if conversion fails (missing/corrupt
    template, LibreOffice not installed, timeout, ...) -- never returns a
    silently-empty or partial PDF."""
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
                "Install it (e.g. `apt-get install libreoffice-writer`) to generate PDF reports."
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


def merge_pdfs(pdf_byte_chunks):
    """Concatenates several in-memory PDFs (each a bytes object) into one,
    in order. Returns the merged PDF's bytes."""
    writer = PdfWriter()
    for data in pdf_byte_chunks:
        reader = PdfReader(BytesIO(data))
        for page in reader.pages:
            writer.add_page(page)
    out = BytesIO()
    writer.write(out)
    out.seek(0)
    return out.read()


def strip_trailing_pages(pdf_bytes, keep_first_n_pages):
    """Returns a PDF containing only the first `keep_first_n_pages` pages --
    used to remove a previously-appended signature page before appending a
    freshly regenerated one (see signature_service.py)."""
    reader = PdfReader(BytesIO(pdf_bytes))
    writer = PdfWriter()
    for page in reader.pages[:keep_first_n_pages]:
        writer.add_page(page)
    out = BytesIO()
    writer.write(out)
    out.seek(0)
    return out.read()


def page_count(pdf_bytes):
    return len(PdfReader(BytesIO(pdf_bytes)).pages)


def build_signature_page(title, steps):
    """
    Builds a single-page PDF listing every signature step and its status --
    this is appended as the LAST page of a report, rather than stamping
    signatures into specific cells of the original content pages.

    WHY a separate page instead of inline stamping (like the old .docx
    signer did, placing a picture into a specific table cell): once the
    report is PDF, "which cell" has no good answer any more -- the content
    came from a .docx template whose exact page/coordinate layout after
    LibreOffice's own pagination isn't something this code can reliably
    predict, especially across a multi-page (chunked, >12 sample) report.
    A dedicated page is unambiguous, always has room for N signers, and
    works identically whether the report is 1 page or 20. The tradeoff:
    signatures no longer appear next to the data they're approving, only
    at the end. If you want them stamped inline instead, I'd need the
    exact page/coordinate layout of your real templates (same way sending
    the Alpha/Beta .docx let me fix the header-label issue precisely).

    `steps`: list of dicts with role, name, date, status, comments (any may
    be blank/None for a step not yet reached).
    """
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4

    c.setFont("Helvetica-Bold", 14)
    c.drawString(20 * mm, height - 25 * mm, str(title))

    c.setFont("Helvetica", 9)
    c.drawString(20 * mm, height - 32 * mm, "Signatures")

    y = height - 42 * mm
    row_h = 22 * mm
    col_role = 20 * mm
    col_name = 80 * mm
    col_date = 130 * mm
    col_status = 160 * mm

    c.setFont("Helvetica-Bold", 9)
    c.drawString(col_role, y, "Role")
    c.drawString(col_name, y, "Name")
    c.drawString(col_date, y, "Date")
    c.drawString(col_status, y, "Status")
    y -= 6 * mm
    c.line(20 * mm, y, width - 20 * mm, y)
    y -= 8 * mm

    c.setFont("Helvetica", 9)
    for step in steps:
        if y < 20 * mm:
            c.showPage()
            y = height - 25 * mm
            c.setFont("Helvetica", 9)
        c.drawString(col_role, y, str(step.get("role") or "-"))
        c.drawString(col_name, y, str(step.get("name") or "-"))
        c.drawString(col_date, y, str(step.get("date") or "-"))
        c.drawString(col_status, y, str(step.get("status") or "-"))
        comment = step.get("comments")
        if comment:
            y -= 5 * mm
            c.setFont("Helvetica-Oblique", 8)
            c.drawString(col_name, y, f"Comment: {comment}"[:110])
            c.setFont("Helvetica", 9)
        y -= row_h - (5 * mm if comment else 0)

    c.save()
    buf.seek(0)
    return buf.read()
