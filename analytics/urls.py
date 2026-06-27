from django.urls import path
from . import views

urlpatterns = [
    path("", views.dashboard, name="analytics_home"),

    # APIs
    path("models/", views.models),
    path("fields/<str:model_key>/", views.fields),
    path("chart/", views.chart),
    path("time-chart/", views.time_chart),
]