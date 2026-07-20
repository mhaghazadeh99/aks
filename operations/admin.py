from django.contrib import admin
from .models import *
# Register your models here.
class LicenseAttachmentInline(admin.TabularInline):
    model = LicenseAttachment
    extra = 1


class LicenseSourceInline(admin.TabularInline):
    model = LicenseSource
    extra = 1


@admin.register(LicenseRequest)
class LicenseRequestAdmin(admin.ModelAdmin):

    inlines = [
        LicenseAttachmentInline,
        LicenseSourceInline,
    ]

    list_display = (
        "id",
        "facility",
        "status",
        "created_at",
    )