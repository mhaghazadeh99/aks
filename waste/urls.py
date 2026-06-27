from django.urls import path
from . import views

urlpatterns = [
    
    path('', views.waste_list, name='waste_list'),
    path('create/', views.waste_create, name='waste_create'),
    path('<int:pk>/', views.waste_detail, name='waste_detail'),
]