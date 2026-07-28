from django.contrib import admin

# Register your models here.

from simple_history.admin import SimpleHistoryAdmin

from .models import LicensePayment


@admin.register(LicensePayment)
class LicensePaymentAdmin(SimpleHistoryAdmin):

    list_display = (
        "license",
        "payment_done",
        "payment_date",
        "amount_paid",
    )

    list_filter = (
        "payment_done",
    )

    search_fields = (
        "license__letter_number",
    )