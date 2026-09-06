from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords

from facilities.models import FacilityModel
from reference.models import Nuclides
from dashboard.choices import ActivityUnit


# =====================================================================
# STATUS / CHOICES
# =====================================================================

class ReceiveStatus(models.TextChoices):

    DRAFT = "DRAFT", _("Draft")

    SPECIFICATION = "SPECIFICATION", _("Preparing Specification")

    WAITING_CREATOR = "WAITING_CREATOR", _("Waiting Creator/Coordinator Signature")

    WAITING_MANAGER_INPUT = "WAITING_MANAGER_INPUT", _("Waiting Manager Data Entry")

    WAITING_MANAGER = "WAITING_MANAGER", _("Waiting Operation Manager Signature")

    WAITING_CONTROL = "WAITING_CONTROL", _("Waiting Operation Control Manager Signature")

    WAITING_DEPUTY = "WAITING_DEPUTY", _("Waiting Deputy Manager Signature")

    CONTRACTS = "CONTRACTS", _("Contracts")

    WAITING_CEO = "WAITING_CEO", _("Waiting CEO Signature (Discount Requested)")

    FINANCE = "FINANCE", _("Finance")

    READY_TO_RECEIVE = "READY_TO_RECEIVE", _("Ready To Receive")

    RECEIVING = "RECEIVING", _("Receiving / Characterization")

    COMPLETED = "COMPLETED", _("Completed")

    REJECTED = "REJECTED", _("Rejected")


class ReceiveItemType(models.TextChoices):

    SOURCE = "SOURCE", _("Radioactive Source")
    WASTE = "WASTE", _("Radioactive Waste")


class YesNo(models.TextChoices):

    YES = "YES", _("Needed") if False else _("Yes")
    NO = "NO", _("No")


class VehicleType(models.TextChoices):

    GASOLINE = "GASOLINE", _("Gasoline")
    DIESEL = "DIESEL", _("Diesel")
    AIRPLANE = "AIRPLANE", _("Airplane")


class RouteDifficulty(models.TextChoices):

    NORMAL = "NORMAL", _("Normal")
    MEDIUM = "MEDIUM", _("Medium")
    HARD = "HARD", _("Hard")


class ReceiveAttachmentType(models.TextChoices):

    INQUIRY = "INQUIRY", _("DSRS Inquiry Letter")
    LETTER = "LETTER", _("Letter")
    SPECIFICATION = "SPECIFICATION", _("Generated Specification")
    SPECIFICATION_APPENDIX = "SPECIFICATION_APPENDIX", _("Specification Appendix")
    CONTRACT = "CONTRACT", _("Contract")
    PAYMENT = "PAYMENT", _("Payment Receipt")
    CHARACTERIZATION = "CHARACTERIZATION", _("Characterization Document")
    OTHER = "OTHER", _("Other")


def receive_attachment_path(instance, filename):
    import os
    return os.path.join(
        "receiving",
        str(instance.receive_request.id),
        instance.attachment_type.lower(),
        filename,
    )


# =====================================================================
# MAIN REQUEST
# =====================================================================

