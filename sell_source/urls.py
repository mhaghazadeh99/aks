from django.urls import path
from . import views

urlpatterns = [

    path("", views.sell_home, name="sell_home"),
    path("list/", views.sell_list, name="sell_list"),
    path("queue/ceo/", views.sell_ceo_queue, name="sell_ceo_queue"),

    path("new/", views.sell_create, name="sell_create"),

    path("<int:pk>/sources/", views.sell_add_sources, name="sell_add_sources"),
    path("<int:pk>/sources/<int:source_pk>/remove/", views.sell_remove_source, name="sell_remove_source"),
    path("<int:pk>/sources/finish/", views.sell_finish_sources, name="sell_finish_sources"),

    path("<int:pk>/sign/", views.sell_sign, name="sell_sign"),

    path("<int:pk>/", views.sell_detail, name="sell_detail"),
]