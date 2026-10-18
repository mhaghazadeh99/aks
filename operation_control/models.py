from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords

from common.utils.fileValidator import validate_attachment   # same validator your waste app uses

from . import assessment, conf
from . import jalali_utils as ju

User = settings.AUTH_USER_MODEL


# ============================================================ shared bases
class TimeStamped(models.Model):
    created_at = models.DateTimeField(_("Created Date"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated Date"), auto_now=True)
    created_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+", verbose_name=_("Created By"),
    )

    class Meta:
        abstract = True


class Lookup(models.Model):
    """Admin-maintained pick-list entry."""
    name = models.CharField(_("Name"), max_length=150, unique=True)
    is_active = models.BooleanField(_("Active"), default=True)
    sort_order = models.PositiveSmallIntegerField(_("Sort order"), default=0)

    class Meta:
        abstract = True
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name


class Season(models.IntegerChoices):
    SPRING = 1, _("Spring")
    SUMMER = 2, _("Summer")
    AUTUMN = 3, _("Autumn")
    WINTER = 4, _("Winter")


class DoseUnit(models.TextChoices):
    USV = "USV", "µSv"
    MSV = "MSV", "mSv"


def to_msv(value, unit):
    value = Decimal(value)
    return value / Decimal(1000) if unit == DoseUnit.USV else value


# ============================================================ 1) CALIBRATION
class EquipmentApplication(Lookup):
    """e.g. 'Personnel dosimetry', 'Environmental gamma monitoring'."""
    is_personal_dosimetry = models.BooleanField(
        _("Is a personal (online) dosimeter"), default=False,
        help_text=_("Devices with this application can be picked in online dose records."),
    )

    class Meta(Lookup.Meta):
        verbose_name = _("Equipment application")
        verbose_name_plural = _("Equipment applications")


class Equipment(TimeStamped):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", _("Active")
        INACTIVE = "INACTIVE", _("Inactive")
        SENT_FOR_CALIBRATION = "SENT", _("Sent for calibration")
        ON_LOAN = "LOAN", _("On loan")

    class Center(models.TextChoices):
        TEHRAN = "TEHRAN", _("Tehran")
        KARAJ = "KARAJ", _("Karaj")
        ANARAK = "ANARAK", _("Anarak")

    class Label(models.TextChoices):
        CALIBRATED = "CALIBRATED", _("Calibrated")
        REJECTED = "REJECTED", _("Rejected")
        OUT_OF_SERVICE = "OUT_OF_SERVICE", _("Out of Service")
        CBU = "CBU", _("CBU")
        VERIFICATION = "VERIFICATION", _("Verification")

    class CalStatus(models.TextChoices):
        EXPIRED = "expired", _("Expired")
        DUE_SOON = "due_soon", _("Due soon")
        VALID = "valid", _("Valid")
        UNKNOWN = "unknown", _("No calibration date")

    name = models.CharField(_("Device name"), max_length=200)
    equipment_id = models.CharField(_("Equipment ID"), max_length=50, unique=True)
    model_name = models.CharField(_("Model"), max_length=120, blank=True)
    serial_number = models.CharField(_("Serial number"), max_length=120, blank=True)
    manufacturer = models.CharField(_("Manufacturer"), max_length=150, blank=True)
    application = models.ForeignKey(
        EquipmentApplication, null=True, blank=True, on_delete=models.PROTECT,
        related_name="equipment", verbose_name=_("Application"),
    )
    status = models.CharField(_("Status"), max_length=10, choices=Status.choices, default=Status.ACTIVE)
    loan_to = models.CharField(_("Loaned to"), max_length=150, blank=True)
    center = models.CharField(_("Center"), max_length=10, choices=Center.choices, blank=True)
    current_location = models.CharField(_("Current location"), max_length=200, blank=True)
    calibration_period_months = models.PositiveSmallIntegerField(_("Calibration period (months)"), default=12)
    current_label = models.CharField(_("Current label"), max_length=20, choices=Label.choices, blank=True)
    notes = models.TextField(_("Notes / action"), blank=True)

    # Derived from the newest CalibrationRecord (kept in the DB so lists can filter/sort on it).
    last_calibration_date = models.DateField(_("Last calibration"), null=True, blank=True, editable=False)
    due_date = models.DateField(_("Calibration due date"), null=True, blank=True, editable=False)

    history = HistoricalRecords()   # audit trail (who changed what, when)

    class Meta:
        ordering = ["equipment_id"]
        verbose_name = _("Equipment")
        verbose_name_plural = _("Equipment")

    def __str__(self):
        return f"{self.equipment_id} — {self.name}"

    # ---- calibration maths ----
    def save(self, *args, **kwargs):
        self.due_date = (
            ju.add_months(self.last_calibration_date, self.calibration_period_months)
            if self.last_calibration_date else None
        )
        super().save(*args, **kwargs)

    def refresh_calibration(self):
        latest = self.calibrations.order_by("-calibration_date", "-id").first()
        self.last_calibration_date = latest.calibration_date if latest else None
        self.save()

    @property
    def days_remaining(self):
        return ju.days_between(self.due_date, ju.today()) if self.due_date else None

    @property
    def calibration_status(self):
        days = self.days_remaining
        if days is None:
            return self.CalStatus.UNKNOWN
        if days < 0:
            return self.CalStatus.EXPIRED
        if days <= conf.CALIBRATION_WARNING_DAYS:
            return self.CalStatus.DUE_SOON
        return self.CalStatus.VALID

    @property
    def calibration_badge_class(self):
        return {
            self.CalStatus.EXPIRED: "bg-danger",
            self.CalStatus.DUE_SOON: "bg-warning text-dark",
            self.CalStatus.VALID: "bg-success",
        }.get(self.calibration_status, "bg-secondary")

    @property
    def latest_assessment(self):
        return self.assessments.order_by("-assessment_date", "-id").first()

    @property
    def last_calibration_display(self):
        return ju.display(self.last_calibration_date)

    @property
    def due_date_display(self):
        return ju.display(self.due_date)


class CalibrationRecord(TimeStamped):
    class Type(models.TextChoices):
        EXTERNAL = "EXTERNAL", _("External")
        INTERNAL_WITH_REF = "INT_REF", _("Internal — verification with calibrated sample")
        INTERNAL_NO_REF = "INT_NOREF", _("Internal — verification without calibrated sample")

    equipment = models.ForeignKey(Equipment, on_delete=models.CASCADE, related_name="calibrations",
                                  verbose_name=_("Equipment"))
    calibration_date = models.DateField(_("Calibration date"))
    certificate_number = models.CharField(_("Certificate number"), max_length=80, blank=True)
    laboratory = models.CharField(_("Laboratory / reference"), max_length=150, blank=True)
    calibration_type = models.CharField(_("Calibration type"), max_length=10, choices=Type.choices, blank=True)
    result_label = models.CharField(_("Label after calibration"), max_length=20,
                                    choices=Equipment.Label.choices, blank=True)
    attachment = models.FileField(_("Certificate file"), upload_to="operation_control/calibration/%Y/", blank=True)
    notes = models.TextField(_("Notes"), blank=True)

    history = HistoricalRecords()   # audit trail (who changed what, when)

    class Meta:
        ordering = ["-calibration_date", "-id"]
        verbose_name = _("Calibration record")
        verbose_name_plural = _("Calibration records")

    def __str__(self):
        return f"{self.equipment_id} @ {ju.display(self.calibration_date)}"

    @property
    def calibration_date_display(self):
        return ju.display(self.calibration_date)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.result_label:
            Equipment.objects.filter(pk=self.equipment_id).update(current_label=self.result_label)
        self.equipment.refresh_from_db()
        self.equipment.refresh_calibration()

    def delete(self, *args, **kwargs):
        equipment = self.equipment
        super().delete(*args, **kwargs)
        equipment.refresh_calibration()


class CalibrationAssessment(TimeStamped):
    """
    Calibration-interval assessment (OIML D10 scoring) - the "برگه ارزیابی" sheet, one row per assessment.
    Seven factors are answered; points, total, level, interval and the audit justification are computed
    from them on every save (see assessment.py). "Apply" copies the interval to the equipment.
    """

    class DeviceType(models.TextChoices):
        PORTABLE = "PORTABLE", _("Portable")
        FIXED = "FIXED", _("Fixed (non-portable)")

    class MakerRecommendation(models.TextChoices):
        SIX_MONTHS = "SIX_MONTHS", _("Six months")
        ONE_YEAR = "ONE_YEAR", _("One year")
        TWO_YEARS = "TWO_YEARS", _("Two years")
        THREE_YEARS = "THREE_YEARS", _("Three years")

    class Accuracy(models.TextChoices):
        LOW = "LOW", _("Low")
        MEDIUM = "MEDIUM", _("Medium")
        HIGH = "HIGH", _("High")
        VERY_HIGH = "VERY_HIGH", _("Very high")

    class Environment(models.TextChoices):
        VERY_GOOD = "VERY_GOOD", _("Very good")
        GOOD = "GOOD", _("Good")
        MEDIUM = "MEDIUM", _("Medium")
        BAD = "BAD", _("Bad")

    class Level(models.TextChoices):   # shared by importance / wear / cost (same four options)
        VERY_HIGH = "VERY_HIGH", _("Very high")
        HIGH = "HIGH", _("High")
        MEDIUM = "MEDIUM", _("Medium")
        LOW = "LOW", _("Low")

    equipment = models.ForeignKey(Equipment, on_delete=models.CASCADE, related_name="assessments",
                                  verbose_name=_("Equipment"))
    assessment_date = models.DateField(_("Assessment date"), default=ju.today)
    assessed_by = models.ForeignKey("RadiationWorker", null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="assessments", verbose_name=_("Assessed by"))

    device_type = models.CharField(_("Device type"), max_length=12, choices=DeviceType.choices)
    has_maker_recommendation = models.BooleanField(_("Manufacturer recommendation available"), default=False)
    maker_recommendation = models.CharField(_("Manufacturer recommendation"), max_length=12,
                                            choices=MakerRecommendation.choices, blank=True)
    accuracy = models.CharField(_("Measurement accuracy / MSA results"), max_length=12, choices=Accuracy.choices)
    environment = models.CharField(_("Environmental influence"), max_length=12, choices=Environment.choices)
    importance = models.CharField(_("Field of use and importance"), max_length=12, choices=Level.choices)
    wear = models.CharField(_("Wear / exposure to damaging factors"), max_length=12, choices=Level.choices)
    cost = models.CharField(_("Calibration cost"), max_length=12, choices=Level.choices)

    # computed on save
    score_device_type = models.PositiveSmallIntegerField(editable=False, default=0)
    score_maker = models.PositiveSmallIntegerField(editable=False, default=0)
    score_accuracy = models.PositiveSmallIntegerField(editable=False, default=0)
    score_environment = models.PositiveSmallIntegerField(editable=False, default=0)
    score_importance = models.PositiveSmallIntegerField(editable=False, default=0)
    score_wear = models.PositiveSmallIntegerField(editable=False, default=0)
    score_cost = models.PositiveSmallIntegerField(editable=False, default=0)
    total_score = models.PositiveSmallIntegerField(_("Total score"), editable=False, default=0)
    level = models.PositiveSmallIntegerField(_("Calibration level"), editable=False, default=1)
    interval_months = models.PositiveSmallIntegerField(_("Recommended interval (months)"), editable=False, default=6)
    justification = models.TextField(_("Justification for audit"), editable=False, blank=True)

    notes = models.TextField(_("Notes"), blank=True)
    applied_at = models.DateTimeField(_("Interval applied to equipment at"), null=True, blank=True, editable=False)

    history = HistoricalRecords()   # audit trail (who changed what, when)

    class Meta:
        ordering = ["-assessment_date", "-id"]
        verbose_name = _("Calibration assessment")
        verbose_name_plural = _("Calibration assessments")

    def __str__(self):
        return f"{self.equipment.equipment_id} — {self.total_score} ({self.interval_months} mo)"

    def save(self, *args, **kwargs):
        r = assessment.compute(
            self.has_maker_recommendation, self.device_type, self.maker_recommendation or None,
            self.accuracy, self.environment, self.importance, self.wear, self.cost)
        s = r["scores"]
        self.score_device_type, self.score_maker, self.score_accuracy = s["device_type"], s["maker"], s["accuracy"]
        self.score_environment, self.score_importance = s["environment"], s["importance"]
        self.score_wear, self.score_cost = s["wear"], s["cost"]
        self.total_score, self.level, self.interval_months = r["total"], r["level"], r["months"]
        self.justification = r["justification"]
        super().save(*args, **kwargs)

    @property
    def score_rows(self):
        """[(factor label, chosen answer, points)] for the detail page."""
        return [
            (_("Device type"), self.get_device_type_display(), self.score_device_type),
            (_("Manufacturer recommendation"),
             self.get_maker_recommendation_display() if self.has_maker_recommendation else _("Not available"),
             self.score_maker),
            (_("Measurement accuracy / MSA results"), self.get_accuracy_display(), self.score_accuracy),
            (_("Environmental influence"), self.get_environment_display(), self.score_environment),
            (_("Field of use and importance"), self.get_importance_display(), self.score_importance),
            (_("Wear / exposure to damaging factors"), self.get_wear_display(), self.score_wear),
            (_("Calibration cost"), self.get_cost_display(), self.score_cost),
        ]

    @property
    def is_applied(self):
        return self.equipment.calibration_period_months == self.interval_months

    def apply_to_equipment(self):
        eq = self.equipment
        eq.calibration_period_months = self.interval_months
        eq.save()                                   # recalculates the due date
        self.applied_at = timezone.now()
        self.save(update_fields=["applied_at"])


# ============================================================ 2) DOSIMETRY
class OperationType(Lookup):
    """Pick-list of operations (source receiving, waste conditioning, sampling, ...)."""

    class Meta(Lookup.Meta):
        verbose_name = _("Operation type")
        verbose_name_plural = _("Operation types")


class RadiationWorker(TimeStamped):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", _("Active")
        LEFT = "LEFT", _("Left")

    personnel_code = models.CharField(_("Personnel code"), max_length=30, unique=True)
    full_name = models.CharField(_("Full name"), max_length=150)
    unit = models.CharField(_("Unit / section"), max_length=120, blank=True)
    position = models.CharField(_("Position"), max_length=120, blank=True)
    status = models.CharField(_("Status"), max_length=10, choices=Status.choices, default=Status.ACTIVE)
    exit_date = models.DateField(_("Exit date"), null=True, blank=True)
    notes = models.TextField(_("Notes"), blank=True)

    history = HistoricalRecords()   # audit trail (who changed what, when)

    class Meta:
        ordering = ["full_name"]
        verbose_name = _("Radiation worker")
        verbose_name_plural = _("Radiation workers")

    def __str__(self):
        return f"{self.full_name} ({self.personnel_code})"


class EnvironmentalPoint(Lookup):
    """The environmental TLD check points."""
    location = models.CharField(_("Location"), max_length=200, blank=True)

    class Meta(Lookup.Meta):
        verbose_name = _("Environmental TLD point")
        verbose_name_plural = _("Environmental TLD points")


class TLDReport(TimeStamped):
    year = models.PositiveSmallIntegerField(_("Jalali year"))
    season = models.PositiveSmallIntegerField(_("Season"), choices=Season.choices)
    report_number = models.CharField(_("Report number"), max_length=60)
    received_date = models.DateField(_("Date received"), null=True, blank=True)
    attachment = models.FileField(_("Report file"), upload_to="operation_control/tld/%Y/", blank=True)
    notes = models.TextField(_("Notes"), blank=True)

    history = HistoricalRecords()   # audit trail (who changed what, when)

    class Meta:
        ordering = ["-year", "-season"]
        constraints = [models.UniqueConstraint(fields=["year", "season"], name="uniq_tld_report_per_season")]
        verbose_name = _("TLD report")
        verbose_name_plural = _("TLD reports")

    def __str__(self):
        return f"{self.report_number} ({self.year}/{self.get_season_display()})"


class TLDReading(TimeStamped):
    class Position(models.TextChoices):
        BODY = "BODY", _("Body")
        HAND = "HAND", _("Hand")
        ENVIRONMENT = "ENV", _("Environmental")

    report = models.ForeignKey(TLDReport, on_delete=models.CASCADE, related_name="readings", verbose_name=_("TLD report"))
    tld_code = models.CharField(_("TLD code"), max_length=40)
    position = models.CharField(_("Wearing position"), max_length=4, choices=Position.choices)
    worker = models.ForeignKey(RadiationWorker, null=True, blank=True, on_delete=models.PROTECT,
                               related_name="tld_readings", verbose_name=_("Worker"))
    env_point = models.ForeignKey(EnvironmentalPoint, null=True, blank=True, on_delete=models.PROTECT,
                                  related_name="tld_readings", verbose_name=_("Environmental point"))
    gamma_msv = models.DecimalField(_("Gamma dose (mSv)"), max_digits=12, decimal_places=4, null=True, blank=True)
    neutron_msv = models.DecimalField(_("Neutron dose (mSv)"), max_digits=12, decimal_places=4, null=True, blank=True)
    remarks = models.CharField(_("Remarks"), max_length=250, blank=True)

    history = HistoricalRecords()   # audit trail (who changed what, when)

    class Meta:
        ordering = ["report", "tld_code"]
        constraints = [
            models.UniqueConstraint(fields=["report", "tld_code"], name="uniq_tld_code_per_report"),
            # NOTE: on Django >= 5.1 you may rename `check=` to `condition=`.
            models.CheckConstraint(
                condition=(Q(worker__isnull=False, env_point__isnull=True)
                       | Q(worker__isnull=True, env_point__isnull=False)),
                name="tld_worker_xor_env_point",
            ),
        ]
        verbose_name = _("TLD reading")
        verbose_name_plural = _("TLD readings")

    def clean(self):
        is_env = self.position == self.Position.ENVIRONMENT
        if is_env and not self.env_point_id:
            raise ValidationError({"env_point": _("Pick the environmental point.")})
        if not is_env and not self.worker_id:
            raise ValidationError({"worker": _("Pick the worker.")})
        if is_env and self.worker_id or (not is_env and self.env_point_id):
            raise ValidationError(_("Use either a worker or an environmental point, not both."))

    def __str__(self):
        return f"{self.tld_code} ({self.report})"


class OperationDoseSession(TimeStamped):
    """One operation (header). Each exposed worker is a line in OnlineDoseRecord."""
    operation_type = models.ForeignKey(OperationType, on_delete=models.PROTECT, related_name="sessions",
                                       verbose_name=_("Operation"))
    performed_date = models.DateField(_("Operation date"))
    location = models.CharField(_("Location"), max_length=200, blank=True)
    duration_minutes = models.PositiveIntegerField(_("Operation duration (min)"), null=True, blank=True)
    description = models.TextField(_("Description"), blank=True)
    year = models.PositiveSmallIntegerField(editable=False, db_index=True)
    season = models.PositiveSmallIntegerField(editable=False, choices=Season.choices, db_index=True)

    history = HistoricalRecords()   # audit trail (who changed what, when)

    class Meta:
        ordering = ["-performed_date", "-id"]
        verbose_name = _("Operation dose session")
        verbose_name_plural = _("Operation dose sessions")

    def save(self, *args, **kwargs):
        jy, jm, _jd = ju.to_jalali(self.performed_date)   # reports group by Jalali year / season
        self.year, self.season = jy, ju.season_of_month(jm)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.operation_type} — {ju.display(self.performed_date)}"


