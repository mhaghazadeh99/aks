from django.db import models
from django.conf import settings
# Create your models here.
from django.contrib.auth.models import Group
from django.utils.translation import gettext_lazy as _



def signature_upload_path(instance, filename):

    return (
        f"users/"
        f"signatures/"
        f"user_{instance.user.id}/"
        f"{filename}"
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
        blank=True, null=True
    )

    signature_image = models.ImageField(
        upload_to=signature_upload_path,
        help_text=(
            "Upload transparent PNG, "
            "recommended 800x300 px"
        ),
        blank=True,
        null=True,
    )
    
   
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
   