from django.contrib import admin

from .models import Analysis, NuclideActivity, Sample


class NuclideActivityInline(admin.TabularInline):
    model = NuclideActivity
    extra = 0


@admin.register(Sample)
class SampleAdmin(admin.ModelAdmin):
    list_display = ("sample_id", "batch", "sample_stage", "status", "sampling_date", "urgent")
    list_filter = ("status", "sample_stage", "urgent")
    search_fields = ("sample_id", "sample_code_barcode")


@admin.register(Analysis)
class AnalysisAdmin(admin.ModelAdmin):
    list_display = ("sample", "analysis_date", "total_alpha", "total_beta", "approved", "is_latest")
    list_filter = ("approved", "is_latest")
    inlines = [NuclideActivityInline]


@admin.register(NuclideActivity)
class NuclideActivityAdmin(admin.ModelAdmin):
    list_display = ("analysis", "radionuclide", "radiation_type", "activity_bq")
    list_filter = ("radiation_type",)
