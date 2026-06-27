# contract/urls.py

from django.urls import path
from . import views

urlpatterns = [
    path('', views.contract_index, name='contract_index'),
    path('contract/edit/<int:pk>/', views.contract_edit, name='contract_edit'),
]