from django.db import models
from django.conf import settings
# Create your models here.



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

    
