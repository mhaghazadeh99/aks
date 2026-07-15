from django.urls import path

from .views import *

urlpatterns = [

    path(
        "",
        facility_list,
        name="facility_list"
    ),

    path(
        "create/",
        facility_create,
        name="facility_create"
    ),

    path(
        "<int:pk>/edit/",
        facility_update,
        name="facility_update"
    ),

    path(
        "<int:pk>/delete/",
        facility_delete,
        name="facility_delete"
    ),

]