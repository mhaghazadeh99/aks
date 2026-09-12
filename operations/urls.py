from django.urls import path
from . import views



# app_name = "operations"


urlpatterns = [
    path("ceo/licenses/", views.operation_ceo_license_list, name="operation_ceo_license_list"),

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
    path(
    "licenses/<int:pk>/sign/",
    views.license_sign,
    name="license_sign",
),
path(
    "manager/",
    views.operation_manager_home,
    name="operation_manager_home",
),

path(
    "manager/licenses/",
    views.operation_manager_license_list,
    name="operation_manager_license_list",
),


path(
    "deputy/",
    views.operation_deputy_home,
    name="operation_deputy_home",
),

path(
    "deputy/licenses/",
    views.operation_deputy_license_list,
    name="operation_deputy_license_list",
),


path(
    "control/",
    views.operation_control_home,
    name="operation_control_home",
),
path(
    "licenses/<int:pk>/edit-draft/",
    views.license_create,
    name="license_create_edit",
),

]