

from django.urls import path
from . import views

urlpatterns = [
    path("", views.radionuclide_list, name="radionuclide_list"),
    path("add/", views.radionuclide_add, name="radionuclide_add"),
    path("edit/<int:pk>/", views.radionuclide_edit, name="radionuclide_edit"),
    path("import/", views.radionuclide_import_csv, name="radionuclide_import_csv"),
]