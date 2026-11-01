from django.db import models
from django.conf import settings
# Create your models here.
from django.contrib.auth.models import Group
from django.utils.translation import gettext_lazy as _
from django.core.files.base import ContentFile
from django.contrib.contenttypes.models import ContentType

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



class TrackedUser(models.Model):
    """A user is tracked if a row exists here."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                related_name="activity_tracking")
    added_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return str(self.user)


class ActivityLog(models.Model):
    class Action(models.TextChoices):
        CREATE = "create", "Create"
        UPDATE = "update", "Update"
        DELETE = "delete", "Delete"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                             on_delete=models.SET_NULL, related_name="activity_logs")
    username = models.CharField(max_length=150, blank=True)
    action = models.CharField(max_length=10, choices=Action.choices, db_index=True)
    content_type = models.ForeignKey(ContentType, null=True, on_delete=models.SET_NULL)
    object_id = models.CharField(max_length=64, blank=True)
    object_repr = models.CharField(max_length=255, blank=True)
    changes = models.JSONField(null=True, blank=True)       # {"field": [old, new]}
    data_before = models.JSONField(null=True, blank=True)   # full old version / deleted record
    path = models.CharField(max_length=500, blank=True)
    method = models.CharField(max_length=10, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-timestamp"]
        indexes = [models.Index(fields=["user", "-timestamp"])]


class ActivityArchive(models.Model):
    month = models.DateField(unique=True)            # first day of the month
    file_path = models.CharField(max_length=500)
    row_count = models.PositiveIntegerField(default=0)
    size_bytes = models.PositiveBigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-month"]