class OnlineDoseRecord(models.Model):
    class DoseType(models.TextChoices):
        GAMMA = "GAMMA", _("Gamma")
        NEUTRON = "NEUTRON", _("Neutron")

    session = models.ForeignKey(OperationDoseSession, on_delete=models.CASCADE, related_name="records",
                                verbose_name=_("Operation"))
    worker = models.ForeignKey(RadiationWorker, on_delete=models.PROTECT, related_name="online_doses",
                               verbose_name=_("Worker"))
    device = models.ForeignKey(Equipment, on_delete=models.PROTECT, related_name="online_doses",
                               limit_choices_to={"application__is_personal_dosimetry": True},
                               verbose_name=_("Device"))
    dose_type = models.CharField(_("Dose type"), max_length=8, choices=DoseType.choices)
    dose_value = models.DecimalField(_("Recorded dose"), max_digits=12, decimal_places=4)
    dose_unit = models.CharField(_("Unit"), max_length=3, choices=DoseUnit.choices, default=DoseUnit.USV)
    exposure_minutes = models.PositiveIntegerField(_("Received over (min)"), null=True, blank=True)
    dose_msv = models.DecimalField(max_digits=14, decimal_places=6, editable=False)

    history = HistoricalRecords()   # audit trail (who changed what, when)

    class Meta:
        ordering = ["session", "worker"]
        verbose_name = _("Online dose record")
        verbose_name_plural = _("Online dose records")

    def save(self, *args, **kwargs):
        self.dose_msv = to_msv(self.dose_value, self.dose_unit)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.worker} — {self.dose_value} {self.get_dose_unit_display()}"