class ReceiveRequest(models.Model):
    """
    One 'Receive Source' case: starts from a DSRS Inquiry letter, ends
    with the delivered sources/waste sitting in stock as STORED DSRS
    records. Mirrors operations.LicenseRequest structurally.
    """

    facility = models.ForeignKey(
        FacilityModel,
        verbose_name=_("Delivering Facility"),
        on_delete=models.PROTECT,
        related_name="receive_requests",
    )

    # ---- Section 1 of the printed form (مشخصات مرکز تحویل دهنده) ----
    # name/address/postal_code/national_id/economic_code all come from
    # `facility` directly — not duplicated here.

    inquiry_letter_number = models.CharField(
        _("Inquiry Letter Number"),
        max_length=100,
        blank=True,
        null=True,
    )

    inquiry_letter_date = models.DateField(
        _("Inquiry Letter Date"),
        blank=True,
        null=True,
    )

    distance_to_tehran_km = models.DecimalField(
        _("Estimated Distance to Tehran Office (km)"),
        max_digits=8,
        decimal_places=2,
        blank=True,
        null=True,
    )

    status = models.CharField(
        _("Status"),
        max_length=25,
        choices=ReceiveStatus.choices,
        default=ReceiveStatus.DRAFT,
    )

    status_date = models.DateTimeField(
        _("Status Date"),
        null=True,
        blank=True,
    )

    specification_completed = models.BooleanField(
        _("Specification Completed"),
        default=False,
    )

    # ---- "Rest of the form" — filled by either manager, after sources
    # are added by the coordinator and before signatures begin. ----
    # The form has TWO separate dispatched-personnel blocks: one for the
    # pre-operation SITE VISIT, one for the actual RECEIVING OPERATION.
    # Only the operation block's counts are Control-Manager, add-only.

    pre_operation_visit_needed = models.BooleanField(
        _("Pre-Operation Visit Needed"),
        null=True,
        blank=True,
    )

    # -- Visit team (بازدید قبل از عملیات) --
    visit_expert_count = models.PositiveIntegerField(_("Visit: Experts"), null=True, blank=True)
    visit_technician_count = models.PositiveIntegerField(_("Visit: Technicians"), null=True, blank=True)
    visit_driver_count = models.PositiveIntegerField(_("Visit: Drivers"), null=True, blank=True)
    visit_mission_days = models.PositiveIntegerField(_("Visit: Mission Days"), null=True, blank=True)
    visit_vehicle_type = models.CharField(
        _("Visit: Vehicle Type"), max_length=10, choices=VehicleType.choices, blank=True, null=True,
    )

    # -- Operation team (مشخصات تکمیلی جهت انجام عملیات) --
    # Control Manager can only ever INCREASE these three counts (see
    # forms.AddOnlyIntegerField) — never remove/reduce.
    operation_expert_count = models.PositiveIntegerField(_("Operation: Experts"), default=0)
    operation_technician_count = models.PositiveIntegerField(_("Operation: Technicians"), default=0)
    operation_driver_count = models.PositiveIntegerField(_("Operation: Drivers"), default=0)

    operation_mission_days = models.PositiveIntegerField(_("Operation: Mission Days"), null=True, blank=True)
    operation_vehicle_type = models.CharField(
        _("Operation: Vehicle Type"), max_length=10, choices=VehicleType.choices, blank=True, null=True,
    )

    route_difficulty = models.CharField(
        _("Route Difficulty"),
        max_length=10,
        choices=RouteDifficulty.choices,
        blank=True,
        null=True,
    )

    accommodation_days = models.PositiveIntegerField(
        _("Accommodation Days"), null=True, blank=True,
    )

    food_cost_days = models.PositiveIntegerField(
        _("Food Cost Days"), null=True, blank=True,
    )

    peripheral_equipment = models.CharField(
        _("Peripheral Equipment Used"), max_length=255, blank=True, null=True,
    )

    other_costs = models.CharField(
        _("Other Costs"), max_length=255, blank=True, null=True,
        help_text=_("Also where the cost of an unmatched/no-license item gets folded in, per current policy."),
    )

    logistics_notes = models.TextField(
        _("Logistics Notes"), blank=True, null=True,
    )

    description = models.TextField(
        _("Description"),
        blank=True,
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("Created By"),
        on_delete=models.PROTECT,
        related_name="receive_requests_created",
    )

    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Receive Request")
        verbose_name_plural = _("Receive Requests")

    def __str__(self):
        return (
            self.inquiry_letter_number
            or _("Receive Request #%(id)s") % {"id": self.pk}
        )

    @property
    def ceo_required(self):
        """CEO only signs if the contract says a discount was requested."""
        return bool(
            hasattr(self, "contract")
            and self.contract
            and self.contract.discount_requested
        )


class ReceiveAttachment(models.Model):

    receive_request = models.ForeignKey(
        ReceiveRequest,
        on_delete=models.CASCADE,
        related_name="attachments",
    )

    attachment_type = models.CharField(
        _("Attachment Type"),
        max_length=25,
        choices=ReceiveAttachmentType.choices,
    )

    file = models.FileField(
        _("File"),
        upload_to=receive_attachment_path,
    )

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
    )

    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["attachment_type"]
        verbose_name = _("Receive Attachment")
        verbose_name_plural = _("Receive Attachments")

    def __str__(self):
        return f"{self.receive_request} - {self.get_attachment_type_display()}"


