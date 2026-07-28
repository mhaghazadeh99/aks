from django.db import models
from simple_history.models import HistoricalRecords

from operations.models import LicenseRequest


class LicensePayment(models.Model):

    license = models.OneToOneField(
        LicenseRequest,
        on_delete=models.PROTECT,
        related_name="payment",
    )

    payment_done = models.BooleanField(
        default=False,
    )

    payment_date = models.DateField(
        blank=True,
        null=True,
    )

    amount_paid = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        blank=True,
        null=True,
    )

    notes = models.TextField(
        blank=True,
        null=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    history = HistoricalRecords()

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "License Payment"
        verbose_name_plural = "License Payments"

    def __str__(self):
        if self.license.letter_number:
            return f"{self.license.letter_number}"
        return f"Payment {self.pk}"