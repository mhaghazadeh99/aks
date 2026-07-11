from django.db import models
from simple_history.models import HistoricalRecords


class Contract(models.Model):

    dsrs = models.ManyToManyField(
        "dashboard.DSRS",
        related_name="contracts"
    )

    Source_Type = models.CharField(
        max_length=10
    )

    status = models.CharField(
        max_length=50
    )

    status_date = models.DateField()

    facility = models.CharField(
        max_length=200,
        blank=True,
        null=True
    )


    contract_signed = models.BooleanField(
        default=False
    )

    contract_signed_date = models.DateField(
        null=True,
        blank=True
    )


    payment_done = models.BooleanField(
        default=False
    )

    payment_date = models.DateField(
        null=True,
        blank=True
    )


    licence_valid = models.BooleanField(
        default=False
    )

    licence_issue_date = models.DateField(
        null=True,
        blank=True
    )


    created_at = models.DateTimeField(
        auto_now_add=True
    )

    history = HistoricalRecords()


    def __str__(self):
        return f"Contract #{self.id}"