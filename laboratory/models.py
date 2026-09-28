import math

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from facilities.models import FacilityModel
from reference.models import Nuclides
from waste.models import WasteBatch

LN2 = math.log(2)


class SampleStage(models.TextChoices):
    RECEIPT = "RECEIPT", _("Receipt")
    TREATMENT = "TREATMENT", _("Treatment")
    RELEASE = "RELEASE", _("Release")
    SOLIDIFICATION = "SOLIDIFICATION", _("Solidification")


class SampleStatus(models.TextChoices):
    COLLECTED = "COLLECTED", _("Collected")
    SENT_TO_LAB = "SENT_TO_LAB", _("Sent To Lab")
    RECEIVED_BY_LAB = "RECEIVED_BY_LAB", _("Received By Lab")
    IN_ANALYSIS = "IN_ANALYSIS", _("In Analysis")
    COMPLETED = "COMPLETED", _("Completed")
    REJECTED = "REJECTED", _("Rejected")


class RadiationType(models.TextChoices):
    ALPHA = "ALPHA", _("Alpha")
    BETA = "BETA", _("Beta")
    GAMMA = "GAMMA", _("Gamma")


class CounterType(models.TextChoices):
    ALPHABETA = "ALPHABETA", _("Gas proportional detector")
    HPGE = "HPGE", _("Gamma spectrometry / HPGe")


# =====================================================================
# APPROVAL WORKFLOW CHOICES — shared by both report types. The 3rd role
# is ONE signature slot that either Operations Manager or Operations
# Control Manager can fill (confirmed group-OR) — enforced via the
# accounts app's ViewPermission (grant both groups on the sign URL),
# not hardcoded here.
# =====================================================================

class LabApprovalRole(models.TextChoices):
    ANALYST = "ANALYST", _("Analysis Lab Expert")
    LAB_MANAGER = "LAB_MANAGER", _("Lab Manager")
    OPS_MANAGER = "OPS_MANAGER", _("Operations / Operations Control Manager")


class LabApprovalStatus(models.TextChoices):
    PENDING = "PENDING", _("Pending")
    APPROVED = "APPROVED", _("Approved")
    REJECTED = "REJECTED", _("Rejected")


class Sample(models.Model):

    sample_id = models.CharField(_("Sample ID"), max_length=50, unique=True)

    batch = models.ForeignKey(
        WasteBatch, verbose_name=_("Waste Batch"), on_delete=models.PROTECT,
        related_name="samples", null=True, blank=True,
    )
    applicant_name = models.CharField(
        _("Applicant name"), max_length=255, blank=True, null=True,
        help_text=_("Name of the applicant company or unit."),
    )
    sample_type = models.CharField(_("Sample type"), max_length=50, blank=True, null=True)
    description = models.CharField(
        _("Description"), max_length=255, blank=True, null=True,
        help_text=_("For standalone samples not linked to a waste batch."),
    )
    sample_stage = models.CharField(_("Sample Stage"), max_length=20, choices=SampleStage.choices)
    analysis_type = models.CharField(
        _("Analysis type"), max_length=30, choices=CounterType.choices, blank=True, default="",
        help_text=_("Which detector this sample will be counted on — decides which report it gets."),
    )
    sampling_date = models.DateTimeField(_("Sampling Date"))
    sampling_location = models.CharField(_("Sampling location"), max_length=50, blank=True, null=True)
    sample_mass_kg = models.DecimalField(
        _("Sample Mass (kg)"), max_digits=10, decimal_places=5, blank=True, null=True
    )
    sample_volume_ml = models.DecimalField(
        _("Sample Volume (ml)"), max_digits=12, decimal_places=3, null=True, blank=True
    )
    urgent = models.BooleanField(_("Urgent"), default=False)
    status = models.CharField(
        _("Status"), max_length=20, choices=SampleStatus.choices, default=SampleStatus.COLLECTED
    )
    collected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name=_("Collected By"),
        on_delete=models.SET_NULL, null=True, related_name="samples_collected",
    )
    remarks = models.TextField(_("Remarks"), blank=True, null=True)
    sample_code_barcode = models.CharField(
        _("Barcode"), max_length=100, unique=True, blank=True, null=True
    )
    sent_to_lab_date = models.DateField(_("Sent To Lab Date"), blank=True, null=True)
    lab_received_date = models.DateField(_("Lab Received Date"), blank=True, null=True)
    lab_comments = models.TextField(_("Lab Comments"), blank=True, null=True)
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    rejected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name=_("Rejected By"), on_delete=models.SET_NULL,
        null=True, blank=True, related_name="samples_rejected",
    )
    rejected_at = models.DateTimeField(_("Rejected At"), null=True, blank=True)
    rejection_reason = models.TextField(_("Rejection Reason"), blank=True, default="")
    # False = the collector hasn't seen the rejection yet (drives the notification).
    rejection_seen = models.BooleanField(default=True)
    class Meta:
        ordering = ["-urgent", "sampling_date"]
        verbose_name = _("Sample")
        verbose_name_plural = _("Samples")

    def __str__(self):
        return self.sample_id

    def send_to_lab(self, performed_by=None):
        self.status = SampleStatus.SENT_TO_LAB
        self.sent_to_lab_date = timezone.now().date()
        self.save(update_fields=["status", "sent_to_lab_date"])