# ============================================================ 3) INSPECTION PLAN
class InspectionPlanYear(models.Model):
    year = models.PositiveSmallIntegerField(_("Jalali year"), unique=True)
    first_month = models.PositiveSmallIntegerField(
        _("First planned month"), default=2,
        help_text=_("Excel plan 1405 starts in Ordibehesht (2). 4 slots per month."),
    )

    class Meta:
        ordering = ["-year"]
        verbose_name = _("Inspection plan year")
        verbose_name_plural = _("Inspection plan years")

    @property
    def total_weeks(self):
        return (12 - self.first_month + 1) * 4

    def __str__(self):
        return str(self.year)


class InspectionItem(TimeStamped):
    class Period(models.IntegerChoices):
        WEEKLY = 1, _("Weekly")
        BIWEEKLY = 2, _("Every two weeks")
        MONTHLY = 4, _("Monthly")
        BIMONTHLY = 8, _("Every two months")
        QUARTERLY = 12, _("Every three months")
        SEMIANNUAL = 24, _("Every six months")

    title = models.CharField(_("Inspection title"), max_length=250)
    form_title = models.CharField(_("Checklist / form"), max_length=250, blank=True)
    form_code = models.CharField(_("Form code"), max_length=40, blank=True)
    area = models.CharField(_("Area"), max_length=200)
    responsible = models.ForeignKey("RadiationWorker", null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="responsible_inspections", verbose_name=_("Responsible"))
    period_weeks = models.PositiveSmallIntegerField(_("Period"), choices=Period.choices)
    is_active = models.BooleanField(_("Active"), default=True)

    history = HistoricalRecords()   # audit trail (who changed what, when)

    class Meta:
        ordering = ["title", "area"]
        constraints = [models.UniqueConstraint(fields=["title", "area"], name="uniq_inspection_title_area")]
        verbose_name = _("Inspection item")
        verbose_name_plural = _("Inspection items")

    def is_due_in_week(self, week_index: int) -> bool:
        return (week_index - 1) % self.period_weeks == 0

    def __str__(self):
        return f"{self.title} — {self.area}"


