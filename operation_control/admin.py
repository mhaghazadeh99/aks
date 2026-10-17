from django.contrib import admin

from . import models as m


@admin.register(m.OperationType, m.EquipmentApplication, m.EnvironmentalPoint)
class LookupAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "sort_order")
    list_editable = ("is_active", "sort_order")
    search_fields = ("name",)


class CalibrationInline(admin.TabularInline):
    model = m.CalibrationRecord
    extra = 0
    fields = ("calibration_date", "certificate_number", "laboratory", "calibration_type", "result_label", "attachment")


@admin.register(m.Equipment)
class EquipmentAdmin(admin.ModelAdmin):
    list_display = ("equipment_id", "name", "serial_number", "center", "status", "last_calibration_date", "due_date")
    list_filter = ("center", "status", "application", "current_label")
    search_fields = ("equipment_id", "name", "serial_number", "model_name")
    inlines = [CalibrationInline]


class OnlineDoseInline(admin.TabularInline):
    model = m.OnlineDoseRecord
    extra = 1


@admin.register(m.OperationDoseSession)
class SessionAdmin(admin.ModelAdmin):
    list_display = ("operation_type", "performed_date", "location", "duration_minutes")
    list_filter = ("operation_type", "year", "season")
    inlines = [OnlineDoseInline]


class TLDReadingInline(admin.TabularInline):
    model = m.TLDReading
    extra = 0


@admin.register(m.TLDReport)
class TLDReportAdmin(admin.ModelAdmin):
    list_display = ("report_number", "year", "season", "received_date")
    inlines = [TLDReadingInline]


@admin.register(m.RadiationWorker)
class WorkerAdmin(admin.ModelAdmin):
    list_display = ("personnel_code", "full_name", "unit", "status")
    list_filter = ("status", "unit")
    search_fields = ("personnel_code", "full_name")


@admin.register(m.InspectionItem)
class InspectionItemAdmin(admin.ModelAdmin):
    list_display = ("title", "area", "form_code", "period_weeks", "responsible", "is_active")
    list_filter = ("period_weeks", "is_active")
    search_fields = ("title", "area", "form_code")


admin.site.register(m.InspectionPlanYear)
admin.site.register(m.InspectionRecord)