# =====================================================================
# ALPHA/BETA COUNTING RUN — groups up to 12 samples counted together in
# ONE gas-proportional-counter session. This is what the printed
# "Gross Alpha & Beta" form actually reports on: one shared MDA α/β,
# one shared counting duration/date, one shared 3-signature block —
# NOT one report per Analysis like the Gamma form is.
# =====================================================================

MAX_SAMPLES_PER_COUNTING_RUN = 12


class AlphaBetaCountingRun(models.Model):

    run_id = models.CharField(_("Run ID"), max_length=50, unique=True)

    run_date = models.DateField(_("Counting Date"))

    counting_duration_seconds = models.PositiveIntegerField(
        _("Counting Duration (seconds)"), null=True, blank=True,
    )

    # NOTE: the printed form's MDA fields are explicitly labeled "(mBq)"
    # — different unit than the Gamma form's Bq/Kg figures. Whatever
    # value is entered here is written into the report AS-IS; make sure
    # it's genuinely in mBq when entering it, this app does no unit
    # conversion for these two fields.
    alpha_mda_mbq = models.DecimalField(
        _("MDA Alpha (mBq)"), max_digits=20, decimal_places=5, null=True, blank=True,
    )
    beta_mda_mbq = models.DecimalField(
        _("MDA Beta (mBq)"), max_digits=20, decimal_places=5, null=True, blank=True,
    )

    notes = models.TextField(_("Notes"), blank=True, null=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name=_("Created By"),
        on_delete=models.SET_NULL, null=True, related_name="counting_runs_created",
    )
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)

    approved = models.BooleanField(_("Approved"), default=False)

    class Meta:
        ordering = ["-run_date", "-id"]
        verbose_name = _("Alpha/Beta Counting Run")
        verbose_name_plural = _("Alpha/Beta Counting Runs")

    def __str__(self):
        return self.run_id

    @property
    def sample_count(self):
        return self.analyses.count()


