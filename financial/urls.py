from django.urls import path

from .views import *

urlpatterns = [

    path(
        "",
        financial_home,
        name="financial_home",
    ),

    path(
        "license-payments/",
        license_payment_list,
        name="license_payment_list",
    ),
    path(
    "license-payments/<int:pk>/",
    license_payment_update,
    name="license_payment_update",
    ),
]