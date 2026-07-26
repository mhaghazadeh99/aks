from django.db import models

# Create your models here.
from django.db import models
from django.utils.translation import gettext_lazy as _


class FacilityModel(models.Model):

    name = models.CharField(
        _("Facility Name"),
        max_length=255, blank=True,null=True
    )

    responsible_person = models.CharField(
        _("Responsible Person"),
        max_length=150, blank=True,null=True
    )

    telephone = models.CharField(
        _("Telephone"),
        max_length=50, blank=True,null=True
    )

    email = models.EmailField(
        _("Email"),
        blank=True,null=True
    )

    address1 = models.CharField(
        _("Address Line 1"),
        max_length=255, blank=True,null=True
    )

    address2 = models.CharField(
        _("Address Line 2"),
        max_length=255,
         blank=True,null=True
    )

    postal_code = models.CharField(
        _("Postal Code"),
        max_length=20,
         blank=True,null=True
    )

    national_id = models.CharField(
        _("National ID"),
        max_length=50,
         blank=True,null=True
    )

    economic_code = models.CharField(
        _("Economic Code"),
        max_length=50,
         blank=True,null=True
    )

    
    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        ordering = ["name"]
        verbose_name = _("Facility")
        verbose_name_plural = _("Facilities")

    def __str__(self):
        return str(self.name) if self.name else "Unnamed Facility"