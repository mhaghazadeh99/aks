from django.urls import path

from . import views, views_dosimetry as dv, views_inspection as iv

urlpatterns = [
    # ---- equipment calibration
    path("equipment/", views.equipment_list, name="oc_equipment_list"),
    path("equipment/new/", views.equipment_create, name="oc_equipment_create"),
    path("equipment/export/", views.equipment_export_csv, name="oc_equipment_export_csv"),
    path("equipment/<int:pk>/", views.equipment_detail, name="oc_equipment_detail"),
    path("equipment/<int:pk>/edit/", views.equipment_edit, name="oc_equipment_edit"),
    path("equipment/<int:pk>/calibrations/add/", views.calibration_add, name="oc_calibration_add"),

    # ---- dosimetry
    path("dosimetry/", dv.dosimetry_home, name="oc_dosimetry_home"),
    path("dosimetry/workers/", dv.worker_list, name="oc_worker_list"),
    path("dosimetry/workers/new/", dv.worker_create, name="oc_worker_create"),
    path("dosimetry/workers/<int:pk>/", dv.worker_detail, name="oc_worker_detail"),
    path("dosimetry/workers/<int:pk>/edit/", dv.worker_edit, name="oc_worker_edit"),
    path("dosimetry/tld/", dv.tld_report_list, name="oc_tld_report_list"),
    path("dosimetry/tld/new/", dv.tld_report_create, name="oc_tld_report_create"),
    path("dosimetry/tld/<int:pk>/", dv.tld_report_detail, name="oc_tld_report_detail"),
    path("dosimetry/tld/<int:pk>/edit/", dv.tld_report_edit, name="oc_tld_report_edit"),
    path("dosimetry/tld/<int:pk>/readings/", dv.tld_readings_edit, name="oc_tld_readings_edit"),
    path("dosimetry/tld/<int:pk>/paste/", dv.tld_paste, name="oc_tld_paste"),
    path("dosimetry/operations/", dv.session_list, name="oc_session_list"),
    path("dosimetry/operations/new/", dv.session_create, name="oc_session_create"),
    path("dosimetry/operations/<int:pk>/", dv.session_detail, name="oc_session_detail"),
    path("dosimetry/operations/<int:pk>/edit/", dv.session_edit, name="oc_session_edit"),
    path("dosimetry/operations/<int:pk>/delete/", dv.session_delete, name="oc_session_delete"),
    path("dosimetry/operation-types/", dv.operation_type_list, name="oc_operation_type_list"),
    path("dosimetry/report/", dv.dose_report, name="oc_dose_report"),

    # ---- inspection plan
    path("inspection/", iv.inspection_plan, name="oc_inspection_plan"),
    path("inspection/report/", iv.inspection_report, name="oc_inspection_report"),
    path("inspection/years/new/", iv.inspection_year_create, name="oc_inspection_year_create"),
    path("inspection/items/new/", iv.inspection_item_create, name="oc_inspection_item_create"),
    path("inspection/items/<int:pk>/edit/", iv.inspection_item_edit, name="oc_inspection_item_edit"),
    path("inspection/record/<int:item_id>/<int:year>/<int:week>/", iv.inspection_record_edit,
         name="oc_inspection_record_edit"),
]
