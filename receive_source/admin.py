from django.contrib import admin

from .models import (
    ReceiveRequest,
    ReceiveSource,
    ReceiveAttachment,
    ReceiveContract,
    ReceivePayment,
    ReceiveApproval,
)


class ReceiveSourceInline(admin.TabularInline):
    model = ReceiveSource
    extra = 0


class ReceiveAttachmentInline(admin.TabularInline):
    model = ReceiveAttachment
    extra = 0


class ReceiveApprovalInline(admin.TabularInline):
    model = ReceiveApproval
    extra = 0


@admin.register(ReceiveRequest)
class ReceiveRequestAdmin(admin.ModelAdmin):
    list_display = ("__str__", "facility", "status", "created_by", "created_at")
    list_filter = ("status", "facility")
    search_fields = ("delivery_letter_number", "facility__name")
    inlines = [ReceiveSourceInline, ReceiveAttachmentInline, ReceiveApprovalInline]


@admin.register(ReceiveContract)
class ReceiveContractAdmin(admin.ModelAdmin):
    list_display = ("contract_number", "receive_request", "contract_cost", "discount_requested", "send_to_financial")
    list_filter = ("discount_requested", "send_to_financial")
    search_fields = ("contract_number",)


@admin.register(ReceivePayment)
class ReceivePaymentAdmin(admin.ModelAdmin):
    list_display = ("receive_request", "payment_done", "payment_date", "amount_paid")
    list_filter = ("payment_done",)


@admin.register(ReceiveSource)
class ReceiveSourceAdmin(admin.ModelAdmin):
    list_display = ("receive_request", "nuclide", "serial_number", "item_type", "result_dsrs_count")
    list_filter = ("item_type",)
    search_fields = ("serial_number", "nuclide__name")

    def result_dsrs_count(self, obj):
        return obj.result_dsrs.count()
    result_dsrs_count.short_description = "Result DSRS Count"


@admin.register(ReceiveApproval)
class ReceiveApprovalAdmin(admin.ModelAdmin):
    list_display = ("receive_request", "step", "status", "approver", "approved_at")
    list_filter = ("step", "status")
