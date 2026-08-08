from django.urls import path
from . import views

urlpatterns = [
    path("", views.receive_source_list, name="receive_source_list"),
    path("create/", views.receive_source_create, name="receive_source_create"),
    path("<int:pk>/", views.receive_source_detail, name="receive_source_detail"),
]