class Analysis(models.Model):

    sample = models.OneToOneField(
        Sample, verbose_name=_("Sample"), on_delete=models.CASCADE, related_name="analysis"
    )

    # Only set for detector_type=ALPHABETA analyses that have been added
    # to a shared counting run. NULL for Gamma analyses (each of those
    # generates its own standalone report) and for Alpha/Beta analyses
    # not yet grouped into a run.
    counting_run = models.ForeignKey(
        AlphaBetaCountingRun, verbose_name=_("Counting Run"),
        on_delete=models.SET_NULL, null=True, blank=True, related_name="analyses",
    )

    detector_type = models.CharField(_("Detector Type"), max_length=30, choices=CounterType.choices)
    analysis_date = models.DateField(_("Analysis Date"))
    counting_duration_seconds = models.PositiveIntegerField(
        _("Counting Duration (seconds)"), null=True, blank=True,
    )
    total_alpha = models.DecimalField(_("Total Alpha (Bq)"), max_digits=20, decimal_places=5, blank=True, null=True)
    total_beta = models.DecimalField(_("Total Beta (Bq)"), max_digits=20, decimal_places=5, blank=True, null=True)
    alpha_uncertainty = models.DecimalField(_("Alpha uncertainty ±2s"), max_digits=20, decimal_places=5, null=True, blank=True)
    beta_uncertainty = models.DecimalField(_("Beta uncertainty ±2s"), max_digits=20, decimal_places=5, null=True, blank=True)
    alpha_mda = models.DecimalField(_("MDA Alpha"), max_digits=20, decimal_places=5, null=True, blank=True)
    beta_mda = models.DecimalField(_("MDA Beta"), max_digits=20, decimal_places=5, null=True, blank=True)

    analyst = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=_("Analyst"), on_delete=models.SET_NULL, null=True)

    approved = models.BooleanField(_("Approved"), default=False)
    is_latest = models.BooleanField(_("Is Latest"), default=True)

    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name=_("Reviewed By"),
        on_delete=models.SET_NULL, null=True, blank=True, related_name="reviewed_analyses",
    )
    review_date = models.DateField(_("Review Date"), blank=True, null=True)
    analysis_notes = models.TextField(_("Analysis Notes"), blank=True, null=True)
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)

    class Meta:
        ordering = ["-analysis_date", "-created_at"]
        verbose_name = _("Analysis")
        verbose_name_plural = _("Analyses")

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

        if self.sample.batch_id:
            Analysis.objects.filter(
                sample__batch_id=self.sample.batch_id
            ).exclude(pk=self.pk).update(is_latest=False)

            if not self.is_latest:
                self.is_latest = True
                super().save(update_fields=["is_latest"])

    def __str__(self):
        return f"Analysis - {self.sample.sample_id}"


class NuclideActivity(models.Model):

    analysis = models.ForeignKey(
        Analysis, verbose_name=_("Analysis"), on_delete=models.CASCADE, related_name="nuclide_activities"
    )
    radionuclide = models.ForeignKey(Nuclides, verbose_name=_("Radionuclide"), on_delete=models.PROTECT)
    radiation_type = models.CharField(
        _("Radiation Type"), max_length=10, choices=RadiationType.choices, default=RadiationType.GAMMA
    )
    activity_bq = models.DecimalField(_("Activity (Bq)"), max_digits=20, decimal_places=5)
    uncertainty_bq = models.DecimalField(_("Uncertainty (Bq)"), max_digits=20, decimal_places=5, blank=True, null=True)
    mda_bq = models.DecimalField(
        _("MDA (Bq)"), max_digits=20, decimal_places=5, blank=True, null=True,
        help_text=_("Minimum detectable activity."),
    )

    class Meta:
        unique_together = ("analysis", "radionuclide", "radiation_type")
        verbose_name = _("Nuclide Activity")
        verbose_name_plural = _("Nuclide Activities")

    def __str__(self):
        return f"{self.radionuclide} ({self.get_radiation_type_display()}) - {self.activity_bq}"

    def current_activity_bq(self, as_of=None):
        if not self.activity_bq or not self.radionuclide:
            return None
        half_life = self.radionuclide.half_life
        if not half_life:
            return float(self.activity_bq)
        as_of = as_of or timezone.now().date()
        elapsed_seconds = (as_of - self.analysis.analysis_date).days * 86400
        if elapsed_seconds <= 0:
            return float(self.activity_bq)
        return float(self.activity_bq) * math.exp(-LN2 * elapsed_seconds / half_life)

    def specific_activity_bq_per_kg(self, decay_corrected=False, as_of=None):
        """Used by the Gamma report — both its Bq/Kg columns are per unit
        MASS, so raw activity_bq needs dividing by the sample's mass.
        Returns None if the sample has no recorded mass (can't compute
        a specific activity without one)."""
        mass = self.analysis.sample.sample_mass_kg
        if not mass:
            return None
        raw = self.current_activity_bq(as_of=as_of) if decay_corrected else float(self.activity_bq)
        if raw is None:
            return None
        return raw / float(mass)


