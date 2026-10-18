from django.urls import path

from . import import_views as imp
from . import views, views_assessment as asm, views_dosimetry as dv, views_inspection as iv, views_lookups as lk

urlpatterns = [
    # ---- equipment calibration
    path("equipment/", views.equipment_list, name="oc_equipment_list"),
    path("equipment/new/", views.equipment_create, name="oc_equipment_create"),
    path("equipment/export/", views.equipment_export_csv, name="oc_equipment_export_csv"),
    path("equipment/<int:pk>/", views.equipment_detail, name="oc_equipment_detail"),
    path("equipment/<int:pk>/edit/", views.equipment_edit, name="oc_equipment_edit"),
    path("equipment/<int:pk>/calibrations/add/", views.calibration_add, name="oc_calibration_add"),
    path("equipment/<int:pk>/delete/", views.equipment_delete, name="oc_equipment_delete"),
    path("equipment/calibrations/<int:pk>/edit/", views.calibration_edit, name="oc_calibration_edit"),
    path("equipment/calibrations/<int:pk>/delete/", views.calibration_delete, name="oc_calibration_delete"),
    path("equipment/<int:equipment_pk>/assessments/new/", asm.assessment_create, name="oc_assessment_create"),
    path("assessments/", asm.assessment_list, name="oc_assessment_list"),
    path("assessments/export/", asm.assessment_export_csv, name="oc_assessment_export_csv"),
    path("assessments/<int:pk>/", asm.assessment_detail, name="oc_assessment_detail"),
    path("assessments/<int:pk>/edit/", asm.assessment_edit, name="oc_assessment_edit"),
    path("assessments/<int:pk>/apply/", asm.assessment_apply, name="oc_assessment_apply"),
    path("assessments/<int:pk>/delete/", asm.assessment_delete, name="oc_assessment_delete"),
    path("equipment/applications/", lk.lookup_list, {"kind": "applications"}, name="oc_application_list"),

    # ---- dosimetry
    path("dosimetry/", dv.dosimetry_home, name="oc_dosimetry_home"),
    path("dosimetry/workers/", dv.worker_list, name="oc_worker_list"),
    path("dosimetry/workers/new/", dv.worker_create, name="oc_worker_create"),
    path("dosimetry/workers/<int:pk>/", dv.worker_detail, name="oc_worker_detail"),
    path("dosimetry/workers/<int:pk>/edit/", dv.worker_edit, name="oc_worker_edit"),
    path("dosimetry/workers/<int:pk>/delete/", dv.worker_delete, name="oc_worker_delete"),
    path("dosimetry/workers/export/", dv.worker_export_csv, name="oc_worker_export_csv"),
    path("dosimetry/tld/", dv.tld_report_list, name="oc_tld_report_list"),
    path("dosimetry/tld/new/", dv.tld_report_create, name="oc_tld_report_create"),
    path("dosimetry/tld/<int:pk>/", dv.tld_report_detail, name="oc_tld_report_detail"),
    path("dosimetry/tld/<int:pk>/edit/", dv.tld_report_edit, name="oc_tld_report_edit"),
    path("dosimetry/tld/<int:pk>/readings/", dv.tld_readings_edit, name="oc_tld_readings_edit"),
    path("dosimetry/tld/<int:pk>/paste/", dv.tld_paste, name="oc_tld_paste"),
    path("dosimetry/tld/<int:pk>/delete/", dv.tld_report_delete, name="oc_tld_report_delete"),
    path("dosimetry/tld/export/", dv.tld_export_csv, name="oc_tld_export_csv"),
    path("dosimetry/operations/", dv.session_list, name="oc_session_list"),
    path("dosimetry/operations/new/", dv.session_create, name="oc_session_create"),
    path("dosimetry/operations/<int:pk>/", dv.session_detail, name="oc_session_detail"),
    path("dosimetry/operations/<int:pk>/edit/", dv.session_edit, name="oc_session_edit"),
    path("dosimetry/operations/<int:pk>/delete/", dv.session_delete, name="oc_session_delete"),
    path("dosimetry/operations/export/", dv.session_export_csv, name="oc_session_export_csv"),
    path("dosimetry/operation-types/", lk.lookup_list, {"kind": "operation-types"}, name="oc_operation_type_list"),
    path("dosimetry/environmental-points/", lk.lookup_list, {"kind": "env-points"}, name="oc_env_point_list"),
    path("dosimetry/report/", dv.dose_report, name="oc_dose_report"),

    # ---- inspection plan
    path("inspection/", iv.inspection_plan, name="oc_inspection_plan"),
    path("inspection/report/", iv.inspection_report, name="oc_inspection_report"),
    path("inspection/export/", iv.inspection_export_csv, name="oc_inspection_export_csv"),
    path("inspection/years/new/", iv.inspection_year_create, name="oc_inspection_year_create"),
    path("inspection/items/new/", iv.inspection_item_create, name="oc_inspection_item_create"),
    path("inspection/items/<int:pk>/edit/", iv.inspection_item_edit, name="oc_inspection_item_edit"),
    path("inspection/record/<int:item_id>/<int:year>/<int:week>/", iv.inspection_record_edit,
         name="oc_inspection_record_edit"),

    # ---- CSV / Excel import (kinds: equipment, workers, tld, online_doses, inspection)
    path("import/<slug:kind>/", imp.csv_import_view, name="oc_import"),
    path("import/<slug:kind>/template/", imp.csv_template_view, name="oc_import_template"),
]
