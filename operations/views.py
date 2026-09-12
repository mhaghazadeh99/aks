from django.contrib import messages
from django.core.files import File
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render, reverse
from django.utils import timezone
import json
import os
import tempfile
from django.utils.translation import gettext_lazy as _
from dashboard.models import DSRS
from .models import LicenseSourceComponent
from operations.services.signature_service import SpecificationSigner
from .services.workflow import create_license_workflow
from .services.specification_generator import (generate_specification,)
from .forms import (LicenseRequestForm, LicenseAttachmentForm, LicenseSourceSpecificationFormSet,
    LicenseSourceForm,LicenseFacilityForm)
from .models import (LicenseRequest, LicenseAttachment, LicenseAttachmentType,
    LicenseSource,LicenseStatus,LicenseApproval,LicenseSourceType)
from django.utils.dateparse import parse_date as django_parse_date
from datetime import date, datetime, timedelta
import csv
import re
import zipfile
from django.core.files.base import ContentFile
from django.contrib.auth.models import User
from facilities.models import FacilityModel
from reference.models import Nuclides

from dashboard.choices import ActivityUnit
from dashboard.models import DSRS, SOURCE_TYPE, SOURCE_STATUS, MovementType

from contract.models import LicenseContract
from financial.models import LicensePayment
from contract.forms import LicenseContractForm
from financial.forms import LicensePaymentForm
 
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
            "contract",
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

                    obj.license = license_request
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

    license_request = get_object_or_404(LicenseRequest, pk=pk)

    contract, _created = LicenseContract.objects.get_or_create(license=license_request)
    payment, _created = LicensePayment.objects.get_or_create(license=license_request)

    sources_qs = (
        license_request.sources
        .select_related("nuclide", "source_dsrs")
        .order_by("specification_order")
    )

    if request.method == "POST":

        request_form = LicenseRequestForm(request.POST, instance=license_request)
        facility_form = LicenseFacilityForm(request.POST)
        contract_form = LicenseContractForm(request.POST, request.FILES, instance=contract)
        payment_form = LicensePaymentForm(request.POST, instance=payment)
        attachment_form = LicenseAttachmentForm(request.POST, request.FILES)
        source_formset = LicenseSourceSpecificationFormSet(
            request.POST, queryset=sources_qs, prefix="sources"
        )

        if (
            request_form.is_valid()
            and facility_form.is_valid()
            and contract_form.is_valid()
            and payment_form.is_valid()
            and attachment_form.is_valid()
            and source_formset.is_valid()
        ):

            license_request = request_form.save(commit=False)
            license_request.facility = facility_form.cleaned_data["facility"]
            license_request.save()

            contract_obj = contract_form.save()

            uploaded_contract_file = contract_form.cleaned_data.get("contract_attachment")
            if uploaded_contract_file:
                existing_attachment = license_request.attachments.filter(
                    attachment_type=LicenseAttachmentType.CONTRACT
                ).first()
                if existing_attachment:
                    existing_attachment.file = uploaded_contract_file
                    existing_attachment.uploaded_by = request.user
                    existing_attachment.save()
                else:
                    LicenseAttachment.objects.create(
                        license=license_request,
                        attachment_type=LicenseAttachmentType.CONTRACT,
                        file=uploaded_contract_file,
                        uploaded_by=request.user,
                    )

            payment_form.save()

            # -------------------------------------------------
            # Letter / Commitment / Permit / Inquiry / Other —
            # each of these is a separate multi-file upload that
            # ADDS to the existing set, same as on the create page.
            # -------------------------------------------------
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

            # -------------------------------------------------
            # Delete any attachments the user checked
            # -------------------------------------------------
            delete_ids = request.POST.getlist("delete_attachments")
            if delete_ids:
                license_request.attachments.filter(id__in=delete_ids).delete()

            for form in source_formset.deleted_forms:
                if form.instance.pk:
                    form.instance.delete()

            for form in source_formset.forms:
                if form in source_formset.deleted_forms:
                    continue
                if not form.has_changed():
                    continue

                obj = form.instance
                obj.license = license_request

                if obj.source_type == LicenseSourceType.REUSED and obj.source_dsrs:
                    obj.nuclide = obj.source_dsrs.Nuclide

                obj.save()

            messages.success(request, _("License updated successfully."))
            return redirect("license_detail", pk=license_request.pk)

    else:
        request_form = LicenseRequestForm(instance=license_request)
        facility_form = LicenseFacilityForm(initial={"facility": license_request.facility})
        contract_form = LicenseContractForm(instance=contract)
        payment_form = LicensePaymentForm(instance=payment)
        attachment_form = LicenseAttachmentForm()
        source_formset = LicenseSourceSpecificationFormSet(queryset=sources_qs, prefix="sources")

    existing_attachments = license_request.attachments.exclude(
        attachment_type__in=[
            LicenseAttachmentType.SPECIFICATION,
            LicenseAttachmentType.SPECIFICATION_APPENDIX,
        ]
    )

    return render(
        request,
        "operations/license_update.html",
        {
            "license": license_request,
            "request_form": request_form,
            "facility_form": facility_form,
            "contract_form": contract_form,
            "payment_form": payment_form,
            "attachment_form": attachment_form,
            "source_formset": source_formset,
            "existing_attachments": existing_attachments,
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

    
import traceback
def parse_date(value):
    if value is None:
        return None

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    value = str(value).strip()

    if not value:
        return None

    # Excel serial date
    try:
        if value.replace(".", "", 1).isdigit():
            serial = float(value)

            if 1 <= serial <= 2958465:
                return (
                    datetime(1899, 12, 30)
                    + timedelta(days=serial)
                ).date()
    except (ValueError, OverflowError):
        pass

    # Supported date formats
    for fmt in (
        "%Y-%m-%d",  # 2026-08-08
        "%d/%m/%Y",  # 08/08/2026
        "%m/%d/%Y",  # 08/08/2026
        "%Y/%m/%d",  # 2026/08/08
        "%d-%m-%Y",  # 08-08-2026
    ):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue

    raise ValueError(f"Invalid date: {value}")



def decode_csv_bytes(raw_bytes):
    for enc in ("utf-8-sig", "utf-8", "cp1256", "windows-1252"):
        try:
            return raw_bytes.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw_bytes.decode("utf-8", errors="replace")


def license_import_csv(request):

    if request.method != "POST":
        return render(request, "operations/license_import.html")

    uploaded_file = request.FILES.get("csv_file")
    if not uploaded_file:
        messages.error(request, _("No CSV file uploaded."))
        return render(request, "operations/license_import.html")

    zip_contents = {}
    zip_file = request.FILES.get("attachments_zip")

    if zip_file:
        try:
            with zipfile.ZipFile(zip_file) as zf:
                for name in zf.namelist():
                    if name.endswith("/"):
                        continue
                    zip_contents[name.rsplit("/", 1)[-1]] = zf.read(name)
        except zipfile.BadZipFile:
            messages.error(request, _("Uploaded attachments file is not a valid ZIP."))
            return render(request, "operations/license_import.html")

    decoded = decode_csv_bytes(uploaded_file.read())
    reader = csv.DictReader(decoded.splitlines())

    def normalize_key(k):
        k = str(k).strip().lower()
        k = re.sub(r"[^\w]+", "_", k)
        return re.sub(r"_+", "_", k).strip("_")

    def get(normalized, key):
        val = normalized.get(normalize_key(key))
        return str(val).strip() if val not in [None, ""] else None

    def match_choice(value, choices, field_name):
        if value is None:
            raise ValueError(f"{field_name}: empty value")
        value = str(value).strip().lower()
        for key, label in choices:
            if value in [str(key).lower(), str(label).lower()]:
                return key
        raise ValueError(f"{field_name}: invalid value '{value}'")

    ATTACHMENT_COLUMN_MAP = {
        "attachment_letter": LicenseAttachmentType.LETTER,
        "attachment_contract": LicenseAttachmentType.CONTRACT,
    }

    def attach_files(license_request, first_row, warnings_list):
        for column, attachment_type in ATTACHMENT_COLUMN_MAP.items():
            filenames_raw = get(first_row, column)
            if not filenames_raw:
                continue
            for filename in [f.strip() for f in filenames_raw.split(",") if f.strip()]:
                file_bytes = zip_contents.get(filename)
                if file_bytes is None:
                    warnings_list.append(_("Attachment '%(name)s' not found in ZIP — skipped") % {"name": filename})
                    continue
                attachment = LicenseAttachment(
                    license=license_request,
                    attachment_type=attachment_type,
                    uploaded_by=request.user,
                )
                attachment.file.save(filename, ContentFile(file_bytes), save=True)

    def build_new_dsrs(facility_obj, nuclide, activity, activity_unit, serial_number,
                        reference_date, contract_obj, dsrs_source_type):
        """Mirrors fulfillment._create_result_dsrs — used here for NEW/RECYCLED
        rows during import, since those source types create brand-new DSRS
        records rather than referencing existing inventory."""
        return DSRS.objects.create(
            Source_Type=dsrs_source_type,
            Facility=facility_obj,
            Location=(facility_obj.address1 or "")[:20] if hasattr(facility_obj, "address1") else "",
            Responsible_Person=getattr(facility_obj, "responsible_person", None),
            Nuclide=nuclide,
            activity_input=activity,
            activity_unit=activity_unit,
            Activity_reference_date=reference_date,
            serial_number=serial_number,
            source_count=1,
            available_count=1,
            Status=SOURCE_STATUS.IN_USE,
            Status_Date=timezone.now().date(),
            contract=contract_obj,
            created_by=request.user,
        )

    groups = {}
    row_numbers = {}

    for i, row in enumerate(reader, start=1):
        normalized = {normalize_key(k): v for k, v in row.items()}
        letter_number = get(normalized, "letter_number")
        if not letter_number:
            continue
        groups.setdefault(letter_number, []).append(normalized)
        row_numbers.setdefault(letter_number, []).append(i)

    created = 0
    errors = []
    warnings = []

    for letter_number, rows in groups.items():

        try:
            with transaction.atomic():

                first = rows[0]

                facility_name = get(first, "facility")
                if not facility_name:
                    raise ValueError("facility is required")

                facility_obj = FacilityModel.objects.filter(name__iexact=facility_name).first()
                if not facility_obj:
                    raise ValueError(f"Facility '{facility_name}' not found")

                if LicenseRequest.objects.filter(
                    facility=facility_obj, letter_number=letter_number
                ).exists():
                    raise ValueError(
                        f"License with letter_number '{letter_number}' already exists for this facility — skipped"
                    )

                contract_date = parse_date(get(first, "contract_date"))
                letter_date = parse_date(get(first, "letter_date"))
                reference_date = contract_date or letter_date or timezone.now().date()

                # All imported licenses are already fully issued and paid —
                # per your workflow, "Completed" is never set directly; it
                # only happens automatically later, when a DSRS is returned
                # (see DSRS._check_license_completion()).
                license_request = LicenseRequest.objects.create(
                    facility=facility_obj,
                    letter_number=letter_number,
                    letter_date=letter_date,
                    status=LicenseStatus.ISSUED,
                    status_date=reference_date,
                    specification_completed=True,
                    created_by=request.user,
                )

                attach_files(license_request, first, warnings)

                contract_cost = get(first, "cost")
                contract_number = get(first, "contract_number")

                contract_obj = LicenseContract.objects.create(
                    license=license_request,
                    contract_number=contract_number,
                    contract_date=contract_date,
                    contract_cost=contract_cost or None,
                    send_to_financial=True,
                )

                LicensePayment.objects.create(
                    license=license_request,
                    payment_done=True,
                    payment_date=contract_date,
                    amount_paid=contract_cost or None,
                )

                for row in rows:

                    source_type_raw = get(row, "source_type")
                    if not source_type_raw:
                        raise ValueError("source_type is required on every source row")

                    source_type = match_choice(source_type_raw, LicenseSourceType.choices, "source_type")

                    nuclide_name = get(row, "nuclide")
                    if not nuclide_name:
                        raise ValueError("nuclide is required on every source row")

                    nuclide = Nuclides.objects.filter(name__iexact=nuclide_name).first()
                    if not nuclide:
                        raise ValueError(f"Nuclide '{nuclide_name}' not found")

                    activity_raw = get(row, "activity")
                    activity = float(activity_raw) if activity_raw else None

                    activity_unit_raw = get(row, "activity_unit")
                    activity_unit = (
                        match_choice(activity_unit_raw, ActivityUnit.choices, "activity_unit")
                        if activity_unit_raw else "mCi"
                    )

                    serial_number = get(row, "serial_number")
                    quantity_raw = get(row, "quantity")
                    quantity = int(quantity_raw) if quantity_raw else 1
                    source_description = get(row, "source_description") 
                    
                    if source_type == LicenseSourceType.REUSED:

                        if not serial_number:
                            raise ValueError("serial_number is required for a Reused source")

                        # Match BOTH nuclide and serial number — same DSRS, verified two ways
                        existing_dsrs = DSRS.objects.filter(
                            serial_number__iexact=serial_number,
                            Nuclide=nuclide,
                        ).first()

                        if not existing_dsrs:
                            raise ValueError(
                                f"No existing DSRS found matching nuclide '{nuclide_name}' "
                                f"and serial '{serial_number}' for Reuse"
                            )

                        LicenseSource.objects.create(
                            license=license_request,
                            source_type=LicenseSourceType.REUSED,
                            source_dsrs=existing_dsrs,
                            result_dsrs=existing_dsrs,
                            nuclide=nuclide,
                            serial_number=serial_number,
                            activity=activity,
                            activity_unit=activity_unit,
                            activity_date=reference_date,
                            description = source_description or ""
                        )

                        # Mirrors fulfillment.py's REUSED branch: consume the
                        # unit, record the movement, flip Quality Control -> Reused.
                        existing_dsrs.available_count = max(existing_dsrs.available_count - 1, 0)
                        existing_dsrs.contract = contract_obj
                        existing_dsrs.Responsible_Person = facility_obj.responsible_person
                        existing_dsrs.save(update_fields=["available_count", "Responsible_Person", "contract"])

                        existing_dsrs.register_movement(
                            movement_type=MovementType.REUSE,
                            to_facility=facility_obj,
                            contract=contract_obj,
                            performed_by=request.user,
                            quantity=1,
                            remarks=f"Imported reuse for license {letter_number}",
                        )

                    else:
                        # NEW or RECYCLED — create `quantity` brand-new DSRS
                        # records, mirroring what fulfillment.py does when a
                        # license is issued through the normal workflow.
                        dsrs_source_type = (
                            SOURCE_TYPE.NEW if source_type == LicenseSourceType.NEW else SOURCE_TYPE.DSRS
                        )

                        for i in range(quantity):

                            # A shared serial number can't apply to more than
                            # one physical unit — left blank when batching.
                            per_instance_serial = serial_number if quantity == 1 else ""

                            new_dsrs = build_new_dsrs(
                                facility_obj, nuclide, activity, activity_unit,
                                per_instance_serial, reference_date, contract_obj,
                                dsrs_source_type,
                            )

                            LicenseSource.objects.create(
                                license=license_request,
                                source_type=source_type,
                                result_dsrs=new_dsrs,
                                nuclide=nuclide,
                                serial_number=per_instance_serial,
                                activity=activity,
                                activity_unit=activity_unit,
                                activity_date=reference_date,
                                description = source_description or ""
                            )

                created += 1

        except Exception as e:
            first_row_num = row_numbers[letter_number][0]
            errors.append(f"License '{letter_number}' (row {first_row_num}): {str(e)}")

    if created:
        messages.success(request, _("%(count)s license(s) imported successfully.") % {"count": created})
    if warnings:
        for w in warnings:
            messages.warning(request, w)
    if errors:
        for e in errors:
            messages.error(request, e)

    return redirect("license_list")
    

def license_export_csv(
    request,
    ):

    return HttpResponse(
        _("Export CSV")
    )




def license_sign(request, pk):

    license_request = get_object_or_404(LicenseRequest, pk=pk)

    if license_request.status == LicenseStatus.WAITING_CREATOR:
        current_step = LicenseApproval.ApprovalStep.CREATOR
    elif license_request.status == LicenseStatus.WAITING_MANAGER:
        current_step = LicenseApproval.ApprovalStep.MANAGER
    elif license_request.status == LicenseStatus.WAITING_DEPUTY:
        current_step = LicenseApproval.ApprovalStep.DEPUTY
    elif license_request.status == LicenseStatus.WAITING_CEO:
        current_step = LicenseApproval.ApprovalStep.CEO
    else:
        messages.info(request, _("This license is not waiting for approval."))
        return redirect("license_detail", pk=pk)

    specification = get_object_or_404(
        LicenseAttachment,
        license=license_request,
        attachment_type=LicenseAttachmentType.SPECIFICATION,
    )

    approval = get_object_or_404(LicenseApproval, license=license_request, step=current_step)
    history = LicenseApproval.objects.filter(license=license_request).order_by("step")

    if request.method == "POST":

        if current_step == LicenseApproval.ApprovalStep.CEO:
            license_request.discount_notes = request.POST.get("discount_notes", license_request.discount_notes)
            license_request.save(update_fields=["discount_notes"])

        profile = request.user.profile

        if not profile.signature_image:
            messages.error(request, _("Please upload your signature image first."))
            return redirect("profile")

        tmp = tempfile.NamedTemporaryFile(suffix=".docx", delete=False)
        tmp.close()

        signer = SpecificationSigner(specification.file.path)
        signer.sign(profile, current_step.name)
        signer.save(tmp.name)

        with open(tmp.name, "rb") as f:
            specification.file.save(os.path.basename(specification.file.name), File(f), save=False)
        specification.save()
        os.remove(tmp.name)

        approval.status = LicenseApproval.ApprovalStatus.APPROVED
        approval.approver = request.user
        approval.approved_at = timezone.now()
        approval.save()

        if current_step == LicenseApproval.ApprovalStep.CREATOR:
            license_request.status = LicenseStatus.WAITING_MANAGER

        elif current_step == LicenseApproval.ApprovalStep.MANAGER:
            license_request.status = LicenseStatus.WAITING_DEPUTY

        elif current_step == LicenseApproval.ApprovalStep.DEPUTY:
            license_request.status = (
                LicenseStatus.WAITING_CEO if license_request.discount_requested else LicenseStatus.CONTRACTS
            )

        elif current_step == LicenseApproval.ApprovalStep.CEO:
            license_request.status = LicenseStatus.CONTRACTS

        license_request.save()

        messages.success(request, _("Specification signed successfully."))

        if current_step == LicenseApproval.ApprovalStep.CREATOR:
            return redirect("license_list")
        elif current_step == LicenseApproval.ApprovalStep.MANAGER:
            return redirect("operation_manager_license_list")
        elif current_step == LicenseApproval.ApprovalStep.DEPUTY:
            return redirect("operation_ceo_license_list" if license_request.discount_requested else "contract_home")
        elif current_step == LicenseApproval.ApprovalStep.CEO:
            return redirect("contract_home")

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



def operation_ceo_license_list(request):

    queryset = (
        LicenseRequest.objects
        .select_related("facility", "created_by")
        .prefetch_related("sources")
        .filter(status=LicenseStatus.WAITING_CEO)
        .order_by("-created_at")
    )

    search = request.GET.get("search", "")
    if search:
        queryset = queryset.filter(
            Q(facility__name__icontains=search) | Q(letter_number__icontains=search)
        )

    paginator = Paginator(queryset, 15)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "operations/license_queue.html",
        {"page_title": _("CEO"), "page_obj": page_obj, "search": search},
    )