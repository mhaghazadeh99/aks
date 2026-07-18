# operations/views.py

from django.shortcuts import render, redirect

from django.contrib import messages

from django.db import transaction

from django.utils.translation import gettext_lazy as _

from django.shortcuts import get_object_or_404

from .forms import OperationAttachmentUploadForm
from .constants import REQUIRED_DOCUMENTS
from .models import (
    Operation,
    OperationAttachment,
)

from .forms import OperationForm



# ============================================================
# Operation Home
# ============================================================

def operation_home(request):

    operations = Operation.objects.select_related(
        "facility",
        "created_by",
    ).all()


    context = {

        "operations": operations,

    }


    return render(

        request,

        "operations/operation_home.html",

        context,

    )



# ============================================================
# Create Operation
# ============================================================

from django.contrib.auth.decorators import login_required

@login_required
@transaction.atomic
def operation_create(request):

    if request.method == "POST":

        form = OperationForm(
            request.POST
        )


        if form.is_valid():

            operation = form.save(
                commit=False
            )

            operation.created_by = request.user

            operation.save()


            messages.success(
                request,
                _("Operation created successfully.")
            )


            return redirect(
                f"/facilities/{operation.facility.pk}/edit/?next=/operations/{operation.pk}/documents/"
            )


    else:

        form = OperationForm()


    return render(
        request,
        "operations/operation_create.html",
        {
            "form":form
        }
    )


@login_required
def operation_documents(request, pk):


    operation = get_object_or_404(
        Operation,
        pk=pk
    )


    required_documents = REQUIRED_DOCUMENTS[
        operation.operation_type
    ]


    if request.method == "POST":


        form = OperationAttachmentUploadForm(
            request.POST,
            request.FILES
        )


        if form.is_valid():


            attachment = form.save(
                commit=False
            )


            attachment.operation = operation

            attachment.uploaded_by = request.user


            attachment.original_filename = (
                attachment.file.name
            )


            attachment.save()


            messages.success(
                request,
                _("Document uploaded.")
            )


            return redirect(
                "operation_documents",
                pk=pk
            )


    else:

        form = OperationAttachmentUploadForm()



    return render(
        request,
        "operations/operation_documents.html",
        {

            "operation":operation,

            "required_documents":
                required_documents,

            "form":form,

            "attachments":
                operation.attachments.all(),

        }
    )