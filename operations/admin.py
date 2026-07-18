from django.contrib import admin
from .models import *
# Register your models here.

from django.contrib import admin

from .models import (
    Operation,
    OperationSource,
    OperationAttachment,
    OperationSignature,
)


class OperationSourceInline(admin.TabularInline):
    model = OperationSource
    extra = 0


class OperationAttachmentInline(admin.TabularInline):
    model = OperationAttachment
    extra = 0


@admin.register(Operation)
class OperationAdmin(admin.ModelAdmin):

    list_display = (
        "operation_number",
        "operation_type",
        "facility",
        "status",
        "created_at",
    )

    list_filter = (
        "operation_type",
        "status",
    )

    search_fields = (
        "operation_number",
    )

    inlines = [
        OperationSourceInline,
        OperationAttachmentInline,
    ]


admin.site.register(OperationSignature)