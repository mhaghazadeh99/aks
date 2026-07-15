from django.urls import path
from . import views

urlpatterns = [

    path(
        "",
        views.radionuclide_list,
        name="radionuclide_list"
    ),

]