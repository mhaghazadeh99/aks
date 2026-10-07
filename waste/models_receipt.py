"""
Receive-waste workflow models. Put these in waste/models.py (or import them there).

Flow
  DRAFT          user 1 registers the letter + the material/package lines
  MINUTES_READY  user 2 (received_by) enters the measurements, prints the form
  FINALIZED      signed scan uploaded -> WasteBatch records created (receipt_services.finalize_receipt)
  CANCELLED
"""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords

from common.utils.fileValidator import validate_attachment
from facilities.models import FacilityModel
from .models import MaterialType, PackageType, WasteType, WasteBatch
from reference.models import Nuclides

class ReceiptStatus(models.TextChoices):
    DRAFT = "DRAFT", _("Draft (data entry)")
    MINUTES_READY = "MINUTES_READY", _("Minutes ready - awaiting signed copy")
    FINALIZED = "FINALIZED", _("Finalized")
    CANCELLED = "CANCELLED", _("Cancelled")


class HalfLifeClass(models.TextChoices):          # liquid form rows
    LT100 = "LT100", _("Half-life < 100 days")
    GT100 = "GT100", _("Half-life > 100 days")


class WasteReceipt(models.Model):
    # ---------- step 1: registration (user 1) ----------
    waste_type = models.CharField(_("Waste Type"), max_length=10, choices=WasteType.choices)
    letter_number = models.CharField(_("Letter Number"), max_length=100)      # = request number on the form
    letter_date = models.DateField(_("Letter Date"))                          # = request date on the form
    letter_file = models.FileField(_("Letter"), upload_to="waste/receipts/letters/", validators=[validate_attachment])
    origin_facility = models.ForeignKey(FacilityModel, verbose_name=_("Delivering Facility"),
                                        on_delete=models.PROTECT, related_name="waste_deliveries")
    facility = models.ForeignKey(FacilityModel, verbose_name=_("Receiving Facility"),
                                 on_delete=models.PROTECT, related_name="waste_receipts")
    laboratory = models.CharField(_("Laboratory / Unit"), max_length=150, blank=True)
    received_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=_("Received By (responsible)"),
                                    on_delete=models.PROTECT, related_name="receipts_to_complete")
    description = models.TextField(_("Description"), blank=True)

    # ---------- step 2: minutes data (user 2) ----------
    delivery_date = models.DateField(_("Delivery Date"), null=True, blank=True)
    minutes_number = models.CharField(_("Minutes Number"), max_length=100, blank=True)
    minutes_date = models.DateField(_("Minutes Date"), null=True, blank=True)
    nuclides = models.ManyToManyField(Nuclides, verbose_name=_("Radionuclides Present"),
                                      blank=True, related_name="waste_receipts")
    waste_origin_place = models.CharField(_("Waste Generation Place"), max_length=255, blank=True)
    cabin_dose_uSv = models.DecimalField(_("Driver Cabin Dose (µSv/h)"), max_digits=10, decimal_places=3, null=True, blank=True)
    container_dose_uSv = models.DecimalField(_("Carrier Container Dose (µSv/h)"), max_digits=10, decimal_places=3, null=True, blank=True)
    deliverer_name = models.CharField(_("Deliverer Representative"), max_length=150, blank=True)
    deliverer_position = models.CharField(_("Deliverer Position"), max_length=150, blank=True)

    # ---------- step 3: signed copy + result ----------
    signed_minutes_file = models.FileField(_("Signed Minutes"), upload_to="waste/receipts/minutes/",
                                           validators=[validate_attachment], null=True, blank=True)
    status = models.CharField(_("Status"), max_length=20, choices=ReceiptStatus.choices, default=ReceiptStatus.DRAFT)
    finalized_at = models.DateTimeField(null=True, blank=True)
    finalized_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ("-created_at",)
        verbose_name = _("Waste Receipt")
        verbose_name_plural = _("Waste Receipts")
        permissions = [("manage_receipts", "Can complete and finalize any waste receipt")]
        constraints = [models.UniqueConstraint(fields=["origin_facility", "letter_number"], name="uniq_receipt_letter_per_origin")]

    def __str__(self):
        return f"{self.letter_number} ({self.origin_facility})"

    @property
    def nuclide_names(self):
        return ", ".join(n.name for n in self.nuclides.all())

    # The receiver is the responsible user; name and position come from their UserProfile.
    @property
    def receiver_name(self):
        u = self.received_by
        profile = getattr(u, "profile", None)          # None if the user has no profile
        return (profile.full_name if profile and profile.full_name else None) or u.get_full_name() or u.get_username()

    @property
    def receiver_position(self):
        profile = getattr(self.received_by, "profile", None)
        return (profile.position if profile and profile.position else "")

    @property
    def is_editable(self):
        return self.status in (ReceiptStatus.DRAFT, ReceiptStatus.MINUTES_READY)


