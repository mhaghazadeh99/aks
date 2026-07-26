from django.db import models
from django.utils import timezone
import math
from common.utils.physics import LN2, mci_to_bq, bq_to_mci
from common.utils.fileValidator import validate_attachment
from contract.models import Contract,LicenseContract
from simple_history.models import HistoricalRecords
from reference.models import Nuclides
# Create your models here.
from facilities.models import FacilityModel
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
    CONTROL = "Quality control", "Quality control"

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
        return self.contract.contract_number if self.contract else ""
    created_from = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="children",
    )
    Source_Type = models.CharField( max_length=10, choices=SOURCE_TYPE.choices, default="DSRS")

    Sso_Code = models.CharField(max_length=12,null=True, blank=True)

    Facility = models.ForeignKey(
                FacilityModel,
                null=True,
                blank=True,
                on_delete=models.SET_NULL,
                related_name="Source_Facility"
            )

    Origin_Type = models.CharField(max_length=20, choices=OriginType.choices,null=True, blank=True)

    Date_received = models.DateField(blank=True, null=True)
    

    is_divisible = models.BooleanField(default=False,)
    source_count = models.PositiveIntegerField(default=1,)
    available_count = models.PositiveIntegerField(default=1,)
    Location = models.CharField(max_length=20,blank=True, null=True)

    

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
    @property
    def last_movement(self):
        return self.movements.order_by("-movement_date", "-id").first()
    
    @property
    def current_facility(self):
        return self.Facility

    

    def register_movement(
        self,
        movement_type,
        to_facility,
        from_facility=None,
        contract=None,
        performed_by=None,
        quantity=None,
        remarks="",
        movement_date=None,
    ):

        if movement_date is None:
            movement_date = timezone.now().date()

        movement = self.movements.create(
            movement_type=movement_type,
            from_facility=from_facility,
            to_facility=to_facility,
            movement_date=movement_date,
            contract=contract,
            performed_by=performed_by,
            source_count=quantity or self.available_count,
            remarks=remarks,
        )

        self.Facility = to_facility
        self.Status_Date = movement_date
        self.Status = MOVEMENT_TO_STATUS.get(movement_type, self.Status)
        self.save(update_fields=["Facility", "Status_Date", "Status"])          # ADD "Status" HERE

        return movement
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



class MovementType(models.TextChoices):
    PURCHASE = "PURCHASE", "Purchase"
    RECEIVE = "RECEIVE", "Receive"
    ISSUE = "ISSUE", "Issue"
    RETURN = "RETURN", "Return"
    TRANSFER = "TRANSFER", "Transfer"
    SPLIT = "SPLIT", "Split"
    MERGE = "MERGE", "Merge"
    REUSE = "REUSE", "Reuse"
    RECYCLE = "RECYCLE", "Recycle"
    DISPOSAL = "DISPOSAL", "Disposal"
    LOAN = "LOAN", "Loan"
    QUALITY_CONTROL = "QUALITY_CONTROL", "Quality Control"


MOVEMENT_TO_STATUS = {
    MovementType.PURCHASE: SOURCE_STATUS.PURCHASED,
    MovementType.RECEIVE: SOURCE_STATUS.STORED,
    MovementType.ISSUE: SOURCE_STATUS.IN_USE,
    MovementType.RETURN: SOURCE_STATUS.STORED,
    MovementType.TRANSFER: SOURCE_STATUS.IN_USE,
    MovementType.REUSE: SOURCE_STATUS.REUSED,
    MovementType.RECYCLE: SOURCE_STATUS.RECYCLED,
    MovementType.DISPOSAL: SOURCE_STATUS.DISPOSED,
    MovementType.LOAN: SOURCE_STATUS.LOANED,
    MovementType.QUALITY_CONTROL: SOURCE_STATUS.CONTROL,
}


class SourceMovement(models.Model):
    
    source = models.ForeignKey(
        DSRS,
        on_delete=models.CASCADE, related_name="movements",
    )

    movement_type = models.CharField(max_length=20, choices=MovementType.choices, )

    from_facility = models.ForeignKey(
        FacilityModel,
        null=True,
        blank=True,
        related_name="+",
        on_delete=models.SET_NULL,
    )

    to_facility = models.ForeignKey(
        FacilityModel,
        null=True,
        blank=True,
        related_name="+",
        on_delete=models.SET_NULL,
    )

    source_count = models.PositiveIntegerField(default=1)


    movement_date = models.DateField()

    contract = models.ForeignKey(
        LicenseContract,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    performed_by = models.ForeignKey(
                User,
                on_delete=models.SET_NULL,
                null=True,
            )
    created_at = models.DateTimeField(auto_now_add=True)
    remarks = models.TextField(blank=True)
    attachment = models.FileField(
            upload_to="source_movements/",
            validators=[validate_attachment],
            blank=True,
            null=True,
        )
    class Meta:
        ordering = ["movement_date", "id"]

        indexes = [
            models.Index(fields=["source"]),
            models.Index(fields=["movement_date"]),
            models.Index(fields=["movement_type"]),
        ]
    
    def __str__(self):
        return (
            f"{self.get_movement_type_display()} "
            f"{self.from_facility} → {self.to_facility}"
        )

class HideShowFilterT(models.Model):
    parent = models.CharField(max_length=50)
    key = models.CharField(max_length=50)
    value = models.BooleanField(default=True)


class ModelFilterT(models.Model):
    parent = models.CharField(max_length=50)
    key = models.CharField(max_length=50)
    value = models.CharField(max_length=100)

