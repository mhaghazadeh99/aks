from django.db import models
from django.utils import timezone
import math
from common.utils.physics import LN2, mci_to_bq, bq_to_mci
from common.utils.fileValidator import validate_attachment
from contract.models import Contract,LicenseContract
from simple_history.models import HistoricalRecords
from reference.models import Nuclides
# Create your models here.
from facilities.models import Facility
from django.contrib.auth.models import User
from .choices import ActivityUnit


class OriginType(models.TextChoices):
    RECEIVED = "Received", "Received"
    HISTORICAL = "Historical", "Historical"
    SRS = "SRS", "SRS"

# -----------------------------
# CHANGED: Expanded lifecycle statuses
# -----------------------------
class SOURCE_STATUS(models.TextChoices):
    PURCHASED = "Purchased", "Purchased"      # New SRS
    IN_USE = "In Use", "In Use"               # Active at customer
    STORED = "Stored", "Stored"               # Returned to waste management
    REUSED = "Reused", "Reused"               # Sent out again
    RECYCLED = "Recycled", "Recycled"
    DISPOSED = "Disposed", "Disposed"         # Final state
    LOANED = "Loaned", "Loaned"

class SourceState(models.TextChoices):
    OK = "OK", "OK"
    CONTAMINATED = "Contaminated", "Contaminated"


class SourceForm(models.TextChoices):
    SEALED = "Solid", "Solid"
    LIQUID = "Liquid", "Liquid"


class SOURCE_TYPE(models.TextChoices):
    SRS = "SRS", "SRS"
    DSRS = "DSRS", "DSRS"
# -----------------------------


