from django.urls import path
from . import views

urlpatterns = [

    path(
        "",
        views.operations_home,
        name="operations_home"
    ),

]