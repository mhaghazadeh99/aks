from django.urls import path
from . import views

urlpatterns = [
    path("", views.waste_home, name="waste_home"),
    path("list/", views.waste_table, name="waste_table"),

    path("new/", views.waste_create, name="waste_create"),
    path("<int:pk>/edit/", views.waste_edit, name="waste_edit"),
    path("<int:pk>/", views.waste_detail, name="waste_detail"),

    path("merge/", views.waste_merge, name="waste_merge"),
    path("<int:pk>/split/", views.waste_split, name="waste_split"),
    path("<int:pk>/condition/", views.waste_condition, name="waste_condition"),
    path("send-to-analysis/", views.waste_send_to_analysis, name="waste_send_to_analysis"),

    path("save-column/", views.waste_save_column, name="waste_save_column"),
    path("get-column/", views.waste_get_column, name="waste_get_column"),
    path("export-csv/", views.waste_export_csv, name="waste_export_csv"),
    path("<int:pk>/release/", views.waste_release, name="waste_release"),
    path("release-report/", views.release_annual_report, name="release_annual_report"),
]
