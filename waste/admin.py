from django.contrib import admin
from .models import *
# Register your models here.

admin.site.register(WasteBatch)
admin.site.register(LiquidWasteDetails)
admin.site.register(WasteConditioning)
admin.site.register(BatchActivitySnapshot)

# operation
# admin.site.register(Operation)
# admin.site.register(OperationInput)
# admin.site.register(OperationOutput)
# admin.site.register(MergeOperation)
# admin.site.register(SplitOperation)
# admin.site.register(TreatmentOperation)
# admin.site.register(ReleaseOperation)
# admin.site.register(SolidificationOperation)
# admin.site.register(SolidifiedPackage)