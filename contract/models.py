from django.db import models
from simple_history.models import HistoricalRecords

from django.db import models
from django.conf import settings
from operations.models import LicenseRequest
from facilities.models import FacilityModel

class LicenseContract(models.Model):

    license = models.OneToOneField(
        LicenseRequest,
        on_delete=models.PROTECT,
        related_name="contract"
    )

    contract_number = models.CharField(
        max_length=100,
        blank=True,
        null=True
    )

    contract_date = models.DateField(
        blank=True,
        null=True
    )

    contract_cost = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        blank=True,
        null=True
    )


    draft_sent_to_customer = models.BooleanField(
        default=False
    )

    draft_sent_date = models.DateField(
        blank=True,
        null=True
    )


    notification_letter_number = models.CharField(
        max_length=30,
        blank=True,
        null=True
    )

    notification_letter_date = models.DateField(
        blank=True,
        null=True
    )


    amendment_notes = models.TextField(
        blank=True,
        null=True
    )


    source_owner = models.CharField(
        max_length=100,
        blank=True,
        null=True
    )


    contract_accountable = models.CharField(
        max_length=100,
        blank=True,
        null=True
    )


    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )


    def __str__(self):
        return self.contract_number or f"Contract {self.pk}"


        
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

    facility =  models.ForeignKey(
            FacilityModel,
            null=True,
            blank=True,
            on_delete=models.SET_NULL,
            related_name="sources"
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