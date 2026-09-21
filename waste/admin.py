from django.contrib import admin

from .models import WasteBatch, WasteMovement, WasteMovementAttachment, WasteBatchLineage


class WasteMovementInline(admin.TabularInline):
    model = WasteMovement
    extra = 0


@admin.register(WasteBatch)
class WasteBatchAdmin(admin.ModelAdmin):
    list_display = ("waste_id", "waste_type", "waste_state", "waste_class", "facility", "status", "created_at")
    list_filter = ("waste_type", "waste_state", "waste_class", "status", "facility")
    search_fields = ("waste_id", "material", "location")
    inlines = [WasteMovementInline]


@admin.register(WasteMovement)
class WasteMovementAdmin(admin.ModelAdmin):
    list_display = ("batch", "movement_type", "from_facility", "to_facility", "movement_date")
    list_filter = ("movement_type",)


@admin.register(WasteBatchLineage)
class WasteBatchLineageAdmin(admin.ModelAdmin):
    list_display = ("operation", "parent", "child", "performed_by", "performed_at")
    list_filter = ("operation",)


admin.site.register(WasteMovementAttachment)