class WasteReceiptLine(models.Model):
    """One (material, package type) combination in a delivery. This IS the many-to-many
    you described - but as a 'through' table, because each combination also needs its own
    mass/volume/dose. One finalized line -> one WasteBatch."""

    receipt = models.ForeignKey(WasteReceipt, on_delete=models.CASCADE, related_name="lines")
    material = models.CharField(_("Material"), max_length=30, choices=MaterialType.choices)
    package_type = models.CharField(_("Package Type"), max_length=20, choices=PackageType.choices)
    package_count = models.PositiveIntegerField(
        _("Number of Packages"), default=1, validators=[MinValueValidator(1)],
        help_text=_("Solid waste: one waste record is created per package."))

    # filled in step 2 (both solid and liquid)
    mass_kg = models.DecimalField(_("Mass (kg)"), max_digits=12, decimal_places=3, null=True, blank=True)
    volume_m3 = models.DecimalField(_("Volume (m³)"), max_digits=12, decimal_places=3, null=True, blank=True)
    surface_dose_uSv = models.DecimalField(_("Surface Dose (µSv/h)"), max_digits=12, decimal_places=3, null=True, blank=True)
    half_life = models.CharField(_("Half-life"), max_length=100, blank=True)          # free text, printed on solid form
    half_life_class = models.CharField(_("Half-life Class"), max_length=5, choices=HalfLifeClass.choices, blank=True)

    # liquid only. These are the figures DECLARED by the sender on the minutes;
    # WasteBatch never stores activity (it comes from lab analyses), so they stay here.
    alpha_bq_l = models.DecimalField(_("Alpha (Bq/L)"), max_digits=18, decimal_places=3, null=True, blank=True)
    beta_bq_l = models.DecimalField(_("Beta (Bq/L)"), max_digits=18, decimal_places=3, null=True, blank=True)
    gamma_bq_l = models.DecimalField(_("Gamma (Bq/L)"), max_digits=18, decimal_places=3, null=True, blank=True)
    ph = models.DecimalField(_("pH"), max_digits=5, decimal_places=2, null=True, blank=True)
    density = models.DecimalField(_("Density"), max_digits=10, decimal_places=4, null=True, blank=True)
    hardness = models.DecimalField(_("Hardness"), max_digits=10, decimal_places=3, null=True, blank=True)

    batch = models.OneToOneField(WasteBatch, null=True, blank=True, on_delete=models.PROTECT, related_name="receipt_line")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["receipt", "material", "package_type"], name="uniq_line_material_package")]

    def clean(self):
        liquid = self.receipt.waste_type == WasteType.LIQUID if self.receipt_id else None
        if liquid is True and self.material != MaterialType.LIQUID:
            raise ValidationError(_("A liquid receipt can only contain liquid material."))
        if liquid is False and self.material == MaterialType.LIQUID:
            raise ValidationError(_("A solid receipt cannot contain liquid material."))

    @property
    def batches(self):
        """The waste records this line produced: one for a liquid line (line.batch),
        one per package for a solid line (see WasteReceiptPackage)."""
        if self.batch_id:
            return [self.batch]
        return [p.batch for p in self.packages.all()]


class WasteReceiptPackage(models.Model):
    """SOLID only: one physical package of a line = one WasteBatch.
    A line of 5 drums produces 5 packages / 5 batches (LW-DR-0001 ... 0005)."""
    line = models.ForeignKey(WasteReceiptLine, on_delete=models.CASCADE, related_name="packages")
    sequence = models.PositiveIntegerField(_("Package No."))
    batch = models.OneToOneField(WasteBatch, on_delete=models.PROTECT, related_name="receipt_package")

    class Meta:
        ordering = ["sequence"]
        constraints = [models.UniqueConstraint(fields=["line", "sequence"], name="uniq_package_sequence_per_line")]


class WasteIdCounter(models.Model):
    """Running number per prefix (e.g. 'LW-BG'). Row-locked in receipt_services.next_waste_id()."""
    prefix = models.CharField(max_length=20, unique=True)
    last_value = models.PositiveIntegerField(default=0)