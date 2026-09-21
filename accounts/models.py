from django.db import models
from django.conf import settings
# Create your models here.
from django.contrib.auth.models import Group
from django.utils.translation import gettext_lazy as _
from django.core.files.base import ContentFile


def signature_upload_path(instance, filename):
    return (
        f"users/"
        f"signatures/"
        f"user_{instance.user.id}/"
        f"{filename}"
    )


def clean_signature_upload_path(instance, filename):
    return (
        f"users/"
        f"signatures/"
        f"user_{instance.user.id}/"
        f"clean_{filename.rsplit('.', 1)[0]}.png"
    )


class UserProfile(models.Model):

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )

    full_name = models.CharField(
        max_length=150
    )

    position = models.CharField(
        max_length=150,
        blank=True,
        null=True
    )

    # Original scanned signature
    signature_image = models.ImageField(
        upload_to=signature_upload_path,
        help_text=(
            "Upload scanned signature image"
        ),
        blank=True,
        null=True,
    )

    # Processed transparent signature
    signature_clean = models.ImageField(
        upload_to=clean_signature_upload_path,
        help_text=(
            "Automatically generated transparent signature"
        ),
        blank=True,
        null=True,
        editable=False,
    )


    def save(self, *args, **kwargs):

        regenerate = False

        if self.pk:
            old = UserProfile.objects.filter(pk=self.pk).only("signature_image").first()
            if old and old.signature_image.name != self.signature_image.name:
                regenerate = True
        else:
            regenerate = bool(self.signature_image)

        super().save(*args, **kwargs)

        if self.signature_image and (regenerate or not self.signature_clean):

            from .utils import extract_signature_ink

            cleaned_file = extract_signature_ink(self.signature_image)

            self.signature_clean.save(
                f"user_{self.user.id}_signature.png",
                ContentFile(cleaned_file.read()),
                save=False,
            )

            super().save(update_fields=["signature_clean"])


    def __str__(self):
        return self.user.username

class ViewPermission(models.Model):

    view_name = models.CharField(
        _("View Name"),
        max_length=150,
        unique=True,
        help_text=_("The Django URL name (the 'name=' in urls.py), e.g. 'add_source'."),
    )

    groups = models.ManyToManyField(
        Group,
        verbose_name=_("Allowed Groups"),
        related_name="view_permissions",
        help_text=_("User needs to belong to AT LEAST ONE of these groups."),
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("View Permission")
        verbose_name_plural = _("View Permissions")
        ordering = ["view_name"]

    def __str__(self):
        return f"{self.view_name} -> {', '.join(g.name for g in self.groups.all())}"
   