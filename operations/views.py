from django.shortcuts import render, redirect

from django.contrib import messages

from django.db import transaction

from django.utils.translation import gettext_lazy as _
from django.db.models import Q

from django.core.paginator import Paginator

from django.contrib import messages

from django.shortcuts import redirect

from .forms import (

    LicenseRequestForm,

    LicenseAttachmentForm,

    LicenseNuclideForm,)

from .models import (

    LicenseRequest,

    LicenseAttachment,

    LicenseAttachmentType,

    LicenseDSRS,)
# ============================================================
# Operation Home
# ============================================================

def operation_home(request):

    return render(

        request,

        "operations/operation_home.html",

        

    )






def license_list(request):

    search = request.GET.get(
        "search",
        "",
    )

    page_size = request.GET.get(
        "page_size",
        "10",
    )

    queryset = (

        LicenseRequest.objects

        .select_related(
            "facility",
        )

        .prefetch_related(
            "license_dsrss__nuclide",
            "attachments",
        )

        .order_by(
            "-created_at",
        )

    )

    if search:

        queryset = queryset.filter(

            Q(
                facility__name__icontains=search
            )

            |

            Q(
                letter_number__icontains=search
            )

            |

            Q(
                contract_number__icontains=search
            )

        )

    paginator = Paginator(

        queryset,

        int(page_size),

    )

    page_number = request.GET.get(
        "page",
    )

    page_obj = paginator.get_page(
        page_number,
    )

    context = {

        "page_obj": page_obj,

        "search": search,

        "page_size": int(page_size),

    }

    return render(

        request,

        "operations/license_list.html",

        context,

    )


from django.http import HttpResponse


def license_create(request):

    if request.method == "POST":

        form = LicenseRequestForm(

            request.POST,
        )

        attachment_form = LicenseAttachmentForm(

            request.POST,

            request.FILES,
        )

        nuclide_form = LicenseNuclideForm(

            request.POST,
        )

        if (

            form.is_valid()

            and

            attachment_form.is_valid()

            and

            nuclide_form.is_valid()

        ):

            license_request = form.save(
                commit=False,
            )

            license_request.created_by = (
                request.user
            )

            license_request.save()

            files = {

                LicenseAttachmentType.LETTER:
                    attachment_form.cleaned_data["letter"],

                LicenseAttachmentType.COMMITMENT:
                    attachment_form.cleaned_data["commitment"],

                LicenseAttachmentType.PERMIT:
                    attachment_form.cleaned_data["permit"],

                LicenseAttachmentType.INQUIRY:
                    attachment_form.cleaned_data["inquiry"],

                LicenseAttachmentType.OTHER:
                    attachment_form.cleaned_data["other"],

            }

            for attachment_type, uploaded_file in files.items():

                if uploaded_file:

                    LicenseAttachment.objects.create(

                        license=license_request,

                        attachment_type=attachment_type,

                        file=uploaded_file,

                        uploaded_by=request.user,

                    )
            selected_nuclides = request.POST.getlist("nuclides")
            for nuclide_id in selected_nuclides:

                LicenseDSRS.objects.create(

                    license=license_request,

                    nuclide_id=nuclide_id,

                )

            messages.success(

                request,

                _("License request created successfully."),

            )

            return redirect(

                "license_specification",

                license_request.pk,

            )

    else:

        form = LicenseRequestForm()

        attachment_form = LicenseAttachmentForm()

        nuclide_form = LicenseNuclideForm()

    return render(

        request,

        "operations/license_create.html",

        {

            "form": form,

            "attachment_form": attachment_form,

            "nuclide_form": nuclide_form,

        },

    )


def license_detail(
    request,
    pk,
    ):

    return HttpResponse(
        f"License {pk}"
    )


def license_continue(
    request,
    pk,
    ):

    return HttpResponse(
        f"Continue {pk}"
    )


def license_update(
    request,
    pk,
    ):

    return HttpResponse(
        f"Update {pk}"
    )


def license_delete(
    request,
    pk,
    ):

    return HttpResponse(
        f"Delete {pk}"
    )


def license_import_csv(
    request,
    ):

    return HttpResponse(
        "Import CSV"
    )


def license_export_csv(
    request,
    ):

    return HttpResponse(
        "Export CSV"
    )