from django.urls import path
from . import views

urlpatterns = [
    path("", views.lab_home, name="lab_home"),
    path("samples/", views.sample_list, name="sample_list"),
    path("samples/new/", views.sample_create, name="sample_create"),
    path("samples/<int:pk>/", views.sample_detail, name="sample_detail"),
    path("samples/<int:pk>/edit/", views.sample_edit, name="sample_edit"),

    # status transitions
    path("samples/<int:pk>/send-to-lab/", views.sample_send_to_lab, name="sample_send_to_lab"),
    path("samples/<int:pk>/receive/", views.sample_lab_receive, name="sample_lab_receive"),
    path("samples/<int:pk>/start-analysis/", views.sample_start_analysis, name="sample_start_analysis"),
    path("samples/<int:pk>/reject/", views.sample_reject, name="sample_reject"),

    # analysis
    path("samples/<int:pk>/analysis/", views.analysis_edit, name="analysis_edit"),
    path("analysis/<int:pk>/approve/", views.analysis_approve, name="analysis_approve"),
    path("analysis/review/", views.analysis_review_queue, name="analysis_review_queue"),

    path("samples/export-csv/", views.sample_export_csv, name="sample_export_csv"),
]
