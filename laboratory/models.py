import math

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from facilities.models import FacilityModel
# FIX: your draft did `from dashboard.models import Nuclides`, but
# Nuclides lives in reference.models (dashboard only imports it from
# there). That import would have failed.
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

class Sample(models.Model):

    sample_id = models.CharField(_("Sample ID"), max_length=50, unique=True)

    # NULLABLE so samples can exist WITHOUT a waste batch — per your
    # requirement to create standalone samples (e.g. a smear, an
    # environmental or incoming sample) that aren't tied to received
    # waste. A batch-linked sample still drives that batch's activity
    # figures via WasteBatch.latest_analysis.
    batch = models.ForeignKey(
        WasteBatch,
        verbose_name=_("Waste Batch"),
        on_delete=models.CASCADE,
        related_name="samples",
        null=True,
        blank=True,
    )
    applicant_name = models.CharField(_("Applicant name"),max_length=255, blank=True, null=True,
        help_text=_("Name of the applicant company or unit."), )
    
    sample_type = models.CharField(_("Sample type"),max_length=50, blank=True, null=True, )
    

    # Only meaningful for standalone samples; batch-linked ones describe
    # themselves through the batch.
    description = models.CharField(
        _("Description"), max_length=255, blank=True, null=True,
        help_text=_("For standalone samples not linked to a waste batch."),
    )

    sample_stage = models.CharField(_("Sample Stage"), max_length=20, choices=SampleStage.choices)
    sampling_date = models.DateTimeField(_("Sampling Date"))
    sampling_location = models.CharField(_("Sampling location"),max_length=50, blank=True, null=True, )
    sample_mass_kg = models.DecimalField(
        _("Sample Mass (kg)"), max_digits=10, decimal_places=5, blank=True, null=True
    )
    sample_volume_ml = models.DecimalField(
        _("Sample Volume (ml)"),
        max_digits=12,
        decimal_places=3,
        null=True,
        blank=True
    )

    urgent = models.BooleanField(_("Urgent"), default=False)

    # Default changed to COLLECTED: a sample is created when it's taken,
    # and only becomes SENT_TO_LAB when someone actually sends it (the
    # "send to analysis" action). Defaulting straight to SENT_TO_LAB
    # would make that action meaningless.
    status = models.CharField(
        _("Status"), max_length=20, choices=SampleStatus.choices, default=SampleStatus.COLLECTED
    )

    collected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("Collected By"),
        on_delete=models.SET_NULL,
        null=True,
        related_name="samples_collected",
    )

    remarks = models.TextField(_("Remarks"), blank=True, null=True)

    sample_code_barcode = models.CharField(
        _("Barcode"), max_length=100, unique=True, blank=True, null=True
    )

    sent_to_lab_date = models.DateField(_("Sent To Lab Date"), blank=True, null=True)
    lab_received_date = models.DateField(_("Lab Received Date"), blank=True, null=True)
    lab_comments = models.TextField(_("Lab Comments"), blank=True, null=True)

    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)

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


