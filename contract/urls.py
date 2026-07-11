# contract/urls.py

from django.urls import path
from . import views

urlpatterns = [
    path('', views.contract_index, name='contract_index'),
    path('contract/edit/<int:pk>/', views.contract_edit, name='contract_edit'),
    path("save-column/", views.save_column, name="save_column"),
    path("get-column/", views.get_column, name="get_column"),
    path("export-contracts-csv/", views.export_contracts_csv, name="export_contracts_csv"),
    path(
    "create-contract-bulk/",
    views.create_contract_bulk,
    name="create_contract_bulk"
),
    ]