from django.urls import path

from . import views

urlpatterns = [

    path(
        'merge/',
        views.merge_operation,
        name='merge_operation'
    ),

    path(
        'split/<int:batch_id>/',
        views.split_operation,
        name='split_operation'
    ),

]