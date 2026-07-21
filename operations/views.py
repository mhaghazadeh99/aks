from django.shortcuts import render, redirect,get_object_or_404
from django.utils import timezone
from django.contrib import messages

from django.db import transaction

from django.utils.translation import gettext_lazy as _
from django.db.models import Q

from django.core.paginator import Paginator

from django.contrib import messages

from django.shortcuts import redirect
from .services.workflow import create_license_workflow
from .services.specification_generator import (
    generate_specification,)

from .forms import (

    LicenseRequestForm,

    LicenseAttachmentForm,LicenseSourceSpecificationFormSet,

    LicenseSourceForm,LicenseFacilityForm)

from .models import (

    LicenseRequest,

    LicenseAttachment,

    LicenseAttachmentType,

    LicenseSource,LicenseStatus,LicenseApproval)
# ============================================================
# Operation Home
# ============================================================

def operation_home(request):

    return render(

        request,

        "operations/operation_home.html",

        

    )





def operation_manager_home(request):

    context = {

        "waiting_count": (

            LicenseRequest.objects.filter(

                status=LicenseStatus.WAITING_MANAGER

            ).count()

        ),

    }

    return render(

        request,

        "operations/manager_home.html",

        context,

    )




def operation_deputy_home(request):

    context = {

        "waiting_count": (

            LicenseRequest.objects.filter(

                status=LicenseStatus.WAITING_DEPUTY

            ).count()

        ),

    }

    return render(

        request,

        "operations/deputy_home.html",

        context,

    )


