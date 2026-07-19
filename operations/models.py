from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _

from dashboard.models import ActivityUnit   # or wherever your ActivityUnit choices are
from facilities.models import Facility

from reference.models import Nuclides

import os


def license_attachment_path(instance, filename):
    """
    Store files as:

    media/licenses/<license_id>/<attachment_type>/<filename>

    Example:
    licenses/15/letter/request.pdf
    """

    attachment_type = instance.attachment_type.lower()

    return os.path.join(
        "licenses",
        str(instance.license.id),
        attachment_type,
        filename,
    )
class LicenseStatus(models.TextChoices):

    DRAFT = "DRAFT", _("Draft")

    OCR = "OCR", _("OCR")

    SIGNATURE = "SIGNATURE", _("Waiting Signature")

    CONTRACT = "CONTRACT", _("Contract")

    FINANCE = "FINANCE", _("Finance")

    ISSUED = "ISSUED", _("Issued")

    COMPLETED = "COMPLETED", _("Completed")



class LicenseRequest(models.Model):

    facility = models.ForeignKey(
        Facility,
        on_delete=models.PROTECT,
        related_name="license_requests",
    )

    letter_number = models.CharField(
        max_length=100,
        blank=True,
        null=True,
    )

    letter_date = models.DateField(
        blank=True,
        null=True,
    )

    contract_number = models.CharField(
        max_length=100,
        blank=True,
        null=True,
    )

    contract_date = models.DateField(
        blank=True,
        null=True,
    )

    contract_cost = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        blank=True,
        null=True,
    )

    status = models.CharField(
        max_length=20,
        choices=LicenseStatus.choices,
        default=LicenseStatus.DRAFT,
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:

        ordering = ["-created_at"]

    def __str__(self):

        return f"{self.facility}"



    
class LicenseAttachmentType(models.TextChoices):

    LETTER = "LETTER", _("Letter")

    COMMITMENT = "COMMITMENT", _("Commitment")

    PERMIT = "PERMIT", _("Permit")

    INQUIRY = "INQUIRY", _("DSRS Inquiry")

    CONTRACT = "CONTRACT", _("Contract")

    OTHER = "OTHER", _("Other")



class LicenseAttachment(models.Model):

    license = models.ForeignKey(
        LicenseRequest,
        on_delete=models.CASCADE,
        related_name="attachments",
    )

    attachment_type = models.CharField(
        _("Attachment Type"),
        max_length=20,
        choices=LicenseAttachmentType.choices,
    )

    file = models.FileField(
        _("File"),
        upload_to=license_attachment_path,
    )

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
    )

    uploaded_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:

        ordering = ["attachment_type"]

    def __str__(self):

        return f"{self.license} - {self.get_attachment_type_display()}"







class LicenseSource(models.Model):

    license = models.ForeignKey(
        LicenseRequest,
        on_delete=models.CASCADE,
        related_name="sources",
        verbose_name=_("License"),
    )

    nuclide = models.ForeignKey(
        Nuclides,
        on_delete=models.PROTECT,
        verbose_name=_("Nuclide"),
    )

    serial_number = models.CharField(
        _("Serial Number"),
        max_length=150,
        blank=True,
    )

    activity = models.DecimalField(
        _("Activity"),
        max_digits=15,
        decimal_places=3,
        null=True,
        blank=True,
    )

    activity_unit = models.CharField(
        _("Activity Unit"),
        max_length=20,
        choices=ActivityUnit.choices,
        default=ActivityUnit.mCi,
    )

    activity_date = models.DateField(
        _("Activity Date"),
        null=True,
        blank=True,
    )

    notes = models.TextField(
        _("Notes"),
        blank=True,
    )

    created_dsrs = models.ForeignKey(
        "dashboard.DSRS",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="license_sources",
    )

    class Meta:

        ordering = [

            "id",

        ]

        verbose_name = _("Requested Source")

        verbose_name_plural = _("Requested Sources")

    def __str__(self):

        return f"{self.nuclide}"