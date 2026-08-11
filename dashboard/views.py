from django.shortcuts import render, redirect, get_object_or_404
from .models import (
    DSRS,
    DSRSImage,
    SourceMovement,
    MovementAttachment,
    HideShowFilterT,
    ModelFilterT,
    MovementType,
    OriginType,
    SOURCE_STATUS,
    SOURCE_TYPE,
)
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login
from django.core.paginator import Paginator
from django.contrib import messages
import json
from django.http import JsonResponse
from django.utils.dateparse import parse_date
import math
import re
from django.utils import timezone
from django.http import HttpResponseForbidden
from datetime import timedelta
from .forms import DSRSForm, SourceMovementForm
from django.db.models import Q
from facilities.models import FacilityModel
from contract.models import LicenseContract
import csv
from django.http import HttpResponse
from django.utils.translation import gettext_lazy as _
from reference.models import Nuclides


def home(request):

    return render(
        request,
        "home.html"
    )
    
def dsrs_history(request, pk):
    dsrs = get_object_or_404(DSRS, pk=pk)

    history = list(dsrs.history.all().order_by("-history_date"))

    items = []

    for i, record in enumerate(history):
        delta = None

        # Compare with the previous version (older record)
        if i < len(history) - 1:
            delta = record.diff_against(history[i + 1])

        items.append({
            "record": record,
            "delta": delta,
        })

    return render(request, "dashboard/dsrs_history.html", {
        "dsrs": dsrs,
        "items": items,
    })

def group_required(user, groups):
    return user.groups.filter(name__in=groups).exists()


def dashboard_view(request):
    total_items = DSRS.objects.count()
    return render(request, 'dashboard/dashboard.html', {'total_items': total_items})


def charts_view(request):
    chart_type = request.GET.get('type', 'items')

    if chart_type == 'sources':
        data = DSRS.objects.all()
    # else:
    #     data = Item.objects.all()

    return render(request, 'dashboard/charts.html', {
        'data': data,
        'chart_type': chart_type,
    })



