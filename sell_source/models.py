from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class SellRequestStatus(models.TextChoices):

    DRAFT = "DRAFT", _("Draft — Request Form Uploaded")
    SPECIFICATION = "SPECIFICATION", _("Adding Sources")
    WAITING_CEO = "WAITING_CEO", _("Waiting CEO Signature")
    APPROVED = "APPROVED", _("Approved")


class SellRequest(models.Model):
    """
    The whole "sell source" case, start to finish: a scanned request
    form (jpeg) -> sources picked from inventory -> CEO sign-off ->
    final view page with a "Send to PI" trigger. Deliberately the
    simplest workflow in the app — one signer, no docx generation (the
    source document is a photo, not something we fill in), and the
    Send to PI action reuses your existing create_contract_bulk
    endpoint rather than reimplementing it.
    """

    request_form = models.ImageField(
        _("DSRS Sale Request Form (scanned)"),
        upload_to="sell_source/request_forms/",
        help_text=_("Scanned copy of the signed paper request, JPEG."),
    )

    status = models.CharField(
        _("Status"),
        max_length=20,
        choices=SellRequestStatus.choices,
        default=SellRequestStatus.DRAFT,
    )
    status_date = models.DateTimeField(_("Status Date"), null=True, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("Created By"),
        on_delete=models.PROTECT,
        related_name="sell_requests_created",
    )
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)

    # No separate approval table needed for a single signer — unlike the
    # receive workflow's 5-step chain, this is deliberately flat.
    ceo_approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("Approved By (CEO)"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    ceo_approved_at = models.DateTimeField(_("Approved At"), null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Sell Source Request")
        verbose_name_plural = _("Sell Source Requests")

    def __str__(self):
        return _("Sell Request #%(id)s") % {"id": self.pk}


class SellRequestSource(models.Model):
    """
    One row = one existing DSRS picked from inventory to include in this
    sale. Everything inventory-derived (nuclide, serial, manufacture
    date, recorded activity) is snapshotted at selection time, per your
    description ("chosen from inventory") — this keeps the sale record
    accurate even if the underlying DSRS changes later (e.g. once
    Send to PI moves it to Quality Control).
    """

    sell_request = models.ForeignKey(
        SellRequest,
        on_delete=models.CASCADE,
        related_name="sources",
        verbose_name=_("Sell Request"),
    )

    dsrs = models.ForeignKey(
        "dashboard.DSRS",
        on_delete=models.PROTECT,
        related_name="sell_request_sources",
        verbose_name=_("Source (DSRS)"),
    )

    # ---- Snapshotted from the chosen DSRS at add-time ----
    nuclide = models.ForeignKey(
        "reference.Nuclides",
        on_delete=models.PROTECT,
        verbose_name=_("نام ماده پرتوزا / Nuclide"),
    )
    serial_number = models.CharField(_("شماره سریال / Serial Number"), max_length=25, blank=True, null=True)
    manufacture_date = models.DateField(_("تاریخ ساخت / Manufacture Date"), null=True, blank=True)
    recorded_activity_mci = models.FloatField(_("پرتوزایی ثبت‌شده / Recorded Activity (mCi)"), null=True, blank=True)

    # ---- Filled by the user ----
    physical_characteristics = models.TextField(_("مشخصات فیزیکی / Physical Characteristics"), blank=True)
    remarks = models.TextField(_("ملاحظات / Remarks"), blank=True)

    added_at = models.DateTimeField(_("Added At"), auto_now_add=True)

    class Meta:
        ordering = ["id"]
        verbose_name = _("Sell Request Source")
        verbose_name_plural = _("Sell Request Sources")

    def __str__(self):
        return f"{self.nuclide} ({self.serial_number or '-'})"