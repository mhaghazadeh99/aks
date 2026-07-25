from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _

from dashboard.choices import ActivityUnit   # or wherever your ActivityUnit choices are
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

    SPECIFICATION = "SPECIFICATION", _("Preparing Specification")

    WAITING_CREATOR = (
        "WAITING_CREATOR",
        _("Waiting Creator Signature"),
    )

    WAITING_MANAGER = (
        "WAITING_MANAGER",
        _("Waiting Manager Signature"),
    )

    WAITING_DEPUTY = (
        "WAITING_DEPUTY",
        _("Waiting Deputy Signature"),
    )

    CONTRACTS = (
        "CONTRACTS",
        _("Contracts"),
    )

    FINANCE = (
        "FINANCE",
        _("Finance"),
    )

    READY_TO_ISSUE = (
        "READY_TO_ISSUE",
        _("Ready To Issue"),
    )

    ISSUED = (
        "ISSUED",
        _("Issued"),
    )

    COMPLETED = (
        "COMPLETED",
        _("Completed"),
    )

    REJECTED = (
        "REJECTED",
        _("Rejected"),
    )

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

    

    status = models.CharField(
        max_length=20,
        choices=LicenseStatus.choices,
        default=LicenseStatus.DRAFT,
    )
    status_date = models.DateTimeField(
        null=True,
        blank=True,
    )
    specification_completed = models.BooleanField(default=False,)
    

    description = models.TextField(

        _("Description"),

        blank=True,)
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
    
    SPECIFICATION = "SPECIFICATION", _("Generated Specification")

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



class LicenseSourceType(models.TextChoices):

    NEW = "NEW", _("New Source")

    REUSED = "REUSED", _("Reused Source")

    RECYCLED = "RECYCLED", _("Recycled Source")



class LicenseSource(models.Model):

    license = models.ForeignKey(
        LicenseRequest,
        on_delete=models.CASCADE,
        related_name="sources",
        verbose_name=_("License"),
    )
    source_type = models.CharField(
            max_length=15,
            choices=LicenseSourceType.choices,
            default=LicenseSourceType.NEW,
        )
    source_dsrs = models.ForeignKey(
           "dashboard.DSRS",
            null=True,
            blank=True,
            on_delete=models.PROTECT,
            related_name="requested_in_licenses",
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

    specification_order = models.PositiveIntegerField(default=1,)
    description = models.TextField(max_length=50, blank=True, null= True)

    result_dsrs = models.ForeignKey(
        "dashboard.DSRS",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_by_licenses",
    )

    class Meta:

        ordering = [

            "id",

        ]

        verbose_name = _("Requested Source")

        verbose_name_plural = _("Requested Sources")

    def __str__(self):

        return f"{self.nuclide}"


    
class UserSignature(models.Model):

    user = models.OneToOneField(

        settings.AUTH_USER_MODEL,

        on_delete=models.CASCADE,

    )

    signature = models.ImageField(

        upload_to="signatures/",

    )

    title = models.CharField(

        max_length=150,

        blank=True,

    )

    updated_at = models.DateTimeField(

        auto_now=True,

    )





class LicenseApproval(models.Model):

    class ApprovalStep(models.TextChoices):

        CREATOR = "CREATOR", _("Creator")

        MANAGER = "MANAGER", _("Manager")

        DEPUTY = "DEPUTY", _("Deputy Manager")

        CONTRACTS = "CONTRACTS", _("Contracts")

    class ApprovalStatus(models.TextChoices):

        PENDING = "PENDING", _("Pending")

        APPROVED = "APPROVED", _("Approved")

        REJECTED = "REJECTED", _("Rejected")

    license = models.ForeignKey(

        LicenseRequest,

        related_name="approvals",

        on_delete=models.CASCADE,

    )

    step = models.CharField(

        max_length=30,

        choices=ApprovalStep.choices,

    )

    order = models.PositiveSmallIntegerField()

    approver = models.ForeignKey(

        settings.AUTH_USER_MODEL,

        on_delete=models.SET_NULL,

        null=True,

        blank=True,

    )

    status = models.CharField(

        max_length=20,

        choices=ApprovalStatus.choices,

        default=ApprovalStatus.PENDING,

    )

    approved_at = models.DateTimeField(

        null=True,

        blank=True,

    )

    comments = models.TextField(

        blank=True,

    )

    class Meta:

        ordering = ["order"]