class LabAttachmentType(models.TextChoices):
    REPORT = "REPORT", _("Generated Report")
    SPECTRUM = "SPECTRUM", _("Spectrum")
    OTHER = "OTHER", _("Other")


class AnalysisAttachment(models.Model):
    """Dual-nullable-FK, same pattern as AnalysisApproval below — a
    Gamma report attaches to one Analysis; an Alpha/Beta report attaches
    to one AlphaBetaCountingRun instead. Exactly one of the two should
    be set (enforced in the views/services that create these, not at
    the DB level)."""

    analysis = models.ForeignKey(
        Analysis, related_name="attachments", on_delete=models.CASCADE, null=True, blank=True,
    )
    counting_run = models.ForeignKey(
        AlphaBetaCountingRun, related_name="attachments", on_delete=models.CASCADE, null=True, blank=True,
    )

    attachment_type = models.CharField(
        _("Attachment Type"), max_length=15, choices=LabAttachmentType.choices, default=LabAttachmentType.OTHER,
    )
    file = models.FileField(_("File"), upload_to="laboratory/attachments/")
    description = models.CharField(_("Description"), max_length=200, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    class Meta:

        constraints = [
            models.CheckConstraint(
                condition=(models.Q(analysis__isnull=False, counting_run__isnull=True)
                       | models.Q(analysis__isnull=True, counting_run__isnull=False)),
                name="attachment_exactly_one_target",
            )
        ]
    def __str__(self):
        target = self.analysis or self.counting_run
        return f"{self.get_attachment_type_display()} - {target}"


class AnalysisApproval(models.Model):
    """Dual-nullable-FK: an approval row attaches to EITHER one Analysis
    (Gamma report — one report per sample) OR one AlphaBetaCountingRun
    (Alpha/Beta report — one report per batch of up to 12 samples).
    Exactly one should be set per row; workflow.py always sets exactly
    one when creating these, never both."""

    analysis = models.ForeignKey(
        Analysis, related_name="approvals", on_delete=models.CASCADE, null=True, blank=True,
    )
    counting_run = models.ForeignKey(
        AlphaBetaCountingRun, related_name="approvals", on_delete=models.CASCADE, null=True, blank=True,
    )

    role = models.CharField(_("Role"), max_length=20, choices=LabApprovalRole.choices)
    order = models.PositiveSmallIntegerField(default=1)
    status = models.CharField(
        _("Status"), max_length=15, choices=LabApprovalStatus.choices, default=LabApprovalStatus.PENDING,
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    signed_date = models.DateField(null=True, blank=True)
    signature = models.ImageField(upload_to="laboratory/signatures/", null=True, blank=True)
    comments = models.TextField(_("Comments"), blank=True)

    class Meta:
        ordering = ["order"]
        verbose_name = _("Lab Approval")
        verbose_name_plural = _("Lab Approvals")
        constraints = [
            models.CheckConstraint(
                condition=(models.Q(analysis__isnull=False, counting_run__isnull=True)
                       | models.Q(analysis__isnull=True, counting_run__isnull=False)),
                name="approval_exactly_one_target",
            )
        ]

    def __str__(self):
        target = self.analysis or self.counting_run
        return f"{self.get_role_display()} - {target}"