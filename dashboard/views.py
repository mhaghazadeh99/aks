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
import io 
from django.db import transaction
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

FIELD_FILTER_MAP = {
    "Source_Type": "Source_Type",
    "Sso_Code": "Sso_Code",
    "Contract_Number": "contract__contract_number",
    "source_count": "source_count",
    "available_count": "available_count",
    "Facility": "Facility__name",
    "Origin_Type": "Origin_Type",
    "Date_received": "Date_received",
    "Origin_Facility": "movements__from_facility__name",
    "Location": "Location",
    "Status": "Status",
    "Status_Date": "Status_Date",
    "Responsible_Person": "Responsible_Person",
    "Nuclide": "Nuclide__name",
    "activity_input": "activity_input",
    "activity_unit": "activity_unit",
    "Activity_reference_date": "Activity_reference_date",
    "serial_number": "serial_number",
    "Dose_rate_surface_uSv": "Dose_rate_surface_uSv",
    "Dose_rate_1m_uSv": "Dose_rate_1m_uSv",
    "Dose_rate_measurement_date": "Dose_rate_measurement_date",
    "source_state": "source_state",
    "contamination_bq_cm2": "contamination_bq_cm2",
    "Source_Physical_Form": "Source_Physical_Form",
    "Source_Manufacturer": "Source_Manufacturer",
    "Source_Model": "Source_Model",
    "Source_Practice": "Source_Practice",
    "Device_Manufacturer": "Device_Manufacturer",
    "Device_Model": "Device_Model",
    "Device_Serial_Number": "Device_Serial_Number",
    "Container_Type": "Container_Type",
    "Dimension": "Dimension",
    "Comment": "Comment",
    "created_by": "created_by__username",
    "created_at": "created_at",
}

# Counts are numeric, so a global text search over them only adds noise.
SEARCH_LOOKUPS = set(FIELD_FILTER_MAP.values()) - {"source_count", "available_count"}


