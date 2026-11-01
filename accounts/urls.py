from django.urls import path
from . import views

urlpatterns = [
    path("view-permissions/", views.view_permission_list, name="view_permission_list"),
    path("view-permissions/import/", views.view_permission_import, name="view_permission_import"),
    path("view-permissions/<int:pk>/delete/", views.view_permission_delete, name="view_permission_delete"),
    path("profile/", views.profile, name="profile"),
    
]

from . import activity_views

urlpatterns += [
    path("activity/", activity_views.activity_log, name="activity_log"),
    path("activity/archives/", activity_views.activity_archives, name="activity_archives"),
    path("activity/archives/<int:pk>/download/", activity_views.activity_archive_download, name="activity_archive_download"),
    path("activity/archives/<int:pk>/delete/", activity_views.activity_archive_delete, name="activity_archive_delete"),
]