class InspectionRecord(TimeStamped):
    item = models.ForeignKey(InspectionItem, on_delete=models.CASCADE, related_name="records", verbose_name=_("Inspection"))
    plan_year = models.ForeignKey(InspectionPlanYear, on_delete=models.CASCADE, related_name="records",
                                  verbose_name=_("Plan year"))
    week_index = models.PositiveSmallIntegerField(_("Plan week"))
    is_done = models.BooleanField(_("Done"), default=True,
                                  help_text=_("Untick to only record a note / reason for delay."))
    done_date = models.DateField(_("Date done"), null=True, blank=True,
                                   help_text=_("Empty for rows imported from Excel (it only stored a tick)."))
    performed_by = models.ManyToManyField("RadiationWorker", blank=True, related_name="inspections_done",
                                          verbose_name=_("Done by"))
    note = models.TextField(_("Note / reason for delay"), blank=True)

    history = HistoricalRecords()   # audit trail (who changed what, when)

    class Meta:
        ordering = ["plan_year", "week_index"]
        constraints = [models.UniqueConstraint(fields=["item", "plan_year", "week_index"],
                                               name="uniq_inspection_record_per_week")]
        verbose_name = _("Inspection record")
        verbose_name_plural = _("Inspection records")

    def __str__(self):
        return f"{self.item} — {self.plan_year}/W{self.week_index}"


class InspectionAttachment(models.Model):
    """Evidence that an inspection was done and how (photos, filled forms, measurements ...)."""
    record = models.ForeignKey(InspectionRecord, on_delete=models.CASCADE, related_name="attachments",
                               verbose_name=_("Inspection record"))
    file = models.FileField(_("Evidence file"), upload_to="operation_control/inspection/%Y/",
                            validators=[validate_attachment])
    uploaded_at = models.DateTimeField(_("Uploaded At"), auto_now_add=True)
    uploaded_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["id"]
        verbose_name = _("Inspection attachment")
        verbose_name_plural = _("Inspection attachments")

    @property
    def filename(self):
        import os
        return os.path.basename(self.file.name)

    def __str__(self):
        return self.filename
