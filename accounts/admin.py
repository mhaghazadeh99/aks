
from django.contrib import admin
from .models import UserProfile, TrackedUser


@admin.register(TrackedUser)
class TrackedUserAdmin(admin.ModelAdmin):
    list_display = ["user", "added_at"]
    raw_id_fields = ["user"]


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):

    list_display = (
        "user",
        "full_name",
        "position",
    )
