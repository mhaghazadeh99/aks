"""
laboratory/services/final_report.py

The report stays an editable Word file for the whole signature chain. When the
LAST signature is in, this turns that signed Word file into a PDF and stores it
as the FINAL_REPORT attachment -- the one people should circulate.

The signed .docx is left in place (it is the audit trail of what was actually
signed); only the PDF is meant to be handed out. Calling this again simply
replaces the PDF (e.g. after installing LibreOffice or the missing fonts).
"""

from django.core.files.base import ContentFile

from ..models import AnalysisAttachment, LabAttachmentType
from .pdf_tools import docx_bytes_to_pdf_bytes


def finalize_report_pdf(report_attachment, user):
    """report_attachment: the signed REPORT (.docx) AnalysisAttachment.
    Returns the new FINAL_REPORT attachment. Raises PdfConversionError if the
    conversion fails -- the caller decides how to tell the user; the signatures
    themselves are already saved and unaffected."""
    with report_attachment.file.open("rb") as f:
        docx_bytes = f.read()

    pdf_bytes = docx_bytes_to_pdf_bytes(docx_bytes)

    if report_attachment.analysis_id:
        target = {"analysis": report_attachment.analysis}
        filename = "gamma_report_final.pdf"
    else:
        target = {"counting_run": report_attachment.counting_run}
        filename = "alpha_beta_report_final.pdf"

    old = AnalysisAttachment.objects.filter(attachment_type=LabAttachmentType.FINAL_REPORT, **target).first()
    if old:
        old.file.delete(save=False)
        old.delete()

    final = AnalysisAttachment.objects.create(
        attachment_type=LabAttachmentType.FINAL_REPORT, uploaded_by=user, **target,
    )
    final.file.save(filename, ContentFile(pdf_bytes), save=True)
    return final