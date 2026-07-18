from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _

from reference.models import Nuclides
from facilities.models import Facility
from django.utils import timezone
# ============================================================
# Helpers
# ============================================================

def operation_attachment_path(instance, filename):

    folders = {

        "LETTER":
            "issues/letters",

        "COMMITMENT":
            "issues/commitments",

        "SOURCE_INQUIRY":
            "issues/source_inquiry",

        "REGULATORY_PERMIT":
            "issues/permits",

        "OTHER":
            "operations/other",

    }


    folder = folders.get(
        instance.attachment_type,
        "operations"
    )


    operation_number = (
        instance.operation.operation_number
        or "draft"
    )


    return (
        f"{folder}/"
        f"{operation_number}/"
        f"{filename}"
    )


# ============================================================
# Choices
# ============================================================

class OperationType(models.TextChoices):

    ISSUE_LICENCE = "ISSUE_LICENCE", _("Issue Licence")
    RECEIVE_SOURCE = "RECEIVE_SOURCE", _("Receive Source")
    RECEIVE_WASTE = "RECEIVE_WASTE", _("Receive Waste")
    SELL_SOURCE = "SELL_SOURCE", _("Sell Source")


class OperationStatus(models.TextChoices):

    DRAFT = "DRAFT", _("Draft")
    OCR_RUNNING = "OCR_RUNNING", _("OCR Running")
    WAITING_REVIEW = "WAITING_REVIEW", _("Waiting Review")
    WAITING_SIGNATURE = "WAITING_SIGNATURE", _("Waiting Signature")
    APPROVED = "APPROVED", _("Approved")
    REJECTED = "REJECTED", _("Rejected")
    COMPLETED = "COMPLETED", _("Completed")


class OCRStatus(models.TextChoices):

    PENDING = "PENDING", _("Pending")
    RUNNING = "RUNNING", _("Running")
    COMPLETED = "COMPLETED", _("Completed")
    FAILED = "FAILED", _("Failed")


class AttachmentType(models.TextChoices):

    LETTER = "LETTER", _("Letter")

    SOURCE_INQUIRY = (
        "SOURCE_INQUIRY",
        _("Radioactive Source Specification Inquiry"),
    )

    REGULATORY_PERMIT = (
        "REGULATORY_PERMIT",
        _("Regulatory Permit"),
    )

    COMMITMENT = (
        "COMMITMENT",
        _("Commitment Letter"),
    )

    OTHER = "OTHER", _("Other")


class SignatureRole(models.TextChoices):

    COORDINATOR = "COORDINATOR", _("Coordinator")

    OPERATION_MANAGER = (
        "OPERATION_MANAGER",
        _("Operation Manager"),
    )

    TECHNICAL_MANAGER = (
        "TECHNICAL_MANAGER",
        _("Technical Manager"),
    )

    DEPUTY_MANAGER = (
        "DEPUTY_MANAGER",
        _("Deputy Manager"),
    )

    DIRECTOR = "DIRECTOR", _("Director")


# ============================================================
# Operation
# ============================================================