class Analysis(models.Model):

    sample = models.OneToOneField(
        Sample, verbose_name=_("Sample"), on_delete=models.CASCADE, related_name="analysis"
    )
    

    detector_type = models.CharField(
        _("Detector Type"),
        max_length=30,
        choices=CounterType.choices
    )
    analysis_date = models.DateField(_("Analysis Date"))
    counting_duration_seconds = models.PositiveIntegerField(
        _("Counting Duration (seconds)"),
        null=True,
        blank=True
    )
    # Gross alpha/beta totals stay here (that's how they're measured —
    # one number for the whole sample). Per-NUCLIDE alpha/beta/gamma
    # results live in NuclideActivity below.
    total_alpha = models.DecimalField(
        _("Total Alpha (Bq)"), max_digits=20, decimal_places=5, blank=True, null=True
    )
    total_beta = models.DecimalField(
        _("Total Beta (Bq)"), max_digits=20, decimal_places=5, blank=True, null=True
    )

    alpha_uncertainty = models.DecimalField(
        _("Alpha uncertainty ±2s"),
        max_digits=20,
        decimal_places=5,
        null=True,
        blank=True
    )

    beta_uncertainty = models.DecimalField(
        _("Beta uncertainty ±2s"),
        max_digits=20,
        decimal_places=5,
        null=True,
        blank=True
    )

    alpha_mda = models.DecimalField(
        _("MDA Alpha"),
        max_digits=20,
        decimal_places=5,
        null=True,
        blank=True
    )

    beta_mda = models.DecimalField(
        _("MDA Beta"),
        max_digits=20,
        decimal_places=5,
        null=True,
        blank=True
    )

    analyst = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name=_("Analyst"), on_delete=models.SET_NULL, null=True,
    )

    approved = models.BooleanField(_("Approved"), default=False)
    is_latest = models.BooleanField(_("Is Latest"), default=True)

    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("Reviewed By"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_analyses",
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

        # Only batch-linked analyses compete for "latest" — standalone
        # samples have no batch to be the latest OF. Your draft's version
        # would crash on a batch-less sample (self.sample.batch is None,
        # and filtering sample__batch=None would wrongly match every
        # other standalone analysis).
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
    """
    Replaces your GammaActivity: same idea, but covers alpha and beta
    per-nuclide results too (via radiation_type), since you said you
    need "alpha beta gamma (different nuclides) activity" — gamma-only
    couldn't express that.
    """

    analysis = models.ForeignKey(
        Analysis, verbose_name=_("Analysis"), on_delete=models.CASCADE, related_name="nuclide_activities"
    )

    radionuclide = models.ForeignKey(Nuclides, verbose_name=_("Radionuclide"), on_delete=models.PROTECT)

    radiation_type = models.CharField(
        _("Radiation Type"), max_length=10, choices=RadiationType.choices, default=RadiationType.GAMMA
    )

    activity_bq = models.DecimalField(_("Activity (Bq)"), max_digits=20, decimal_places=5)

    uncertainty_bq = models.DecimalField(
        _("Uncertainty (Bq)"), max_digits=20, decimal_places=5, blank=True, null=True
    )
    mda_bq = models.DecimalField(
        _("MDA (Bq)"), max_digits=20, decimal_places=5, blank=True, null=True,
        help_text=_("Minimum detectable activity."),
    )

    class Meta:
        # Was unique_together ('analysis','radionuclide') — now includes
        # radiation_type, since the same nuclide can legitimately be
        # reported under more than one radiation type.
        unique_together = ("analysis", "radionuclide", "radiation_type")
        verbose_name = _("Nuclide Activity")
        verbose_name_plural = _("Nuclide Activities")

    def __str__(self):
        return f"{self.radionuclide} ({self.get_radiation_type_display()}) - {self.activity_bq}"

    def current_activity_bq(self, as_of=None):
        """Decay-corrects this measurement from the analysis date to
        `as_of` (default today), same formula as DSRS.current_activity_bq."""
        if not self.activity_bq or not self.radionuclide:
            return None

        half_life = self.radionuclide.half_life  # seconds
        if not half_life:
            return float(self.activity_bq)

        as_of = as_of or timezone.now().date()
        elapsed_seconds = (as_of - self.analysis.analysis_date).days * 86400
        if elapsed_seconds <= 0:
            return float(self.activity_bq)

        return float(self.activity_bq) * math.exp(-LN2 * elapsed_seconds / half_life)



class AnalysisAttachment(models.Model):

    analysis = models.ForeignKey(
        Analysis,
        related_name="attachments",
        on_delete=models.CASCADE
    )

    file = models.FileField(
        upload_to="laboratory/spectra/"
    )

    description = models.CharField(
        max_length=200,
        blank=True
    )



class AnalysisApproval(models.Model):

    analysis = models.ForeignKey(
        Analysis,
        related_name="approvals",
        on_delete=models.CASCADE
    )

    role = models.CharField(
        max_length=50
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True
    )

    signed_date = models.DateField(
        null=True
    )

    signature = models.ImageField(
        upload_to="laboratory/signatures/",
        null=True
    )