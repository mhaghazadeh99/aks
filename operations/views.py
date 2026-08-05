from django.contrib import messages
from django.core.files import File
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
import json
from django.utils.translation import gettext_lazy as _
from dashboard.models import DSRS
from .models import LicenseSourceComponent
from operations.services.signature_service import SpecificationSigner

from django.utils.translation import gettext_lazy as _
from django.db.models import Q

from django.core.paginator import Paginator


from .services.workflow import create_license_workflow
from .services.specification_generator import (generate_specification,)

from .forms import (LicenseRequestForm, LicenseAttachmentForm, LicenseSourceSpecificationFormSet,
    LicenseSourceForm,LicenseFacilityForm)

from .models import (LicenseRequest, LicenseAttachment, LicenseAttachmentType,
    LicenseSource,LicenseStatus,LicenseApproval,LicenseSourceType)



class _SpecificationValidationFailed(Exception):
    pass
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
                sources__serial_number__icontains=search
            )
            |
            Q(
                sources__nuclide__name__icontains=search
            )

        )
        queryset = queryset.distinct()

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




def license_create(request, pk=None):

    license_request_instance = None

    if pk is not None:
        license_request_instance = get_object_or_404(LicenseRequest, pk=pk)

        if license_request_instance.status != LicenseStatus.DRAFT:
            messages.info(request, _("This license is no longer a draft and can't be edited here."))
            return redirect("license_detail", pk=pk)

    def get_license_forms(post=None, files=None):
        return {
            "request_form": LicenseRequestForm(post, instance=license_request_instance),
            "facility_form": LicenseFacilityForm(
                post,
                initial=(
                    {"facility": license_request_instance.facility}
                    if license_request_instance else None
                ),
            ),
            "attachment_form": LicenseAttachmentForm(post, files),
            "source_form": LicenseSourceForm(post, prefix="picker"),
        }

    if request.method == "POST":
  
        forms = get_license_forms(request.POST, request.FILES)

        request_form = forms["request_form"]
        facility_form = forms["facility_form"]
        attachment_form = forms["attachment_form"]
        source_form = forms["source_form"]


        source_types = request.POST.getlist("source_type")
        nuclides = request.POST.getlist("nuclide")
        dsrs_sources = request.POST.getlist("source_dsrs")
        recycled_components_raw = request.POST.getlist("recycled_components")

        source_errors = []

        if not source_types:
            source_errors.append(_("Please add at least one requested source."))

        requested_qty_by_dsrs = {}
        parsed_recycled_components = []

        for i, s_type in enumerate(source_types):

            if s_type == LicenseSourceType.NEW:
                parsed_recycled_components.append([])
                if not nuclides[i]:
                    source_errors.append(_("Row %(row)d: nuclide is required for a New source.") % {"row": i + 1})

            elif s_type == LicenseSourceType.REUSED:
                parsed_recycled_components.append([])
                dsrs_id = dsrs_sources[i]
                if not dsrs_id:
                    source_errors.append(_("Row %(row)d: no DSRS selected for Reuse.") % {"row": i + 1})
                else:
                    requested_qty_by_dsrs[dsrs_id] = requested_qty_by_dsrs.get(dsrs_id, 0) + 1

            elif s_type == LicenseSourceType.RECYCLED:
                if not nuclides[i]:
                    source_errors.append(_("Row %(row)d: final nuclide is required for a Recycled source.") % {"row": i + 1})

                try:
                    components = json.loads(recycled_components_raw[i]) if recycled_components_raw[i] else []
                except (ValueError, IndexError):
                    components = []

                if not components:
                    source_errors.append(_("Row %(row)d: no components staged for this Recycled source.") % {"row": i + 1})

                for comp in components:
                    dsrs_id = comp.get("dsrsId")
                    qty = int(comp.get("qty", 0))
                    if dsrs_id and qty > 0:
                        requested_qty_by_dsrs[dsrs_id] = requested_qty_by_dsrs.get(dsrs_id, 0) + qty

                parsed_recycled_components.append(components)

            else:
                parsed_recycled_components.append([])
                source_errors.append(_("Row %(row)d: unknown source type.") % {"row": i + 1})

        if requested_qty_by_dsrs:
            dsrs_lookup = DSRS.objects.in_bulk(requested_qty_by_dsrs.keys())
            for dsrs_id, requested_qty in requested_qty_by_dsrs.items():
                dsrs_obj = dsrs_lookup.get(int(dsrs_id))
                if dsrs_obj is None:
                    source_errors.append(_("Selected DSRS (id %(id)s) no longer exists.") % {"id": dsrs_id})
                    continue
                if requested_qty > dsrs_obj.available_count:
                    source_errors.append(
                        _("DSRS %(serial)s: requested %(requested)d but only %(available)d available.") % {
                            "serial": dsrs_obj.serial_number or dsrs_obj.pk,
                            "requested": requested_qty,
                            "available": dsrs_obj.available_count,
                        }
                    )

        if (
            request_form.is_valid()
            and facility_form.is_valid()
            and attachment_form.is_valid()
            # and source_form.is_valid()
            and not source_errors
        ):
            with transaction.atomic():

                license_request = request_form.save(commit=False)
                license_request.facility = facility_form.cleaned_data["facility"]
                action = request.POST.get("action")

                if license_request_instance is None:
                    license_request.created_by = request.user

                if action == "draft":
                    license_request.status = LicenseStatus.DRAFT
                else:
                    license_request.status = LicenseStatus.SPECIFICATION

                license_request.save()

                if license_request_instance is None:
                    create_license_workflow(license_request)

                files = {
                    LicenseAttachmentType.LETTER: attachment_form.cleaned_data.get("letter", []),
                    LicenseAttachmentType.COMMITMENT: attachment_form.cleaned_data.get("commitment", []),
                    LicenseAttachmentType.PERMIT: attachment_form.cleaned_data.get("permit", []),
                    LicenseAttachmentType.INQUIRY: attachment_form.cleaned_data.get("inquiry", []),
                    LicenseAttachmentType.OTHER: attachment_form.cleaned_data.get("other", []),
                }

                for attachment_type, uploaded_files in files.items():
                    for uploaded_file in uploaded_files:
                        LicenseAttachment.objects.create(
                            license=license_request,
                            attachment_type=attachment_type,
                            file=uploaded_file,
                            uploaded_by=request.user,
                        )

                # Editing a draft: simplest correct approach is to replace the
                # source list wholesale rather than diff it — nothing has been
                # consumed yet (available_count is untouched until the
                # specification step), so this is safe.
                if license_request_instance is not None:
                    license_request.sources.all().delete()

                for i, s_type in enumerate(source_types):

                    if s_type == LicenseSourceType.NEW:
                        LicenseSource.objects.create(
                            license=license_request,
                            source_type=s_type,
                            nuclide_id=nuclides[i],
                            source_dsrs=None,
                        )

                    elif s_type == LicenseSourceType.REUSED:
                        LicenseSource.objects.create(
                            license=license_request,
                            source_type=s_type,
                            nuclide=None,
                            source_dsrs_id=dsrs_sources[i],
                        )

                    elif s_type == LicenseSourceType.RECYCLED:
                        license_source = LicenseSource.objects.create(
                            license=license_request,
                            source_type=s_type,
                            nuclide_id=nuclides[i],
                            source_dsrs=None,
                        )
                        for comp in parsed_recycled_components[i]:
                            LicenseSourceComponent.objects.create(
                                license_source=license_source,
                                dsrs_id=comp["dsrsId"],
                                quantity_used=int(comp["qty"]),
                            )

            messages.success(request, _("License request saved successfully."))

            if action == "draft":
                return redirect("license_list")

            return redirect("license_specification", pk=license_request.pk)

        else:
            for err in source_errors:
                messages.error(request, err)

    else:
        forms = get_license_forms()

    existing_sources_data = []

    if license_request_instance is not None:
        existing_sources = (
            license_request_instance.sources
            .select_related("nuclide", "source_dsrs")
            .prefetch_related("components__dsrs")
        )
        for src in existing_sources:
            if src.source_type == LicenseSourceType.NEW:
                existing_sources_data.append({
                    "type": "NEW",
                    "nuclideId": src.nuclide_id,
                    "nuclideLabel": str(src.nuclide),
                })
            elif src.source_type == LicenseSourceType.REUSED:
                existing_sources_data.append({
                    "type": "REUSED",
                    "dsrsId": src.source_dsrs_id,
                    "dsrsLabel": str(src.source_dsrs),
                })
            elif src.source_type == LicenseSourceType.RECYCLED:
                existing_sources_data.append({
                    "type": "RECYCLED",
                    "nuclideId": src.nuclide_id,
                    "nuclideLabel": str(src.nuclide),
                    "components": [
                        {"dsrsId": c.dsrs_id, "dsrsText": str(c.dsrs), "qty": c.quantity_used}
                        for c in src.components.all()
                    ],
                })

    forms["existing_sources_json"] = json.dumps(existing_sources_data)
    forms["license_request_instance"] = license_request_instance

    if license_request_instance is not None:
        forms["existing_attachments"] = license_request_instance.attachments.all()

    return render(request, "operations/license_create.html", forms)