class Operation(models.Model):

    operation_number = models.CharField(
        _("Operation Number"),
        max_length=30,
        unique=True,
        blank=True,
        help_text=_("Unique operation number."),
    )

    operation_type = models.CharField(
        _("Operation Type"),
        max_length=30,
        choices=OperationType.choices,
    )

    facility = models.ForeignKey(
        Facility,
        verbose_name=_("Facility"),
        related_name="operations",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )

    status = models.CharField(
        _("Status"),
        max_length=30,
        choices=OperationStatus.choices,
        default=OperationStatus.DRAFT,
    )

    notes = models.TextField(
        _("Notes"),
        blank=True,
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("Created By"),
        related_name="created_operations",
        on_delete=models.PROTECT,
    )

    created_at = models.DateTimeField(
        _("Created At"),
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        _("Updated At"),
        auto_now=True,
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Operation")
        verbose_name_plural = _("Operations")
    def save(self, *args, **kwargs):

        if not self.operation_number:

            year = timezone.now().year

            count = Operation.objects.filter(
                created_at__year=year
            ).count() + 1

            self.operation_number = (
                f"OP-{year}-{count:05d}"
            )

        super().save(*args, **kwargs)
    def __str__(self):
        return self.operation_number or str(self.pk)



# ============================================================
# Operation Source
# ============================================================

class OperationSource(models.Model):

    operation = models.ForeignKey(
        Operation,
        verbose_name=_("Operation"),
        related_name="sources",
        on_delete=models.CASCADE,
        help_text=_("Operation associated with this radioactive source."),
    )

    nuclides = models.ManyToManyField(
        Nuclides,
        verbose_name=_("Nuclides"),
        related_name="operation_sources",
        blank=True,
        help_text=_("One or more radionuclides contained in this source."),
    )

    source_model = models.CharField(
        _("Source Model"),
        max_length=200,
        blank=True,
        help_text=_("Manufacturer or source model."),
    )

    serial_number = models.CharField(
        _("Serial Number"),
        max_length=100,
        db_index=True,
        help_text=_("Manufacturer serial number."),
        blank=True,
    )

    activity = models.DecimalField(
        _("Activity"),
        max_digits=18,
        decimal_places=4,
        help_text=_("Source activity."),
         null=True,
    blank=True,
    )

    activity_unit = models.CharField(
        _("Activity Unit"),
        max_length=20,
        help_text=_("For example: Bq, kBq, MBq, GBq, Ci, mCi."),
         null=True,
    blank=True,
    )

    half_life = models.CharField(
        _("Half-life"),
        max_length=100,
        blank=True,
        help_text=_("Optional half-life information."),
    )

    remarks = models.TextField(
        _("Remarks"),
        blank=True,
    )

    class Meta:
        ordering = ["serial_number"]

        verbose_name = _("Operation Source")

        verbose_name_plural = _("Operation Sources")

        indexes = [
            models.Index(fields=["serial_number"]),
        ]

    def __str__(self):

        if self.source_model:
            return f"{self.source_model} ({self.serial_number})"

        return self.serial_number


# ============================================================
# Operation Attachment
# ============================================================

class OperationAttachment(models.Model):

    operation = models.ForeignKey(
        Operation,
        verbose_name=_("Operation"),
        related_name="attachments",
        on_delete=models.CASCADE,
        help_text=_("Operation associated with this attachment."),
    )

    attachment_type = models.CharField(
        _("Attachment Type"),
        max_length=40,
        choices=AttachmentType.choices,
    )

    title = models.CharField(
        _("Attachment Title"),
        max_length=200,
        blank=True,
        help_text=_(
            "A descriptive title for this document "
            "(for example: Licence Letter, Purchase Contract)."
        ),
    )

    file = models.FileField(
        _("File"),
        upload_to=operation_attachment_path,
        help_text=_("Upload document file."),
    )

    original_filename = models.CharField(
        _("Original Filename"),
        max_length=255,
        blank=True,
    )

    ocr_status = models.CharField(
        _("OCR Status"),
        max_length=20,
        choices=OCRStatus.choices,
        default=OCRStatus.PENDING,
    )

    ocr_confidence = models.DecimalField(
        _("OCR Confidence"),
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_(
            "OCR confidence percentage if available."
        ),
    )

    extracted_text = models.TextField(
        _("Extracted Text"),
        blank=True,
    )

    uploaded_at = models.DateTimeField(
        _("Uploaded At"),
        auto_now_add=True,
    )

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("Uploaded By"),
        related_name="uploaded_operation_attachments",
        on_delete=models.PROTECT,
    )


    class Meta:

        ordering = ["-uploaded_at"]

        verbose_name = _("Operation Attachment")

        verbose_name_plural = _("Operation Attachments")


    def __str__(self):

        if self.title:
            return self.title

        return self.get_attachment_type_display()



class OperationOCR(models.Model):

    operation = models.OneToOneField(
        Operation,
        related_name="ocr",
        on_delete=models.CASCADE,
    )

    raw_text = models.TextField(
        blank=True,
    )

    extracted_data = models.JSONField(
        default=dict,
        blank=True,
    )

    confidence = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
    )

    reviewed = models.BooleanField(
        default=False,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        verbose_name = _("Operation OCR")
        verbose_name_plural = _("Operation OCR")
# ============================================================
# Operation Signature
# ============================================================

class OperationSignature(models.Model):

    operation = models.ForeignKey(
        Operation,
        verbose_name=_("Operation"),
        related_name="signatures",
        on_delete=models.CASCADE,
        help_text=_(
            "Operation requiring this signature."
        ),
    )

    role = models.CharField(
        _("Signature Role"),
        max_length=30,
        choices=SignatureRole.choices,
        help_text=_(
            "Required approval role for this operation."
        ),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("Signer"),
        related_name="operation_signatures",
        on_delete=models.PROTECT,
        help_text=_(
            "User responsible for signing this operation."
        ),
    )

    signed = models.BooleanField(
        _("Signed"),
        default=False,
    )

    signed_at = models.DateTimeField(
        _("Signed At"),
        null=True,
        blank=True,
    )

    remarks = models.TextField(
        _("Remarks"),
        blank=True,
    )


    class Meta:

        ordering = ["role"]

        verbose_name = _("Operation Signature")

        verbose_name_plural = _("Operation Signatures")

        constraints = [

            models.UniqueConstraint(
                fields=[
                    "operation",
                    "role",
                ],
                name="unique_operation_signature_role",
            )

        ]


    def __str__(self):

        return (
            f"{self.get_role_display()} - "
            f"{self.operation.operation_number}"
        )