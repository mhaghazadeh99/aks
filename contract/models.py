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
    send_to_financial = models.BooleanField(
            default=False
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
    """Historically misnamed 'Contract' — this represents a PI (buyer)
    sale record for ONE DSRS, not a legal contract. Contract number/date
    shown for it come from the DSRS's own linked LicenseContract
    (dashboard.DSRS.contract), never stored here directly."""

    dsrs = models.OneToOneField(
        "dashboard.DSRS",
        on_delete=models.PROTECT,
        related_name="pi_record",
        null=True,
    blank=True,
        
    )

    payment_done = models.BooleanField(default=False)
    payment_date = models.DateField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    history = HistoricalRecords()

    @property
    def contract_number(self):
        return self.dsrs.contract.contract_number if self.dsrs.contract else ""

    @property
    def contract_date(self):
        return self.dsrs.contract.contract_date if self.dsrs.contract else None

    @property
    def facility(self):
        return self.dsrs.Facility

    @property
    def source_type(self):
        return self.dsrs.Source_Type

    @property
    def status(self):
        return self.dsrs.Status

    @property
    def status_date(self):
        return self.dsrs.Status_Date

    def __str__(self):
        return f"PI Record #{self.id} - {self.dsrs}"