# =====================================================================
# SOURCES / WASTE TABLE (one row per line in "مشخصات چشمه‌ها" table)
# =====================================================================

class ReceiveSource(models.Model):
    """
    One row of the source/waste characterization table. Added by the
    Coordinator during SPECIFICATION. `nuclide` is required (matches the
    printed form's "نام چشمه/پسماند" column); `serial_number` is an
    app-only field — NOT printed on the form — used purely to check
    the DSRS inventory for an existing license contract.
    """

    receive_request = models.ForeignKey(
        ReceiveRequest,
        on_delete=models.CASCADE,
        related_name="sources",
        verbose_name=_("Receive Request"),
    )

    item_type = models.CharField(
        _("Item Type"),
        max_length=10,
        choices=ReceiveItemType.choices,
        default=ReceiveItemType.SOURCE,
    )

    nuclide = models.ForeignKey(
        Nuclides,
        verbose_name=_("Nuclide"),
        on_delete=models.PROTECT,
    )

    serial_number = models.CharField(
        _("Serial Number"),
        max_length=150,
        blank=True,
        null=True,
        help_text=_("Not printed on the form — used only to check for an existing license contract."),
    )

    average_activity_mci = models.DecimalField(
        _("Average Activity (mCi)"),
        max_digits=15,
        decimal_places=3,
        null=True,
        blank=True,
    )

    quantity = models.PositiveIntegerField(
        _("Quantity"),
        default=1,
    )

    half_life_display = models.CharField(
        _("Half-Life"),
        max_length=50,
        blank=True,
        null=True,
        help_text=_(
            "Auto-formatted from nuclide.half_life (stored in seconds) at "
            "save time — not user-entered. Kept as a display snapshot since "
            "the printed form shows it as static text."
        ),
    )

    needs_shield = models.BooleanField(_("Needs Shield"), null=True, blank=True)
    needs_burial = models.BooleanField(_("Needs Burial"), null=True, blank=True)

    storage_duration = models.CharField(
        _("Storage Duration"), max_length=100, blank=True, null=True,
    )

    sale_probability = models.CharField(
        _("Sale Probability"), max_length=100, blank=True, null=True,
    )

    description = models.TextField(
        _("Description"),
        blank=True,
        help_text=_("Auto-annotated with a license-contract match, if any (see below)."),
    )

    # ---- License-contract match (facility + nuclide + serial) ----
    # Populated by receiving.services.license_check when the coordinator
    # adds this row. `serial_matched_exactly=True` means an exact
    # facility+nuclide+serial hit was found automatically. If the serial
    # didn't match exactly but the facility does have contract(s) for this
    # nuclide, `matched_license_dsrs` records whichever candidate the
    # creator manually confirmed (or stays null if they picked "none of
    # these"). Either way this is informational only — it never sets
    # `DSRS.contract` on the newly-created record; see result_dsrs below.
    matched_license_dsrs = models.ForeignKey(
        "dashboard.DSRS",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name=_("Matched Existing Licensed Source"),
        help_text=_("Set automatically on an exact serial match, or manually confirmed by the creator on a fuzzy match."),
    )

    serial_matched_exactly = models.BooleanField(
        _("Serial Matched Exactly"),
        default=False,
    )

    specification_order = models.PositiveIntegerField(
        _("Specification Order"), default=1,
    )

    # Set once payment clears and the physical DSRS record is created.
    # Deliberately NOT linked to any LicenseContract (DSRS.contract stays
    # null) — a ReceiveContract, if any, is tracked separately above, and
    # per current policy a received item with no matched license simply
    # has its cost folded into ReceiveRequest.other_costs instead.
    result_dsrs = models.ForeignKey(
        "dashboard.DSRS",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_by_receive_sources",
    )

    class Meta:
        ordering = ["specification_order", "id"]
        verbose_name = _("Receive Source")
        verbose_name_plural = _("Receive Sources")

    def __str__(self):
        return str(self.nuclide) if self.nuclide else _("Source #%(id)s") % {"id": self.pk}