def _float_or_none(v):
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def filter_dsrs_queryset(request, queryset):
    """Single source of truth for search + filters + activity range.
    Used by both tables_view and export_csv."""

    search = (request.GET.get("search") or "").strip()
    if search:
        q = Q()
        for lookup in SEARCH_LOOKUPS:
            q |= Q(**{f"{lookup}__icontains": search})
        queryset = queryset.filter(q)

    act_min = _float_or_none(request.GET.get("activity_min"))
    act_max = _float_or_none(request.GET.get("activity_max"))

    filtered = False
    for k, v in zip(request.GET.getlist("key"), request.GET.getlist("value")):
        v = v.strip()
        if k == "current_activity":
            lo = _float_or_none(v)
            hi = _float_or_none(request.GET.get("value_max"))
            if lo is not None:
                act_min = lo
            if hi is not None:
                act_max = hi
            continue
        lookup = FIELD_FILTER_MAP.get(k)
        if not v or not lookup:
            continue
        queryset = queryset.filter(**{f"{lookup}__icontains": v})
        filtered = True

    if search or filtered:
        queryset = queryset.distinct()

    # Current activity is computed in Python (decay), so it can't be filtered in SQL.
    if act_min is not None or act_max is not None:
        ids = []
        for s in queryset.prefetch_related(None).select_related("Nuclide"):
            a = s.current_activity_mci()
            if a is None:
                continue
            if act_min is not None and a < act_min:
                continue
            if act_max is not None and a > act_max:
                continue
            ids.append(s.pk)
        queryset = queryset.filter(pk__in=ids)

    return queryset
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
        "Nuclide", "created_by", "Facility"
    ).prefetch_related(
        "dsrs_images",
        "movements__from_facility",
        "movements__to_facility",
        "movements__attachments",
    ).order_by("-created_at")

    queryset = filter_dsrs_queryset(request, queryset)

    size = request.GET.get("size", "10")
    if size == "all":
        page_size = max(queryset.count(), 1)
    else:
        try:
            page_size = max(1, int(size))
        except (ValueError, TypeError):
            page_size, size = 10, "10"

    paginator = Paginator(queryset, page_size)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(request, "dashboard/tables.html", {
        "sources": page_obj,
        "page_obj": page_obj,
        "page_size": size,
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
        .order_by("-created_at")
    )
    queryset = filter_dsrs_queryset(request, queryset)

    response = HttpResponse(content_type="text/csv; charset=utf-8-sig")
    response["Content-Disposition"] = 'attachment; filename="dsrs.csv"'
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
        movements = list(obj.movements.all())   # prefetched; Meta ordering = date, id
        origin_facility = movements[0].from_facility if movements else None

        writer.writerow([
            obj.id, obj.contract_number, obj.Source_Type, obj.Sso_Code,
            obj.Facility.name if obj.Facility else None,
            origin_facility.name if origin_facility else None,
            obj.Origin_Type, obj.Date_received, obj.is_divisible, obj.source_count,
            obj.available_count, obj.Location, obj.Status, obj.Status_Date,
            obj.Responsible_Person,
            obj.Nuclide.name if obj.Nuclide else None,
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
    """Upsert by (Facility, Nuclide, serial_number). Blank CSV cells never
    overwrite existing values."""

    if request.method != "POST":
        return JsonResponse({"error": _("POST required")}, status=400)

    uploaded_file = request.FILES.get("csv_file")
    if not uploaded_file:
        return JsonResponse({"error": _("No file uploaded")}, status=400)

    decoded = uploaded_file.read().decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(decoded))

    created = updated = unchanged = 0
    errors = []

    def normalize_key(k):
        k = str(k).strip().lower()
        k = re.sub(r"[^\w]+", "_", k)
        return re.sub(r"_+", "_", k).strip("_")

    def get(normalized, *keys):
        for key in keys:
            key = normalize_key(key)
            if key in normalized and normalized[key] not in [None, ""]:
                return str(normalized[key]).strip() or None
        return None

    def get_date(normalized, *keys):
        raw = get(normalized, *keys)
        if raw is None:
            return None
        d = parse_date(raw)
        if d is None:
            raise ValueError(f"{keys[0]}: invalid date '{raw}' (use YYYY-MM-DD)")
        return d

    def get_float(normalized, *keys):
        raw = get(normalized, *keys)
        if raw is None:
            return None
        try:
            return float(raw.replace(",", ""))
        except ValueError:
            raise ValueError(f"{keys[0]}: invalid number '{raw}'")

    def get_int(normalized, *keys):
        raw = get(normalized, *keys)
        return int(float(raw)) if raw is not None else None

    def match_choice(value, choices, field_name):
        if value is None:
            return None
        v = str(value).strip().lower()
        for key, label in choices:
            if v in [str(key).lower(), str(label).lower()]:
                return key
        raise ValueError(f"{field_name}: invalid value '{value}'")

    for i, row in enumerate(reader, start=1):
        try:
            n = {normalize_key(k): v for k, v in row.items() if k}

            serial = get(n, "serial_number")
            facility_name = get(n, "facility")
            nuclide_name = get(n, "nuclide")

            missing = [name for name, val in
                       (("serial_number", serial), ("facility", facility_name)) if not val]
            if missing:
                raise ValueError(f"Missing fields: {', '.join(missing)}")

            facility_obj = FacilityModel.objects.filter(name__iexact=facility_name).first()
            if not facility_obj:
                raise ValueError(_("Facility '%(name)s' not found") % {"name": facility_name})

            nuclide = None
            if nuclide_name:
                nuclide = Nuclides.objects.filter(name__iexact=nuclide_name).first()
                if not nuclide:
                    raise ValueError(_("Nuclide '%(name)s' not found") % {"name": nuclide_name})

            origin_facility_obj = None
            origin_facility_name = get(n, "origin_facility")
            if origin_facility_name:
                origin_facility_obj = FacilityModel.objects.filter(
                    name__iexact=origin_facility_name).first()
                if not origin_facility_obj:
                    raise ValueError(_("Origin Facility '%(name)s' not found")
                                     % {"name": origin_facility_name})

            contract_obj = None
            contract_number = get(n, "contract_number")
            if contract_number:
                contract_obj = LicenseContract.objects.filter(
                    contract_number__iexact=contract_number).first()
                if not contract_obj:
                    raise ValueError(_("Contract '%(number)s' not found")
                                     % {"number": contract_number})

            is_div_raw = get(n, "is_divisible")

            fields = {
                "Source_Type": match_choice(get(n, "source_type"), SOURCE_TYPE.choices, "Source_Type"),
                "Origin_Type": match_choice(get(n, "origin_type"), OriginType.choices, "Origin_Type"),
                "Status": match_choice(get(n, "status"), SOURCE_STATUS.choices, "Status"),
                "Sso_Code": get(n, "sso_code"),
                "Date_received": get_date(n, "date_received"),
                "Location": get(n, "location"),
                "Status_Date": get_date(n, "status_date"),
                "Responsible_Person": get(n, "responsible_person"),
                "activity_input": get_float(n, "activity_input"),
                "activity_unit": get(n, "activity_unit"),
                "Activity_reference_date": get_date(n, "activity_reference_date"),
                "is_divisible": (is_div_raw.lower() in ("true", "1", "yes")) if is_div_raw else None,
                "source_count": get_int(n, "source_count"),
                "available_count": get_int(n, "available_count"),
                "Dose_rate_surface_uSv": get(n, "dose_rate_surface_usv"),
                "Dose_rate_1m_uSv": get(n, "dose_rate_1m_usv"),
                "Dose_rate_measurement_date": get_date(
                    n, "dose_rate_measurement_date", "dose_rate_date"),
                "source_state": get(n, "source_state"),
                "contamination_bq_cm2": get(n, "contamination_bq_cm2"),
                "Source_Physical_Form": get(n, "source_physical_form"),
                "Source_Manufacturer": get(n, "source_manufacturer"),
                "Source_Model": get(n, "source_model"),
                "Source_Practice": get(n, "source_practice"),
                "Device_Manufacturer": get(n, "device_manufacturer"),
                "Device_Model": get(n, "device_model"),
                "Device_Serial_Number": get(n, "device_serial_number"),
                "Container_Type": get(n, "container_type"),
                "Dimension": get(n, "dimension"),
                "Comment": get(n, "comment"),
            }
            # Blank cells are "no change", never "erase". Convert to proper types
            # up front so comparison and validation work for both paths.
            fields = {
                k: DSRS._meta.get_field(k).to_python(v)
                for k, v in fields.items() if v is not None
            }

            with transaction.atomic():
                matches = list(DSRS.objects.filter(
                    Facility=facility_obj,
                    Nuclide=nuclide,                      # None -> IS NULL
                    serial_number__iexact=serial,
                )[:2])

                if len(matches) > 1:
                    raise ValueError(
                        f"More than one existing record for {facility_name} / "
                        f"{nuclide_name or '-'} / {serial}")

                if matches:
                    obj = matches[0]
                    changed = False
                    for name, new in fields.items():
                        if getattr(obj, name) != new:
                            setattr(obj, name, new)
                            changed = True
                    if contract_obj and obj.contract_id != contract_obj.pk:
                        obj.contract = contract_obj
                        changed = True
                    if changed:
                        obj.save()
                        updated += 1
                    else:
                        unchanged += 1
                else:
                    required = [k for k in ("Source_Type", "Origin_Type", "Status")
                                if k not in fields]
                    if required:
                        raise ValueError(
                            f"New record needs: {', '.join(required)}")
                    obj = DSRS(
                        Facility=facility_obj,
                        Nuclide=nuclide,
                        serial_number=serial,
                        contract=contract_obj,
                        created_by=request.user,
                        **fields,
                    )
                    obj.save()
                    created += 1

                # Origin movement for history/export only, and only when the
                # record has none yet (so re-imports don't duplicate it).
                # Not via register_movement(): that would overwrite the
                # imported Status/Facility.
                if origin_facility_obj and not obj.movements.exists():
                    SourceMovement.objects.create(
                        source=obj,
                        movement_type=MovementType.RECEIVE,
                        from_facility=origin_facility_obj,
                        to_facility=facility_obj,
                        movement_date=fields.get("Date_received") or timezone.now().date(),
                        source_count=1,
                        performed_by=request.user,
                        remarks="Imported origin record",
                    )

        except Exception as e:
            errors.append(f"Row {i}: {e}")

    return JsonResponse({
        "created": created,
        "updated": updated,
        "unchanged": unchanged,
        "errors": errors,
    })


def delete_dsrs_image(request, pk):
    img = get_object_or_404(DSRSImage, pk=pk)


    dsrs_id = img.dsrs.id
    img.delete()

    return redirect("edit_source", pk=dsrs_id)