def license_specification(request, pk):

    license_request = get_object_or_404(
        LicenseRequest.objects.select_related("facility"),
        pk=pk,
    )

    queryset = (
        LicenseSource.objects
        .filter(license=license_request)
        .select_related("nuclide", "source_dsrs")
        .prefetch_related("components__dsrs")
        .order_by("specification_order")
    )

    if request.method == "POST":

        formset = LicenseSourceSpecificationFormSet(request.POST, queryset=queryset)

        if formset.is_valid():
            with transaction.atomic():

                for form in formset.forms:

                    obj = form.instance

                    if obj.source_type == LicenseSourceType.REUSED and obj.source_dsrs:

                        dsrs_obj = obj.source_dsrs
                        obj.nuclide = dsrs_obj.Nuclide
                        if not obj.serial_number:
                            obj.serial_number = dsrs_obj.serial_number
                        obj.activity = dsrs_obj.activity_input
                        obj.activity_unit = dsrs_obj.activity_unit
                        obj.activity_date = dsrs_obj.Activity_reference_date

                    obj.save()

                generate_specification(license_request, request.user)

                license_request.status = LicenseStatus.WAITING_CREATOR
                license_request.specification_completed = True
                license_request.save(update_fields=["status", "specification_completed"])

            messages.success(request, _("Specification saved successfully."))

            return redirect("license_sign", pk=license_request.pk)

    else:
        formset = LicenseSourceSpecificationFormSet(queryset=queryset)

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
                "sources__source_dsrs",
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

    if license_request.status == LicenseStatus.WAITING_CREATOR:

        return redirect(
            "license_sign",
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

    # -------------------------------------------------------
    # Current workflow step
    # -------------------------------------------------------

    if license_request.status == LicenseStatus.WAITING_CREATOR:

        current_step = LicenseApproval.ApprovalStep.CREATOR

    elif license_request.status == LicenseStatus.WAITING_MANAGER:

        current_step = LicenseApproval.ApprovalStep.MANAGER

    elif license_request.status == LicenseStatus.WAITING_DEPUTY:

        current_step = LicenseApproval.ApprovalStep.DEPUTY

    else:

        messages.info(
            request,
            _("This license is not waiting for approval."),
        )

        return redirect(
            "license_detail",
            pk=pk,
        )

    # -------------------------------------------------------
    # Generated specification
    # -------------------------------------------------------

    specification = get_object_or_404(

        LicenseAttachment,

        license=license_request,

        attachment_type=LicenseAttachmentType.SPECIFICATION,

    )

    # -------------------------------------------------------
    # Approval record
    # -------------------------------------------------------

    approval = get_object_or_404(

        LicenseApproval,

        license=license_request,

        step=current_step,

    )

    # -------------------------------------------------------
    # Approval history
    # -------------------------------------------------------

    history = (

        LicenseApproval.objects

        .filter(
            license=license_request,
        )

        .order_by(
            "step",
        )

    )

    # -------------------------------------------------------
    # POST
    # -------------------------------------------------------

    if request.method == "POST":

        profile = request.user.profile

        if not profile.signature_image:

            messages.error(
                request,
                _("Please upload your signature image first."),
            )

            return redirect(
                "profile",
            )

        # -----------------------------------------------
        # Sign the specification document
        # -----------------------------------------------

        tmp = tempfile.NamedTemporaryFile(
            suffix=".docx",
            delete=False,
        )

        signer = SpecificationSigner(
            specification.file.path,
        )

        signer.sign(
            profile,
            current_step.name,
        )

        signer.save(
            tmp.name,
        )

        with open(tmp.name, "rb") as f:

            specification.file.save(

                os.path.basename(
                    specification.file.name,
                ),

                File(f),

                save=False,

            )

        specification.save()

        os.remove(
            tmp.name,
        )

        # -----------------------------------------------
        # Save approval
        # -----------------------------------------------
        with transaction.atomic():
            approval.status = LicenseApproval.ApprovalStatus.APPROVED

            approval.approver = request.user

            approval.approved_at = timezone.now()

            approval.save()

            # -----------------------------------------------
            # Next workflow stage
            # -----------------------------------------------

            if current_step == LicenseApproval.ApprovalStep.CREATOR:

                license_request.status = LicenseStatus.WAITING_MANAGER

            elif current_step == LicenseApproval.ApprovalStep.MANAGER:

                license_request.status = LicenseStatus.WAITING_DEPUTY

            elif current_step == LicenseApproval.ApprovalStep.DEPUTY:

                license_request.status = LicenseStatus.CONTRACTS

            license_request.save()

        messages.success(
            request,
            _("Specification signed successfully."),
        )

        # -----------------------------------------------
        # Redirect
        # -----------------------------------------------

        if current_step == LicenseApproval.ApprovalStep.CREATOR:

            return redirect(
                "license_list",
            )

        elif current_step == LicenseApproval.ApprovalStep.MANAGER:

            return redirect(
                "operation_manager_license_list",
            )

        elif current_step == LicenseApproval.ApprovalStep.DEPUTY:

            return redirect(
                "operation_deputy_license_list",
            )

    # -------------------------------------------------------
    # GET
    # -------------------------------------------------------

    return render(

        request,

        "operations/license_sign.html",

        {

            "license": license_request,

            "specification": specification,

            "approval": approval,

            "history": history,

        },

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