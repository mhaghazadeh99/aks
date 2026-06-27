from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin
# Register your models here.
from .models import *



# admin.py

admin.site.register(Nuclides)
# admin.site.register(HideShowFilter)
# admin.site.register(ModelFilter)


@admin.register(DSRS)
class DSRSAdmin(SimpleHistoryAdmin):

    list_display = (
        "Source_Type",
        "Nuclide",
        "serial_number",
        "current_activity",
        "category",
    )

    


    def current_activity(self, obj):
        val = obj.current_activity_mci()
        return f"{val:.3f} mCi" if val else "-"

    

    def category(self, obj):
        return obj.source_category()