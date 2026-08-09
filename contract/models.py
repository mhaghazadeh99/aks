from django.db import models
from simple_history.models import HistoricalRecords
from django.conf import settings
from operations.models import LicenseRequest
from facilities.models import FacilityModel
from django.utils.translation import gettext_lazy as _

class LicenseContract(models.Model):

    license = models.OneToOneField(
        LicenseRequest,
        on_delete=models.PROTECT,
        related_name="contract"
    )

    contract_number = models.CharField(
            _("Contract Number"),
            max_length=100,
            blank=True,
            null=True,
        )
    
    


    contract_date = models.DateField(
        _("Contract Date"),
        blank=True,
        null=True,
    )

    contract_cost = models.DecimalField(
        _("Contract Cost"),
        max_digits=14,
        decimal_places=2,
        blank=True,
        null=True,
    )

    send_to_financial = models.BooleanField(
        _("Send to Financial"),
        default=False,
    )

    draft_sent_to_customer = models.BooleanField(
        _("Draft Sent to Customer"),
        default=False,
    )

    draft_sent_date = models.DateField(
        _("Draft Sent Date"),
        blank=True,
        null=True,
    )
    draft_letter_number = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=_("Draft Letter Number"),
    )
    draft_letter_date = models.DateField(
        blank=True,
        null=True,
        verbose_name=_("Draft Letter Date"),
    )

    notification_letter_number = models.CharField(
        _("Notification Letter Number"),
        max_length=30,
        blank=True,
        null=True,
    )

    notification_letter_date = models.DateField(
        _("Notification Letter Date"),
        blank=True,
        null=True,
    )

     
    License_letter_number = models.CharField(
        _("License Letter Number"),
        max_length=30,
        blank=True,
        null=True,
    )

    License_letter_date = models.DateField(
        _("License Letter Date"),
        blank=True,
        null=True,
    )

    amendment_notes = models.TextField(
        _("Amendment Notes"),
        blank=True,
        null=True,
    )

    source_owner = models.CharField(
        _("Source Owner"),
        max_length=100,
        blank=True,
        null=True,
    )

    contract_accountable = models.CharField(
        _("Contract Accountable"),
        max_length=100,
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


    def __str__(self):
        return self.contract_number or f"Contract {self.pk}"


   




class Contract(models.Model):
    """Historically misnamed 'Contract' — this represents a PI (buyer)
    sale record for ONE DSRS, not a legal contract. Contract number/date
    shown for it come from the DSRS's own linked LicenseContract
    (dashboard.DSRS.contract), never stored here directly."""

    dsrs = models.ManyToManyField(
        "dashboard.DSRS",
       
        related_name="pi_record",
        null=True,
    blank=True,
        
    )

    payment_done = models.BooleanField(
        _("Payment Done"),
        default=False,
    )

    payment_date = models.DateField(
        _("Payment Date"),
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(
        _("Created At"),
        auto_now_add=True,
    )

    history = HistoricalRecords()
    @property
    def contract_number(self):
        source = self.dsrs.select_related("contract").first()
        if source and source.contract:
            return source.contract.contract_number
        return ""


    @property
    def contract_date(self):
        source = self.dsrs.select_related("contract").first()
        if source and source.contract:
            return source.contract.contract_date
        return None


    @property
    def facility(self):
        source = self.dsrs.first()
        return source.Facility if source else ""


    @property
    def source_type(self):
        return ", ".join(
            str(s)
            for s in self.dsrs.values_list("Source_Type", flat=True).distinct()
            if s
        )


    @property
    def status(self):
        return ", ".join(
            str(s)
            for s in self.dsrs.values_list("Status", flat=True).distinct()
            if s
        )


    @property
    def status_date(self):
        dates = self.dsrs.values_list("Status_Date", flat=True).distinct()
        return ", ".join(str(d) for d in dates if d)

  
    

    def __str__(self):
        return f"PI Record #{self.id} - {self.dsrs}"