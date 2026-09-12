from django.contrib import admin


from .models import SellRequest, SellRequestSource


class SellRequestSourceInline(admin.TabularInline):
    model = SellRequestSource
    extra = 0


@admin.register(SellRequest)
class SellRequestAdmin(admin.ModelAdmin):
    list_display = ("__str__", "status", "created_by", "created_at", "ceo_approved_by", "ceo_approved_at")
    list_filter = ("status",)
    inlines = [SellRequestSourceInline]


@admin.register(SellRequestSource)
class SellRequestSourceAdmin(admin.ModelAdmin):
    list_display = ("sell_request", "nuclide", "serial_number", "recorded_activity_mci")
    search_fields = ("serial_number", "nuclide__name")