from django.db import models
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords

from operations.models import LicenseRequest


class LicensePayment(models.Model):

    license = models.OneToOneField(
        LicenseRequest,
        verbose_name=_("License"),
        on_delete=models.PROTECT,
        related_name="payment",
    )

    payment_done = models.BooleanField(
        _("Payment Completed"),
        default=False,
    )

    payment_date = models.DateField(
        _("Payment Date"),
        blank=True,
        null=True,
    )

    amount_paid = models.DecimalField(
        _("Amount Paid"),
        max_digits=14,
        decimal_places=2,
        blank=True,
        null=True,
    )

    notes = models.TextField(
        _("Notes"),
        blank=True,
        null=True,
    )

    created_at = models.DateTimeField(
        _("Created At"),
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        _("Updated At"),
        auto_now=True,
    )

    history = HistoricalRecords()

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("License Payment")
        verbose_name_plural = _("License Payments")

    def __str__(self):
        if self.license.letter_number:
            return self.license.letter_number
        return _("Payment %(id)s") % {"id": self.pk}