from django.urls import path
from . import views



# app_name = "operations"


urlpatterns = [

    path(
        "",
        views.operation_home,
        name="operation_home"
    ),

    path(
        "licenses/",
        views.license_list,
        name="license_list",
    ),

    path(
    "licenses/new/",
    views.license_create,
    name="license_create",
),
path(
    "licenses/<int:pk>/specification/",
    views.license_specification,
    name="license_specification",),
    path(
        "<int:pk>/",
        views.license_detail,
        name="license_detail",
    ),

    path(
        "<int:pk>/continue/",
        views.license_continue,
        name="license_continue",
    ),

    path(
        "<int:pk>/edit/",
        views.license_update,
        name="license_update",
    ),

    path(
        "<int:pk>/delete/",
        views.license_delete,
        name="license_delete",
    ),

    path(
        "import/",
        views.license_import_csv,
        name="license_import_csv",
    ),

    path(
        "export/",
        views.license_export_csv,
        name="license_export_csv",
    ),

]