# =====================================================================
# CONTRACT (payment/financial + discount → CEO trigger)
# =====================================================================

class ReceiveContract(models.Model):

    receive_request = models.OneToOneField(
        ReceiveRequest,
        on_delete=models.PROTECT,
        related_name="contract",
    )

    contract_number = models.CharField(
        _("Contract Number"), max_length=100, blank=True, null=True,
    )

    contract_date = models.DateField(
        _("Contract Date"), blank=True, null=True,
    )

    contract_cost = models.DecimalField(
        _("Contract Cost"), max_digits=14, decimal_places=2, blank=True, null=True,
    )

    discount_requested = models.BooleanField(
        _("Discount Requested"),
        default=False,
        help_text=_("If checked, the request routes to the CEO for signature before Finance."),
    )

    discount_notes = models.TextField(
        _("Discount Notes"), blank=True, null=True,
    )

    send_to_financial = models.BooleanField(
        _("Send to Financial"), default=False,
    )

    contract_accountable = models.CharField(
        _("Contract Accountable"), max_length=100, blank=True, null=True,
    )

    amendment_notes = models.TextField(
        _("Amendment Notes"), blank=True, null=True,
    )

    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)

    history = HistoricalRecords()

    class Meta:
        verbose_name = _("Receive Contract")
        verbose_name_plural = _("Receive Contracts")

    def __str__(self):
        return self.contract_number or f"Receive Contract {self.pk}"


class ReceivePayment(models.Model):

    receive_request = models.OneToOneField(
        ReceiveRequest,
        verbose_name=_("Receive Request"),
        on_delete=models.PROTECT,
        related_name="payment",
    )

    payment_done = models.BooleanField(_("Payment Completed"), default=False)
    payment_date = models.DateField(_("Payment Date"), blank=True, null=True)

    amount_paid = models.DecimalField(
        _("Amount Paid"), max_digits=14, decimal_places=2, blank=True, null=True,
    )

    notes = models.TextField(_("Notes"), blank=True, null=True)

    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Receive Payment")
        verbose_name_plural = _("Receive Payments")

    def __str__(self):
        if self.receive_request.inquiry_letter_number:
            return self.receive_request.inquiry_letter_number
        return _("Payment %(id)s") % {"id": self.pk}


# =====================================================================
# APPROVALS / SIGNATURES
# =====================================================================

class ReceiveApproval(models.Model):

    class ApprovalStep(models.TextChoices):

        CREATOR = "CREATOR", _("Creator / Coordinator")
        MANAGER = "MANAGER", _("Operation Manager")
        CONTROL = "CONTROL", _("Operation Control Manager")
        DEPUTY = "DEPUTY", _("Deputy Manager")
        CEO = "CEO", _("CEO")

    class ApprovalStatus(models.TextChoices):

        PENDING = "PENDING", _("Pending")
        APPROVED = "APPROVED", _("Approved")
        REJECTED = "REJECTED", _("Rejected")
        NOT_REQUIRED = "NOT_REQUIRED", _("Not Required")

    receive_request = models.ForeignKey(
        ReceiveRequest,
        verbose_name=_("Receive Request"),
        related_name="approvals",
        on_delete=models.CASCADE,
    )

    step = models.CharField(
        _("Approval Step"), max_length=15, choices=ApprovalStep.choices,
    )

    order = models.PositiveSmallIntegerField()

    approver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("Approver"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    status = models.CharField(
        _("Status"), max_length=15,
        choices=ApprovalStatus.choices,
        default=ApprovalStatus.PENDING,
    )

    approved_at = models.DateTimeField(_("Approved At"), null=True, blank=True)
    comments = models.TextField(_("Comments"), blank=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["order"]
        verbose_name = _("Receive Approval")
        verbose_name_plural = _("Receive Approvals")

    def __str__(self):
        return f"{self.get_step_display()} - {self.get_status_display()}"