# ---- MAIN MODEL ----
class DSRS(models.Model):
    contract = models.ForeignKey(
        LicenseContract,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    @property
    def contract_number(self):
        return self.LicenseContract.contract_number if self.contract else ""
    created_from = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="children",
    )
    Source_Type = models.CharField( max_length=10, choices=SOURCE_TYPE.choices, default="DSRS")

    Sso_Code = models.CharField(max_length=12,null=True, blank=True)

    Facility = models.CharField(max_length=100, blank=True, null=True)

    Origin_Type = models.CharField(max_length=20, choices=OriginType.choices,null=True, blank=True)

    Date_received = models.DateField(blank=True, null=True)
    Origin_Facility = models.CharField(max_length=250,blank=True, null=True)
    is_divisible = models.BooleanField(default=False,)
    source_count = models.PositiveIntegerField(default=1,)
    available_count = models.PositiveIntegerField(default=1,)
    Location = models.CharField(max_length=20,blank=True, null=True)

    @property
    def Loc1(self):
        return self.Location[:3]

    @property
    def Loc2(self):
        return self.Location[3:7]

    @property
    def Num(self):
        return self.Location[7:]

    Status = models.CharField(max_length=15, choices=SOURCE_STATUS.choices,blank=True, null=True)
    Status_Date = models.DateField(blank=True, null=True)

    Responsible_Person = models.CharField(max_length=50,null=True, blank=True)

    Nuclide = models.ForeignKey(Nuclides, on_delete=models.SET_NULL, null=True, blank=True)
    activity_input = models.FloatField(null=True, blank=True)
    activity_unit = models.CharField(
        max_length=10,
        choices=ActivityUnit.choices,
        default='Bq',blank=True, null=True
    )

    # Stored value (normalized)

    

    Activity_reference_date = models.DateField(null=True, blank=True)

    serial_number = models.CharField(max_length=25,null=True, blank=True)

    Dose_rate_surface_uSv = models.FloatField(null=True, blank=True)
    Dose_rate_1m_uSv = models.FloatField(null=True, blank=True)
    Dose_rate_measurement_date = models.DateField(null=True, blank=True)

    source_state = models.CharField(max_length=15, choices=SourceState.choices, null=True, blank=True)

    contamination_bq_cm2 = models.FloatField(null=True, blank=True)

    Source_Physical_Form = models.CharField(max_length=10, choices=SourceForm.choices, null=True, blank=True)
    Source_Manufacturer = models.CharField(max_length=50, blank=True, null=True)
    Source_Model = models.CharField(max_length=20,null=True, blank=True)
    Source_Practice = models.CharField(max_length=20, blank=True, null=True)

    Device_Manufacturer = models.CharField(max_length=50, blank=True, null=True)
    Device_Model = models.CharField(max_length=50, blank=True, null=True)
    Device_Serial_Number = models.CharField(max_length=50, blank=True, null=True)

    Container_Type = models.CharField(max_length=25, blank=True, null=True)

    Dimension = models.CharField(max_length=20, blank=True, null=True)

    Attachments = models.FileField(
        upload_to="DSRS_Doc",
        validators=[validate_attachment],
        blank=True,
        null=True
    )

    Comment = models.CharField(max_length=255, blank=True, null=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    history = HistoricalRecords()
    initial_activity_bq = models.FloatField(null=True, blank=True)

    # -----------------------------
    # CURRENT ACTIVITY
    # -----------------------------

    def current_activity_bq(self):
        if not self.initial_activity_bq or not self.Nuclide or not self.Activity_reference_date:
            return None

        now = timezone.now().date()

        # time difference in seconds
        t = (now - self.Activity_reference_date).days * 86400

        hl = self.Nuclide.half_life  # MUST be in seconds

        if not hl:
            return None

        return self.initial_activity_bq * math.exp(-LN2 * t / hl)


    def current_activity_mci(self):
        val = self.current_activity_bq()
        return val / 3.7e7 if val else None
    @property
    def current_activity_mci_value(self):
        val = self.current_activity_mci()
        return round(val, 3) if val else None
    # -----------------------------
    # A/D VALUE
    # -----------------------------
    def a_over_d(self):
        if not self.Nuclide:
            return None

        current_bq = self.current_activity_bq()
        d = self.Nuclide.d_value_bq

        if not current_bq or not d:
            return None

        return current_bq / d

    # -----------------------------
    # CATEGORY (IAEA style)
    # -----------------------------
    def source_category(self):
        ratio = self.a_over_d()

        if ratio is None:
            return None

        if ratio >= 1000:
            return 1
        elif ratio >= 10:
            return 2
        elif ratio >= 1:
            return 3
        elif ratio >= 0.01:
            return 4
        else:
            return 5

    @property
    def category_value(self):
        return self.source_category()

    
    def save(self, *args, **kwargs):
        # if getattr(self, "_skip_contract", False):
        #     super().save(*args, **kwargs)
        #     return

        conversion = {
            'Bq': 1,
            'kBq': 1e3,
            'MBq': 1e6,
            'GBq': 1e9,
            'Ci': 3.7e10,
            'mCi': 3.7e7,
            'uCi': 3.7e4,
        }

        # -----------------------------
        # 1. CALCULATE INITIAL ACTIVITY
        # -----------------------------
        if self.activity_input is not None and self.activity_unit:
            self.initial_activity_bq = (
                float(self.activity_input)
                * conversion.get(self.activity_unit, 1)
            )

        super().save(*args, **kwargs)
        

    def __str__(self):
        return f"{self.Nuclide} (S.N: {self.serial_number})"


class DSRSImage(models.Model):
    dsrs = models.ForeignKey(
        "DSRS",
        on_delete=models.CASCADE,
        related_name="dsrs_images"
    )
    file = models.FileField(
        upload_to="dsrs_images/",
        validators=[validate_attachment],
        blank=True,
        null=True
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)


class SourceMovement(models.Model):
    
    source = models.ForeignKey(
        DSRS,
        on_delete=models.CASCADE,
    )

    movement_type = models.CharField(
        max_length=20,
        choices=[
            ("ISSUE", "Issue"),
            ("RETURN", "Return"),
            ("REUSE", "Reuse"),
            ("RECYCLE", "Recycle"),
            ("DISPOSAL", "Disposal"),
        ],
    )

    from_facility = models.ForeignKey(
        Facility,
        null=True,
        blank=True,
        related_name="+",
        on_delete=models.SET_NULL,
    )

    to_facility = models.ForeignKey(
        Facility,
        null=True,
        blank=True,
        related_name="+",
        on_delete=models.SET_NULL,
    )

    quantity = models.PositiveIntegerField(default=1)

    movement_date = models.DateField()

    contract = models.ForeignKey(
        LicenseContract,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )

    remarks = models.TextField(blank=True)


class HideShowFilterT(models.Model):
    parent = models.CharField(max_length=50)
    key = models.CharField(max_length=50)
    value = models.BooleanField(default=True)


class ModelFilterT(models.Model):
    parent = models.CharField(max_length=50)
    key = models.CharField(max_length=50)
    value = models.CharField(max_length=100)

