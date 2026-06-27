from django.db import models

# Create your models here.
from django.db import models

# Create your models here.
from django.conf import settings
from django.db import models
from waste.models import WasteBatch
from dashboard.models import Nuclides


class SampleStage(models.TextChoices):
    RECEIPT = 'RECEIPT', 'Receipt'
    TREATMENT = 'TREATMENT', 'Treatment'
    RELEASE = 'RELEASE', 'Release'
    SOLIDIFICATION = 'SOLIDIFICATION', 'Solidification'


class SampleStatus(models.TextChoices):

    COLLECTED = 'COLLECTED', 'Collected'

    SENT_TO_LAB = 'SENT_TO_LAB', 'Sent To Lab'

    RECEIVED_BY_LAB = 'RECEIVED_BY_LAB', 'Received By Lab'

    IN_ANALYSIS = 'IN_ANALYSIS', 'In Analysis'

    COMPLETED = 'COMPLETED', 'Completed'

    REJECTED = 'REJECTED', 'Rejected'


class Sample(models.Model):

    sample_id = models.CharField(
        max_length=50,
        unique=True
    )

    batch = models.ForeignKey(
        WasteBatch,
        on_delete=models.CASCADE,
        related_name='samples'
    )

    sample_stage = models.CharField(
        max_length=20,
        choices=SampleStage.choices
    )

    sampling_date = models.DateField()

    sample_mass_kg = models.DecimalField(
        max_digits=10,
        decimal_places=5,
        blank=True,
        null=True
    )

    sample_volume_l = models.DecimalField(
        max_digits=10,
        decimal_places=5,
        blank=True,
        null=True
    )

    urgent = models.BooleanField(
        default=False
    )

    status = models.CharField(
        max_length=20,
        choices=SampleStatus.choices,
        default=SampleStatus.SENT_TO_LAB
    )

    collected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='samples_collected'
    )

    remarks = models.TextField(
        blank=True,
        null=True
    )

    sample_code_barcode = models.CharField(
    max_length=100,
    unique=True,
    blank=True,
    null=True
    )

    lab_received_date = models.DateField(
        blank=True,
        null=True
    )

    lab_comments = models.TextField(
        blank=True,
        null=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        ordering = [
            '-urgent',
            'sampling_date'
        ]

    def __str__(self):
        return self.sample_id


# Analysis

class Analysis(models.Model):

    sample = models.OneToOneField(
        Sample,
        on_delete=models.CASCADE,
        related_name='analysis'
    )

    analysis_date = models.DateField()

    total_alpha = models.DecimalField(
        max_digits=20,
        decimal_places=5,
        blank=True,
        null=True
    )

    total_beta = models.DecimalField(
        max_digits=20,
        decimal_places=5,
        blank=True,
        null=True
    )

    analyst = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True
    )

    approved = models.BooleanField(
        default=False
    )

    is_latest = models.BooleanField(
    default=True
    )

    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_analyses'
    )

    review_date = models.DateField(
        blank=True,
        null=True
    )

    analysis_notes = models.TextField(
        blank=True,
        null=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )
    
    def save(self, *args, **kwargs):

        super().save(*args, **kwargs)

        Analysis.objects.filter(
            sample__batch=self.sample.batch
        ).exclude(
            pk=self.pk
        ).update(
            is_latest=False
        )

        if not self.is_latest:
            self.is_latest = True
            super().save(
                update_fields=['is_latest']
            )
            
    def __str__(self):
        return f"Analysis - {self.sample.sample_id}"



# Gamma Activities

class GammaActivity(models.Model):

    analysis = models.ForeignKey(
        Analysis,
        on_delete=models.CASCADE,
        related_name='gamma_activities'
    )

    radionuclide = models.ForeignKey(
        Nuclides,
        on_delete=models.PROTECT
    )

    activity_bq = models.DecimalField(
        max_digits=20,
        decimal_places=5
    )

    class Meta:
        unique_together = (
            'analysis',
            'radionuclide'
        )

    def __str__(self):
        return (
            f"{self.radionuclide} - "
            f"{self.activity_bq}"
        )