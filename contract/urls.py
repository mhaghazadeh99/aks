# contract/urls.py

from django.urls import path
from . import views

urlpatterns = [
    path("",views.contract_home,name="contract_home"),

    path(
        "license",
        views.license_contract_home,
        name="license_contract_home"
    ),
      path(
        "create/<int:pk>/",
        views.license_contract_create,
        name="license_contract_create"
    ),


    path(
        "update/<int:pk>/",
        views.license_contract_update,
        name="license_contract_update"
    ),
    path('source', views.contract_index, name='contract_index'),
    path('contract/edit/<int:pk>/', views.contract_edit, name='contract_edit'),
    path("save-column/", views.save_column, name="save_column"),
    path("get-column/", views.get_column, name="get_column"),
    path("export-contracts-csv/", views.export_contracts_csv, name="export_contracts_csv"),
    path(
    "create-contract-bulk/",
    views.create_contract_bulk,
    name="create_contract_bulk"
),
path(
    "ready-to-issue/",
    views.ready_to_issue_list,
    name="ready_to_issue_list",
),
path(
    "licenses/<int:pk>/issue/",
    views.issue_license,
    name="issue_license",
),
path(
    "licenses/issued/",
    views.issued_license_list,
    name="issued_license_list",
),
path("send-to-pi/", views.contract_send_to_pi, name="contract_send_to_pi"),
    ]