def register_view(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.is_active = False
            user.save()

            messages.success(
            request,
            _("Account created. Wait for admin approval before logging in.")
        )
            return redirect('login')
    else:
        form = UserCreationForm()

    return render(request, 'registration/auth_signup.html', {'form': form})



def add_source(request):
    

    

    if request.method == "POST":

        form = DSRSForm(request.POST, request.FILES, user=request.user)
        movement_form = SourceMovementForm(request.POST)

        if form.is_valid() and movement_form.is_valid():

            srs = request.user.groups.filter(name="SRS Users").exists()
            dsrs = request.user.groups.filter(name="DSRS Users").exists()
            if srs and dsrs:
                resolved_source_type = form.cleaned_data.get("Source_Type")
            elif srs:
                resolved_source_type = SOURCE_TYPE.NEW
            else:
                resolved_source_type = SOURCE_TYPE.DSRS

            quantity = movement_form.cleaned_data.get("source_count") or 1

            # source_count / available_count describe the internal makeup of ONE
            # device (e.g. a seed source device with many recyclable sub-sources)
            # — not how many DSRS rows to create. That's what `quantity` above is
            # for. If available_count is left blank, default it to source_count
            # (a freshly added device starts with everything available).
            device_source_count = form.cleaned_data.get("source_count") or 1
            device_available_count = form.cleaned_data.get("available_count")
            if not device_available_count:
                device_available_count = device_source_count

            base_data = form.cleaned_data.copy()
            base_data.pop("Source_Type", None)
            base_data.pop("source_count", None)
            base_data.pop("available_count", None)

            created_sources = []

            for _ in range(quantity):

                source = DSRS(
                    **base_data,
                    Source_Type=resolved_source_type,
                    source_count=device_source_count,
                    available_count=device_available_count,
                    created_by=request.user,
                )
                source.save()
                created_sources.append(source)


            # Images go on the first instance only — the others can get
            # their own photos individually later via the edit page.
            if created_sources:
                for img in request.FILES.getlist("dsrs_images"):
                    DSRSImage.objects.create(dsrs=created_sources[0], file=img)

            # -----------------------------
            # ONE MOVEMENT PER INSTANCE
            # -----------------------------
            movement_attachments = request.FILES.getlist("movement_attachments")

            for source in created_sources:

                movement = source.register_movement(
                    movement_type=movement_form.cleaned_data["movement_type"],
                    to_facility=movement_form.cleaned_data["to_facility"],
                    from_facility=movement_form.cleaned_data.get("from_facility"),
                    contract=source.contract,   # None at creation — correct, nothing to inherit yet
                    performed_by=request.user,
                    quantity=1,
                    remarks=movement_form.cleaned_data.get("remarks", ""),
                    movement_date=movement_form.cleaned_data["movement_date"],
                )

                for f in movement_attachments:
                    f.seek(0)   # same uploaded file reused across N movements — reset pointer each time
                    MovementAttachment.objects.create(movement=movement, file=f)

            return redirect("tables")

    else:

        form = DSRSForm(user=request.user)
        movement_form = SourceMovementForm()

    return render(
        request,
        "dsrs/add_source.html",
        {
            "form": form,
            "movement_form": movement_form,
        }
    )
    

def edit_source(request, pk):

    obj = get_object_or_404(DSRS, pk=pk)

    user_groups = set(request.user.groups.values_list("name", flat=True))
    is_srs_user = "SRS Users" in user_groups
    is_dsrs_user = "DSRS Users" in user_groups
    source_type = (obj.Source_Type or "").strip()

    if is_srs_user and source_type == "DSRS" and not is_dsrs_user:
        return HttpResponseForbidden(_("No access to DSRS records"))

    if is_dsrs_user and source_type == SOURCE_TYPE.NEW and not is_srs_user:
        return HttpResponseForbidden(_("No access to SRS records"))

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "add_movement":

            form = DSRSForm(instance=obj, user=request.user)
            movement_form = SourceMovementForm(request.POST)   # no request.FILES needed now — field removed from form

            if movement_form.is_valid():

                movement = obj.register_movement(
                    movement_type=movement_form.cleaned_data["movement_type"],
                    to_facility=movement_form.cleaned_data["to_facility"],
                    from_facility=movement_form.cleaned_data.get("from_facility"),
                    contract=obj.contract,   # inherited automatically, never chosen manually
                    performed_by=request.user,
                    quantity=movement_form.cleaned_data.get("source_count"),
                    remarks=movement_form.cleaned_data.get("remarks", ""),
                    movement_date=movement_form.cleaned_data["movement_date"],
                )

                for f in request.FILES.getlist("movement_attachments"):
                    MovementAttachment.objects.create(movement=movement, file=f)

                messages.success(request, _("Movement recorded successfully."))
                return redirect("edit_source", pk=obj.pk)

        else:

            form = DSRSForm(request.POST, request.FILES, instance=obj, user=request.user)
            movement_form = SourceMovementForm(initial={"from_facility": obj.Facility})

            if form.is_valid():

                obj = form.save(commit=False)
                obj.save()

                delete_ids = request.POST.getlist("delete_images")
                if delete_ids:
                    DSRSImage.objects.filter(
                        id__in=delete_ids,
                        dsrs=obj
                    ).delete()

                images = request.FILES.getlist("dsrs_images")
                for img in images:
                    DSRSImage.objects.create(dsrs=obj, file=img)

                messages.success(request, _("Source updated successfully."))

                return redirect("tables")

    else:
        form = DSRSForm(instance=obj, user=request.user)
        movement_form = SourceMovementForm(initial={"from_facility": obj.Facility})

    movements = (
        obj.movements
        .select_related("from_facility", "to_facility", "performed_by")
        .order_by("-movement_date", "-id")
    )

    return render(request, "dsrs/edit_source.html", {
        "form": form,
        "movement_form": movement_form,
        "movements": movements,
        "source": obj,
    })
    




def source_list(request):
    sources = DSRS.objects.select_related("Nuclide").all().order_by('-created_at')
    return render(request, "dsrs/source_list.html", {
        "sources": sources
    })




def tables_view(request):

    queryset = DSRS.objects.select_related(
                'Nuclide',
                'created_by',
                'Facility'
            ).prefetch_related(
                'dsrs_images',
                'movements__from_facility',
                'movements__to_facility',
                'movements__attachments',   # added
            ).order_by("-created_at")

    # 🔍 SEARCH
    search = request.GET.get("search")
    if search:
        queryset = queryset.filter(
            Q(Facility__name__icontains=search) |
            Q(Status__icontains=search) |
            Q(Nuclide__name__icontains=search) |
            Q(Source_Type__icontains=search) |
            Q(Source_Model__icontains=search) |
            Q(Device_Model__icontains=search) |
            Q(Container_Type__icontains=search)
        )

    # 🎯 FILTERS
    keys = request.GET.getlist("key")
    values = request.GET.getlist("value")

    for k, v in zip(keys, values):
        if v:
            queryset = queryset.filter(**{f"{k}__icontains": v})

    # 📄 PAGE SIZE
    size = request.GET.get("size", "10")

    if size == "all":
        page_size = max(queryset.count(), 1)   # show everything in one page
    else:
        try:
            page_size = max(1, int(size))
        except (ValueError, TypeError):
            page_size = 10

    # 📌 PAGINATION
    paginator = Paginator(queryset, page_size)
    page = request.GET.get("page")
    page_obj = paginator.get_page(page)

    return render(request, "dashboard/tables.html", context = {
    "sources": page_obj,
    "page_obj": page_obj,
    "page_size": size,
    "search": search,
    "keys": keys,
    "values": values,
    })



def save_filter(request):
    if request.method == "POST":
        key = request.POST.get("key")
        value = request.POST.get("value")

        ModelFilterT.objects.update_or_create(
            parent="dsrs",
            key=key,
            defaults={"value": value}
        )

    return redirect("tables")
    
def save_column_visibility(request):
    if request.method == "POST":
        data = json.loads(request.body)

        HideShowFilterT.objects.update_or_create(
            parent="dsrs",
            key=data["key"],
            defaults={"value": data["value"]}
        )

        return JsonResponse({"status": "ok"})

    return JsonResponse({"error": "bad"}, status=400)


def get_column_visibility(request):
    data = list(
        HideShowFilterT.objects.filter(parent="dsrs").values("key", "value")
    )
    return JsonResponse(data, safe=False)



def decay_chart_view(request, pk):
    source = get_object_or_404(DSRS, pk=pk)
    nuclide = source.Nuclide

    if not nuclide or not nuclide.half_life:
        return render(request, 'dsrs/decay_chart.html', {
            'source': source,
            'error': _("Missing nuclide data"),
            'values': [],
            'years_range': 10
        })

    # ✅ CURRENT ACTIVITY instead of initial
    A0_bq = source.current_activity_bq()

    if not A0_bq:
        return render(request, 'dsrs/decay_chart.html', {
            'source': source,
            'error': _("No current activity available"),
            'values': [],
            'years_range': 10
        })

    T_half = nuclide.half_life
    lam = math.log(2) / T_half

    years_range = int(request.GET.get("years", 10))

    years = list(range(0, years_range + 1))
    values_mci = []

    BQ_TO_MCI = 1 / 3.7e7

    for y in years:
        t = y * 365.25 * 86400
        A_t_bq = A0_bq * math.exp(-lam * t)

        A_t_mci = A_t_bq * BQ_TO_MCI
        values_mci.append(A_t_mci)

    return render(request, 'dsrs/decay_chart.html', {
        'source': source,
        'days': years,
        'values': values_mci,
        'years_range': years_range
    })


def create_hide_show_filter(request, model_name):
    model_name = model_name.lower()
    if request.method == "POST":
        data_str = list(request.POST.keys())[0]
        data = json.loads(data_str)

        HideShowFilterT.objects.update_or_create(
            parent=model_name,
            key=data.get('key'),
            defaults={'value': data.get('value')}
        )

        response_data = {'message': _('Model updated successfully')}
        return JsonResponse(response_data)

    return JsonResponse({'error': 'Invalid request'}, status=400)

def get_hide_show(request, model_name):
    data = list(
        HideShowFilterT.objects
        .filter(parent=model_name)
        .values('key', 'value')
    )
    return JsonResponse(data, safe=False)


def export_csv(request):

    queryset = (
        DSRS.objects
        .select_related("Nuclide", "created_by", "Facility", "contract")
        .prefetch_related("movements__from_facility")
    )

    keys = request.GET.getlist("key")
    values = request.GET.getlist("value")
    for k, v in zip(keys, values):
        queryset = queryset.filter(**{f"{k}__icontains": v})

    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = 'attachment; filename="dsrs.csv"'

    writer = csv.writer(response)

    writer.writerow([
        "ID", "Contract_Number", "Source_Type", "Sso_Code", "Facility", "Origin_Facility",
        "Origin_Type", "Date_received", "Is_Divisible", "Source_Count", "Available_Count",
        "Location", "Status", "Status_Date", "Responsible_Person", "Nuclide",
        "Activity_Input", "Activity_Unit", "Initial_Activity_Bq", "Current_Activity_MCi",
        "Category", "Activity_Reference_Date", "Serial_Number", "Dose_Rate_Surface_uSv",
        "Dose_Rate_1m_uSv", "Dose_Rate_Date", "Source_State", "Contamination_Bq_cm2",
        "Source_Physical_Form", "Source_Manufacturer", "Source_Model", "Source_Practice",
        "Device_Manufacturer", "Device_Model", "Device_Serial_Number", "Container_Type",
        "Dimension", "Comment", "Created_By", "Created_At",
    ])

    for obj in queryset:

        first_movement = obj.movements.order_by("movement_date", "id").first()
        origin_facility = first_movement.from_facility if first_movement else None

        writer.writerow([
            obj.id, obj.contract_number, obj.Source_Type, obj.Sso_Code,
            obj.Facility.name if obj.Facility else None,
            origin_facility.name if origin_facility else None,
            obj.Origin_Type, obj.Date_received, obj.is_divisible, obj.source_count,
            obj.available_count, obj.Location, obj.Status, obj.Status_Date,
            obj.Responsible_Person, str(obj.Nuclide) if obj.Nuclide else None,
            obj.activity_input, obj.activity_unit, obj.initial_activity_bq,
            obj.current_activity_mci_value, obj.category_value, obj.Activity_reference_date,
            obj.serial_number, obj.Dose_rate_surface_uSv, obj.Dose_rate_1m_uSv,
            obj.Dose_rate_measurement_date, obj.source_state, obj.contamination_bq_cm2,
            obj.Source_Physical_Form, obj.Source_Manufacturer, obj.Source_Model,
            obj.Source_Practice, obj.Device_Manufacturer, obj.Device_Model,
            obj.Device_Serial_Number, obj.Container_Type, obj.Dimension, obj.Comment,
            obj.created_by.username if obj.created_by else None, obj.created_at,
        ])

    return response


def import_csv(request):
    """Server-side CSV import. Accepts a multipart file upload directly."""

    if request.method != "POST":
        return JsonResponse({"error": _("POST required")}, status=400)

    uploaded_file = request.FILES.get("csv_file")
    if not uploaded_file:
        return JsonResponse({"error": _("No file uploaded")}, status=400)

    decoded = uploaded_file.read().decode("utf-8-sig")
    reader = csv.DictReader(decoded.splitlines())

    created = 0
    errors = []

    def normalize_key(k):
        k = str(k).strip().lower()
        k = re.sub(r"[^\w]+", "_", k)
        return re.sub(r"_+", "_", k).strip("_")

    def get(normalized, *keys):
        for key in keys:
            key = normalize_key(key)
            if key in normalized and normalized[key] not in [None, ""]:
                return str(normalized[key]).strip()
        return None

    def match_choice(value, choices, field_name):
        if value is None:
            raise ValueError(f"{field_name}: empty value")
        value = str(value).strip().lower()
        for key, label in choices:
            if value in [str(key).lower(), str(label).lower()]:
                return key
        raise ValueError(f"{field_name}: invalid value '{value}'")

    for i, row in enumerate(reader, start=1):
        try:
            normalized = {normalize_key(k): v for k, v in row.items()}

            source_type = get(normalized, "source_type")
            serial = get(normalized, "serial_number")
            facility_name = get(normalized, "facility")
            origin_facility_name = get(normalized, "origin_facility")
            origin_type = get(normalized, "origin_type")
            status = get(normalized, "status")
            location = get(normalized, "location")
            responsible = get(normalized, "responsible_person")
            date_received = parse_date(get(normalized, "date_received"))
            ref_date = parse_date(get(normalized, "activity_reference_date"))
            status_date = parse_date(get(normalized, "status_date"))

            missing = []
            if not source_type: missing.append("source_type")
            if not serial: missing.append("serial_number")
            if not facility_name: missing.append("facility")
            if not origin_type: missing.append("origin_type")
            if not status: missing.append("status")

            if missing:
                raise ValueError(f"Missing fields: {', '.join(missing)}")

            origin_type = match_choice(origin_type, OriginType.choices, "Origin_Type")
            status = match_choice(status, SOURCE_STATUS.choices, "Status")
            source_type = match_choice(source_type, SOURCE_TYPE.choices, "Source_Type")

            facility_obj = FacilityModel.objects.filter(name__iexact=facility_name).first()
            if not facility_obj:
                raise ValueError(_("Facility '%(name)s' not found") % {"name": facility_name})

            origin_facility_obj = None
            if origin_facility_name:
                origin_facility_obj = FacilityModel.objects.filter(
                    name__iexact=origin_facility_name
                ).first()
                if not origin_facility_obj:
                    raise ValueError(_("Origin Facility '%(name)s' not found") % {"name": origin_facility_name})

            nuclide_name = get(normalized, "nuclide")
            nuclide = None
            if nuclide_name:
                nuclide = Nuclides.objects.filter(name__iexact=nuclide_name).first()
                if not nuclide:
                    raise ValueError(_("Nuclide '%(name)s' not found") % {"name": nuclide_name})

            contract_number = get(normalized, "contract_number")
            contract_obj = None
            if contract_number:
                contract_obj = LicenseContract.objects.filter(
                    contract_number__iexact=contract_number
                ).first()
                if not contract_obj:
                    raise ValueError(_("Contract '%(number)s' not found") % {"number": contract_number})

            activity_input_raw = get(normalized, "activity_input")
            activity_input = float(activity_input_raw.replace(",", "")) if activity_input_raw else None

            source_count_raw = get(normalized, "source_count")
            available_count_raw = get(normalized, "available_count")
            is_divisible_raw = get(normalized, "is_divisible")

            obj = DSRS(
                contract=contract_obj,
                Source_Type=source_type,
                Sso_Code=get(normalized, "sso_code"),
                Origin_Type=origin_type,
                Date_received=date_received,
                Facility=facility_obj,
                Location=location,
                Status=status,
                Status_Date=status_date,
                Responsible_Person=responsible,
                Nuclide=nuclide,
                activity_input=activity_input,
                activity_unit=get(normalized, "activity_unit") or "Bq",
                Activity_reference_date=ref_date,
                serial_number=serial,
                is_divisible=(is_divisible_raw or "").lower() in ("true", "1", "yes"),
                source_count=int(source_count_raw) if source_count_raw else 1,
                available_count=int(available_count_raw) if available_count_raw else 1,
                Dose_rate_surface_uSv=get(normalized, "dose_rate_surface_usv"),
                Dose_rate_1m_uSv=get(normalized, "dose_rate_1m_usv"),
                Dose_rate_measurement_date=parse_date(get(normalized, "dose_rate_measurement_date")),
                source_state=get(normalized, "source_state"),
                contamination_bq_cm2=get(normalized, "contamination_bq_cm2"),
                Source_Physical_Form=get(normalized, "source_physical_form"),
                Source_Manufacturer=get(normalized, "source_manufacturer"),
                Source_Model=get(normalized, "source_model"),
                Source_Practice=get(normalized, "source_practice"),
                Device_Manufacturer=get(normalized, "device_manufacturer"),
                Device_Model=get(normalized, "device_model"),
                Device_Serial_Number=get(normalized, "device_serial_number"),
                Container_Type=get(normalized, "container_type"),
                Dimension=get(normalized, "dimension"),
                Comment=get(normalized, "comment"),
                created_by=request.user,
            )
            obj.save()

            # Backfill an origin movement for history/export purposes only —
            # NOT via register_movement(), since that would overwrite the
            # Status/Facility we just explicitly imported above.
            if origin_facility_obj:
                SourceMovement.objects.create(
                    source=obj,
                    movement_type=MovementType.RECEIVE,
                    from_facility=origin_facility_obj,
                    to_facility=facility_obj,
                    movement_date=date_received or timezone.now().date(),
                    source_count=1,
                    performed_by=request.user,
                    remarks="Imported origin record",
                )

            created += 1

        except Exception as e:
            errors.append(f"Row {i}: {str(e)}")

    return JsonResponse({"created": created, "errors": errors})




def delete_dsrs_image(request, pk):
    img = get_object_or_404(DSRSImage, pk=pk)


    dsrs_id = img.dsrs.id
    img.delete()

    return redirect("edit_source", pk=dsrs_id)