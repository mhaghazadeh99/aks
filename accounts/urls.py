from django.urls import path
from . import views

urlpatterns = [
    path("view-permissions/", views.view_permission_list, name="view_permission_list"),
    path("view-permissions/import/", views.view_permission_import, name="view_permission_import"),
    path("view-permissions/<int:pk>/delete/", views.view_permission_delete, name="view_permission_delete"),
]