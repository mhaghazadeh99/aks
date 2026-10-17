from django.urls import path

from . import views

urlpatterns = [
    path("equipment/", views.equipment_list, name="oc_equipment_list"),
    path("equipment/new/", views.equipment_create, name="oc_equipment_create"),
    path("equipment/export/", views.equipment_export_csv, name="oc_equipment_export_csv"),
    path("equipment/<int:pk>/", views.equipment_detail, name="oc_equipment_detail"),
    path("equipment/<int:pk>/edit/", views.equipment_edit, name="oc_equipment_edit"),
    path("equipment/<int:pk>/calibrations/add/", views.calibration_add, name="oc_calibration_add"),
]
