"""In waste/urls.py:

    from .urls_receipt import receipt_urlpatterns
    urlpatterns += receipt_urlpatterns

Flat names (waste_receipt_*) to match your existing waste_create / waste_detail style."""
from django.urls import path
from . import views_receipt as v

receipt_urlpatterns = [
    path("receipts/",                       v.receipt_list,     name="waste_receipt_list"),
    path("receipts/new/",                   v.receipt_create,   name="waste_receipt_create"),
    path("receipts/<int:pk>/",              v.receipt_detail,   name="waste_receipt_detail"),
    path("receipts/<int:pk>/minutes/",      v.receipt_minutes,  name="waste_receipt_minutes"),
    path("receipts/<int:pk>/minutes.docx",  v.receipt_print,    name="waste_receipt_print"),
    path("receipts/<int:pk>/finalize/",     v.receipt_finalize, name="waste_receipt_finalize"),
]