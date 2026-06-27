from django.db import models

# Create your models here.
from django.db import models

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Sum

from waste.models import WasteBatch


## 2. Operation Types

class OperationType(models.TextChoices):

    MERGE = 'MERGE', 'Merge'

    SPLIT = 'SPLIT', 'Split'

    TREATMENT = 'TREATMENT', 'Treatment'

    RELEASE = 'RELEASE', 'Release'

    SOLIDIFICATION = 'SOLIDIFICATION', 'Solidification'


## 3. Operation Status


class OperationStatus(models.TextChoices):

    DRAFT = 'DRAFT', 'Draft'

    COMPLETED = 'COMPLETED', 'Completed'

    CANCELLED = 'CANCELLED', 'Cancelled'


## 4. Base Operation Model



class Operation(models.Model):

    operation_number = models.CharField(
        max_length=50,
        unique=True
    )

    operation_type = models.CharField(
        max_length=20,
        choices=OperationType.choices
    )

    operation_date = models.DateField()

    status = models.CharField(
        max_length=20,
        choices=OperationStatus.choices,
        default=OperationStatus.DRAFT
    )

    remarks = models.TextField(
        blank=True,
        null=True
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='operations_created'
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        ordering = ['-operation_date']

    def __str__(self):
        return (
            f"{self.operation_number}"
            f" ({self.operation_type})"
        )



## 5. Input Batches


class OperationInput(models.Model):

    operation = models.ForeignKey(
        Operation,
        on_delete=models.CASCADE,
        related_name='inputs'
    )

    batch = models.ForeignKey(
        WasteBatch,
        on_delete=models.PROTECT,
        related_name='used_as_input'
    )

    mass_used_kg = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        blank=True,
        null=True
    )

    volume_used_m3 = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        blank=True,
        null=True
    )

    class Meta:
        unique_together = (
            'operation',
            'batch'
        )

    def __str__(self):
        return (
            f"{self.batch}"
            f" -> "
            f"{self.operation}"
        )


## 6. Output Batches


class OperationOutput(models.Model):

    operation = models.ForeignKey(
        Operation,
        on_delete=models.CASCADE,
        related_name='outputs'
    )

    batch = models.ForeignKey(
        WasteBatch,
        on_delete=models.PROTECT,
        related_name='created_from_operation'
    )

    class Meta:
        unique_together = (
            'operation',
            'batch'
        )

    def __str__(self):
        return (
            f"{self.operation}"
            f" -> "
            f"{self.batch}"
        )


# Specialized Operation Models

# These provide extra information.



## 7. Merge Operation

class MergeOperation(models.Model):

    operation = models.OneToOneField(
        Operation,
        on_delete=models.CASCADE,
        related_name='merge_details'
    )

    reason = models.TextField(
        blank=True,
        null=True
    )

    def __str__(self):
        return (
            f"Merge "
            f"{self.operation.operation_number}"
        )


## 8. Split Operation


class SplitOperation(models.Model):

    operation = models.OneToOneField(
        Operation,
        on_delete=models.CASCADE,
        related_name='split_details'
    )

    reason = models.TextField(
        blank=True,
        null=True
    )

    automatic_mass_distribution = models.BooleanField(
        default=True
    )

    def __str__(self):
        return (
            f"Split "
            f"{self.operation.operation_number}"
        )


## 9. Treatment Types

class TreatmentType(models.TextChoices):

    CHEMICAL = 'CHEMICAL', 'Chemical Treatment'

    SEDIMENTATION = 'SEDIMENTATION', 'Sedimentation'

    FILTRATION = 'FILTRATION', 'Filtration'
    INCINERATION = 'INCINERATION', 'Incineration'
    RETREATMENT = 'RETREATMENT', 'Retreatment'

    

## 10. Treatment Operation

class TreatmentOperation(models.Model):

    operation = models.OneToOneField(
        Operation,
        on_delete=models.CASCADE,
        related_name='treatment_details'
    )

    treatment_type = models.CharField(
        max_length=30,
        choices=TreatmentType.choices
    )

    chemicals_used = models.TextField(
        blank=True,
        null=True
    )

    successful = models.BooleanField(
        null=True,
        blank=True
    )

    requires_retreatment = models.BooleanField(
        default=False
    )

    def __str__(self):
        return (
            f"{self.treatment_type}"
        )


## 11. Release Operation


class ReleaseOperation(models.Model):

    operation = models.OneToOneField(
        Operation,
        on_delete=models.CASCADE,
        related_name='release_details'
    )

    release_authorized_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='authorized_releases'
    )

    release_date = models.DateField()

    release_notes = models.TextField(
        blank=True,
        null=True
    )

    def __str__(self):
        return (
            f"Release "
            f"{self.operation.operation_number}"
        )


## 12. Solidification Types

class ConditioningMatrix(models.TextChoices):

    CEMENT = 'CEMENT', 'Cement'

    CONCRETE = 'CONCRETE', 'Concrete'

    BITUMEN = 'BITUMEN', 'Bitumen'

    POLYMER = 'POLYMER', 'Polymer'



## 13. Solidification Operation

class SolidificationOperation(models.Model):

    operation = models.OneToOneField(
        Operation,
        on_delete=models.CASCADE,
        related_name='solidification_details'
    )

    conditioning_matrix = models.CharField(
        max_length=20,
        choices=ConditioningMatrix.choices
    )

    waste_to_matrix_ratio = models.DecimalField(
        max_digits=10,
        decimal_places=4
    )

    additives = models.TextField(
        blank=True,
        null=True
    )

    def __str__(self):
        return (
            f"Solidification "
            f"{self.operation.operation_number}"
        )



## 14. Output Package Information

# For cemented drums/packages.

class SolidifiedPackage(models.Model):

    solidification = models.ForeignKey(
        SolidificationOperation,
        on_delete=models.CASCADE,
        related_name='packages'
    )

    batch = models.OneToOneField(
        WasteBatch,
        on_delete=models.PROTECT
    )

    package_number = models.CharField(
        max_length=50,
        unique=True
    )

    package_mass_kg = models.DecimalField(
        max_digits=12,
        decimal_places=3
    )

    package_volume_m3 = models.DecimalField(
        max_digits=12,
        decimal_places=3
    )

    def __str__(self):
        return self.package_number


# Getting Parent Batches

# ```python
# OperationInput.objects.filter(
#     operation__outputs__batch=batch
# )
# ```

# ---

# # Getting Children Batches

# ```python
# OperationOutput.objects.filter(
#     operation__inputs__batch=batch
# )

