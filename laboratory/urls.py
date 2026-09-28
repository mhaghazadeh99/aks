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
    path("counting-runs/", views.counting_run_list, name="counting_run_list"),
    path("counting-runs/new/", views.counting_run_create, name="counting_run_create"),
    path("counting-runs/<int:pk>/", views.counting_run_detail, name="counting_run_detail"),
    path("reports/<str:kind>/<int:pk>/sign/", views.lab_report_sign, name="lab_report_sign"),
        path("samples/<int:pk>/resubmit/", views.sample_resubmit, name="sample_resubmit"),
    path("analysis/<int:pk>/generate-report/", views.analysis_generate_report, name="analysis_generate_report"),

    path("signatures/analyst/", views.signature_queue, {"role_key": "analyst"}, name="signature_queue_analyst"),
    path("signatures/lab-manager/", views.signature_queue, {"role_key": "lab-manager"}, name="signature_queue_lab_manager"),
    path("signatures/ops-manager/", views.signature_queue, {"role_key": "ops-manager"}, name="signature_queue_ops_manager"),
    path("reports/finalized/", views.finalized_reports, name="finalized_reports"),
]
