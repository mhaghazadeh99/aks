from django.urls import path
from . import views

urlpatterns = [
    path('queue/', views.lab_queue, name='lab_queue'),
    path('analysis/<int:sample_id>/', views.analysis_create, name='analysis_create'),
    path('sample_create/<int:batch_id>/', views.sample_create, name='sample_create'),
    path(
    'receive/<int:sample_id>/',
    views.receive_sample_lab,
    name='receive_sample_lab'
),
]