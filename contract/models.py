from django.db import models
from simple_history.models import HistoricalRecords

# Create your models here.
# from dashboard.models import DSRS

class Contract(models.Model):
    # CHANGED: One source can have multiple contracts over its lifecycle
    dsrs = models.ForeignKey(
    "dashboard.DSRS",
    on_delete=models.CASCADE,
    related_name="contracts"
)

    # copied from DSRS at transfer moment
    Source_Type = models.CharField(max_length=10)
    status = models.CharField(max_length=50)
    status_date = models.DateField()
    facility = models.CharField(max_length=200)
    serial_number = models.CharField(max_length=100)
    nuclide = models.CharField(max_length=100)

    activity = models.FloatField(null=True, blank=True)
    activity_unit = models.CharField(max_length=20, null=True, blank=True)
    activity_date = models.DateField(null=True, blank=True)

    # NEW fields (your business logic)
    contract_signed = models.BooleanField(default=False)
    contract_signed_date = models.DateField(null=True, blank=True)

    payment_done = models.BooleanField(default=False)
    payment_date = models.DateField(null=True, blank=True)

  

    licence_valid = models.BooleanField(default=False)
    licence_issue_date = models.DateField(null=True, blank=True)


    created_at = models.DateTimeField(auto_now_add=True)
    history = HistoricalRecords()
    def __str__(self):
        return f"Contract for {self.serial_number}"