def operation_control_home(request):

    context = {

        "active_count": (

            LicenseRequest.objects.exclude(

                status=LicenseStatus.COMPLETED

            ).count()

        ),

    }

    return render(

        request,

        "operations/control_home.html",

        context,

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

            "sources__nuclide",

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
            |
            Q(
                sources__serial_number__icontains=search
            )
            |
            Q(
                sources__nuclide__name__icontains=search
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

    def get_license_forms(post=None, files=None):

        return {
            "request_form": LicenseRequestForm(post),
            "facility_form": LicenseFacilityForm(post),
            "attachment_form": LicenseAttachmentForm(post, files),
            "source_form": LicenseSourceForm(post),
        }


    if request.method == "POST":

        forms = get_license_forms(
            request.POST,
            request.FILES
        )

        request_form = forms["request_form"]
        facility_form = forms["facility_form"]
        attachment_form = forms["attachment_form"]
        source_form = forms["source_form"]


        if (
            request_form.is_valid()
            and facility_form.is_valid()
            and attachment_form.is_valid()
            and source_form.is_valid()):
         
            

            license_request = request_form.save(
                commit=False
            )

            license_request.facility = (
                facility_form.cleaned_data["facility"]
            )

            license_request.created_by = request.user
            action = request.POST.get("action")


            if action == "draft":
                license_request.status = LicenseStatus.DRAFT
            else:
                license_request.status = LicenseStatus.SPECIFICATION


            license_request.save()

            create_license_workflow(
                    license_request
                )

            files = {

                LicenseAttachmentType.LETTER:
                    attachment_form.cleaned_data.get("letter"),

                LicenseAttachmentType.COMMITMENT:
                    attachment_form.cleaned_data.get("commitment"),

                LicenseAttachmentType.PERMIT:
                    attachment_form.cleaned_data.get("permit"),

                LicenseAttachmentType.INQUIRY:
                    attachment_form.cleaned_data.get("inquiry"),

                LicenseAttachmentType.OTHER:
                    attachment_form.cleaned_data.get("other"),

            }


            for attachment_type, uploaded_file in files.items():

                if uploaded_file:

                    LicenseAttachment.objects.create(

                        license=license_request,

                        attachment_type=attachment_type,

                        file=uploaded_file,

                        uploaded_by=request.user,

                    )


            selected_sources = request.POST.getlist(
                "sources"
            )


            for nuclide_id in selected_sources:

                LicenseSource.objects.create(

                    license=license_request,

                    nuclide_id=nuclide_id,

                )


            messages.success(
                request,
                _("License request saved successfully."),
            )

            
            if action == "draft":

                return redirect(
                    "license_list"
                )


            return redirect(
                "license_specification",
                pk=license_request.pk,
            )


    else:
        

        forms = get_license_forms()


    return render(
        request,
        "operations/license_create.html",
        forms,
    )





def license_specification(request, pk):

    license_request = get_object_or_404(

        LicenseRequest.objects.select_related(

            "facility",

        ),

        pk=pk,

    )

    queryset = (

        LicenseSource.objects

        .filter(

            license=license_request,

        )

        .select_related(

            "nuclide",

        )

        .order_by(

            "specification_order",

        )

    )

    if request.method == "POST":

        formset = LicenseSourceSpecificationFormSet(

            request.POST,

            queryset=queryset,

        )

        if formset.is_valid():

            formset.save()
            generate_specification(

                license_request,

                request.user,

            )

            license_request.status = LicenseStatus.WAITING_CREATOR

            license_request.specification_completed = True

            license_request.save(
                update_fields=[
                    "status",
                    "specification_completed",
                ]
            )

            messages.success(

                request,

                _("Specification saved successfully."),

            )
            # return redirect(
            #         "license_detail",
            #         pk=license_request.pk,
            #     )
            return redirect(
                "license_sign",
                pk=license_request.pk,
            )
            


    else:

        formset = LicenseSourceSpecificationFormSet(

            queryset=queryset,

        )

    return render(

        request,

        "operations/license_specification.html",

        {

            "license": license_request,

            "formset": formset,

        },

    )




def license_detail(request, pk):

    license_request = get_object_or_404(

        LicenseRequest.objects

        .select_related(
            "facility",
            "created_by",
        )

        .prefetch_related(

            "attachments",

            "sources__nuclide",

        ),

        pk=pk,

    )


    context = {

        "license": license_request,

    }


    return render(

        request,

        "operations/license_detail.html",

        context,

    )



def license_continue(request, pk):

    license_request = get_object_or_404(
        LicenseRequest,
        pk=pk,
    )

    if license_request.status == LicenseStatus.DRAFT:

        return redirect(
            "license_create_edit",
            pk=pk,
        )

    if not license_request.specification_completed:

        return redirect(
            "license_specification",
            pk=pk,
        )

    if license_request.status in [

        LicenseStatus.WAITING_CREATOR,

        LicenseStatus.WAITING_MANAGER,

        LicenseStatus.WAITING_DEPUTY,

    ]:

        return redirect(
            "license_sign",
            pk=pk,
        )

    if license_request.status == LicenseStatus.CONTRACTS:

        return redirect(
            "contract_detail",
            pk=pk,
        )

    if license_request.status == LicenseStatus.FINANCE:

        return redirect(
            "finance_detail",
            pk=pk,
        )

    if license_request.status == LicenseStatus.READY_TO_ISSUE:

        return redirect(
            "license_issue",
            pk=pk,
        )

    return redirect(
        "license_detail",
        pk=pk,
    )


def license_update(request, pk):

    license_request = get_object_or_404(
        LicenseRequest,
        pk=pk,
    )


    if request.method == "POST":

        request_form = LicenseRequestForm(
            request.POST,
            instance=license_request,
        )

        facility_form = LicenseFacilityForm(
            request.POST,
        )


        if (
            request_form.is_valid()
            and facility_form.is_valid()
        ):

            license_request = request_form.save(
                commit=False
            )


            license_request.facility = (
                facility_form.cleaned_data["facility"]
            )


            license_request.save()


            messages.success(
                request,
                _("License updated successfully."),
            )


            return redirect(
                "license_detail",
                pk=license_request.pk,
            )


    else:

        request_form = LicenseRequestForm(
            instance=license_request,
        )


        facility_form = LicenseFacilityForm(
            initial={
                "facility": license_request.facility,
            }
        )


    return render(
        request,
        "operations/license_update.html",
        {
            "license": license_request,
            "request_form": request_form,
            "facility_form": facility_form,
        },
    )




def license_delete(request, pk):

    license_request = get_object_or_404(
        LicenseRequest,
        pk=pk,
    )


    if request.method == "POST":

        license_request.delete()


        messages.success(
            request,
            _("License deleted successfully."),
        )


        return redirect(
            "license_list"
        )


    return render(
        request,
        "operations/license_delete_confirm.html",
        {
            "license": license_request,
        },
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




def license_sign(request, pk):

    license_request = get_object_or_404(
        LicenseRequest,
        pk=pk,
    )


    # Creator can only sign in this stage
    if license_request.status != LicenseStatus.WAITING_CREATOR:
        return redirect(
            "license_continue",
            pk=pk,
        )


    specification = get_object_or_404(
        LicenseAttachment,
        license=license_request,
        attachment_type=LicenseAttachmentType.SPECIFICATION,
    )


    creator_approval = get_object_or_404(
        LicenseApproval,
        license=license_request,
        step=LicenseApproval.ApprovalStep.CREATOR,
    )


    if request.method == "POST":

        creator_approval.status = (
            LicenseApproval.ApprovalStatus.APPROVED
        )

        creator_approval.approver = request.user

        creator_approval.approved_at = timezone.now()

        creator_approval.save()


        license_request.status = (
            LicenseStatus.WAITING_MANAGER
        )

        license_request.save()


        return redirect(
            "license_continue",
            pk=pk,
        )


    history = LicenseApproval.objects.filter(
        license=license_request
    )


    return render(
        request,
        "operations/license_sign.html",
        {
            "license": license_request,
            "specification": specification,
            "approval": creator_approval,
            "history": history,
        }
    )

    

def operation_manager_license_list(request):

    queryset = (

        LicenseRequest.objects

        .select_related(
            "facility",
            "created_by",
        )

        .prefetch_related(
            "sources",
        )

        .filter(
            status=LicenseStatus.WAITING_MANAGER
        )

        .order_by(
            "-created_at",
        )

    )

    search = request.GET.get("search", "")

    if search:

        queryset = queryset.filter(

            Q(
                facility__name__icontains=search
            )

            |

            Q(
                letter_number__icontains=search
            )

        )

    paginator = Paginator(queryset, 15)

    page_obj = paginator.get_page(
        request.GET.get("page")
    )

    return render(

        request,

        "operations/license_queue.html",

        {

            "page_title": _("Operations Manager"),

            "page_obj": page_obj,

            "search": search,

        },

    )


def operation_deputy_license_list(request):

    queryset = (

        LicenseRequest.objects

        .select_related(
            "facility",
            "created_by",
        )

        .prefetch_related(
            "sources",
        )

        .filter(
            status=LicenseStatus.WAITING_DEPUTY
        )

        .order_by(
            "-created_at",
        )

    )

    search = request.GET.get("search", "")

    if search:

        queryset = queryset.filter(

            Q(
                facility__name__icontains=search
            )

            |

            Q(
                letter_number__icontains=search
            )

        )

    paginator = Paginator(queryset, 15)

    page_obj = paginator.get_page(
        request.GET.get("page")
    )

    return render(

        request,

        "operations/license_queue.html",

        {

            "page_title": _("Deputy Manager"),

            "page_obj": page_obj,

            "search": search,

        },

    )