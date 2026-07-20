from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile

from docx import Document

from operations.models import (
    LicenseAttachment,
    LicenseAttachmentType,
)

def generate_specification(
    license_request,
    generated_by,
):
    """
    Generate DSRS Specification document.

    Returns:
        LicenseAttachment
    """

    template_path = (
        Path(settings.BASE_DIR)
        / "templates"
        / "documents"
        / "dsrs_specification.docx"
    )

    doc = Document(template_path)

    # --------------------------------------------------
    # Fill document
    # --------------------------------------------------

    _fill_header(doc, license_request)

    _fill_facility(
        doc,
        license_request.facility,
    )

    _fill_sources(
        doc,
        license_request.sources
        .select_related("nuclide")
        .order_by("specification_order")
    )

    _fill_description(
        doc,
        license_request.description,
    )

    # --------------------------------------------------
    # Save to memory
    # --------------------------------------------------

    buffer = BytesIO()

    doc.save(buffer)

    buffer.seek(0)

    # --------------------------------------------------
    # Remove previous generated specification
    # --------------------------------------------------

    LicenseAttachment.objects.filter(

        license=license_request,

        attachment_type=LicenseAttachmentType.SPECIFICATION,

    ).delete()

    # --------------------------------------------------
    # Save attachment
    # --------------------------------------------------

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

    return attachment



def _fill_header(doc, license):

    pass


def _fill_facility(doc, facility):

    pass


def _fill_sources(doc, sources):

    pass


def _fill_description(doc, description):

    pass