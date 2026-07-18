from django.urls import path
from . import views


# app_name = "operations"


urlpatterns = [

    path(
        "operation_home/",
        views.operation_home,
        name="operation_home"
    ),


  path(
    "create/",
    views.operation_create,
    name="operation_create"
),

path(
    "<int:pk>/documents/",
    views.operation_documents,
    name="operation_documents"
),

path(
    "<int:pk>/ocr/",
    views.operation_ocr,
    name="operation_ocr"
),

# path(
#     "<int:pk>/review/",
#     views.operation_review,
#     name="operation_review"
# ),

# path(
#     "<int:pk>/form/",
#     views.operation_form,
#     name="operation_form"
# ),

# path(
#     "<int:pk>/signatures/",
#     views.operation_signatures,
#     name="operation_signatures"
# ),

]