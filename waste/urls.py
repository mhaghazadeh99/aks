from django.urls import path
from . import views

urlpatterns = [

    path("", views.waste_list, name="waste_list"),

    path("create/", views.waste_create, name="waste_create"),

    path("<int:pk>/", views.waste_detail, name="waste_detail"),

    path("<int:pk>/edit/", views.waste_edit, name="waste_edit"),

    path("<int:pk>/delete/", views.waste_delete, name="waste_delete"),
]


## operations
# from django.urls import path

# from . import views

# urlpatterns = [

#     path(
#         'merge/',
#         views.merge_operation,
#         name='merge_operation'
#     ),

#     path(
#         'split/<int:batch_id>/',
#         views.split_operation,
#         name='split_operation'
#     ),

# ]