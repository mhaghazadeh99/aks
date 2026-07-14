from django.shortcuts import render, redirect, get_object_or_404
from .models import *
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
from .forms import DSRSForm
from django.db.models import Q

import csv
from django.http import HttpResponse

from django.shortcuts import render


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
                "Account created. Wait for admin approval before logging in."
            )

            return redirect('login')
    else:
        form = UserCreationForm()

    return render(request, 'registration/auth_signup.html', {'form': form})



def add_source(request):

    if not group_required(request.user, ["DSRS Users", "SRS Users"]):
        return HttpResponseForbidden("No access")

    if request.method == "POST":
        print("POST DATA:")
        print(request.POST)
        form = DSRSForm(request.POST, request.FILES, user=request.user)
    

        if form.is_valid():
            obj = form.save(commit=False)
            obj.created_by = request.user

            srs = request.user.groups.filter(name="SRS Users").exists()
            dsrs = request.user.groups.filter(name="DSRS Users").exists()

            if srs and dsrs:
                # user has both → allow selection from form
                obj.Source_Type = form.cleaned_data["Source_Type"]

            elif srs:
                obj.Source_Type = "SRS"

            elif dsrs:
                obj.Source_Type = "DSRS"

            obj.save()   # IMPORTANT

            
            for img in request.FILES.getlist("dsrs_images"):
                DSRSImage.objects.create(dsrs=obj, file=img)
            form.save_m2m()
            return redirect("tables")
    else:
        form = DSRSForm(user=request.user)
    

    return render(request, "dsrs/add_source.html", {"form": form})



def edit_source(request, pk):

    # CHANGED: allow both groups
    if not group_required(request.user, ["DSRS Users", "SRS Users"]):
        return HttpResponseForbidden("No access")

    obj = get_object_or_404(DSRS, pk=pk)

    user_groups = set(request.user.groups.values_list("name", flat=True))

    is_srs_user = "SRS Users" in user_groups
    is_dsrs_user = "DSRS Users" in user_groups

    # normalize value just in case
    source_type = (obj.Source_Type or "").strip()

    # RULE 1: SRS users cannot access DSRS
    if is_srs_user and source_type == "DSRS" and not is_dsrs_user:
        return HttpResponseForbidden("No access to DSRS records")

    # RULE 2: DSRS users cannot access SRS
    if is_dsrs_user and source_type == "SRS" and not is_srs_user:
        return HttpResponseForbidden("No access to SRS records")

    if request.method == "POST":
        form = DSRSForm(request.POST, request.FILES, instance=obj)

        if form.is_valid():
            obj = form.save()

            

            delete_ids = request.POST.getlist("delete_images")
            if delete_ids:
                DSRSImage.objects.filter(
                    id__in=delete_ids,
                    dsrs=obj
                ).delete()
            
            images = request.FILES.getlist("dsrs_images")
            for img in images:
                DSRSImage.objects.create(dsrs=obj, file=img)

            return redirect("tables")
    else:
        form = DSRSForm(instance=obj)

    return render(request, "dsrs/edit_source.html", {"form": form})


def source_list(request):
    sources = DSRS.objects.select_related("Nuclide").all().order_by('-created_at')
    return render(request, "dsrs/source_list.html", {
        "sources": sources
    })




def tables_view(request):

    queryset = DSRS.objects.select_related(
    'Nuclide',
    'created_by'
    ).prefetch_related(
    'dsrs_images'
    )

    # 🔍 SEARCH
    search = request.GET.get("search")
    if search:
        queryset = queryset.filter(
            Q(Facility__icontains=search) |
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
            'error': "Missing nuclide data",
            'values': [],
            'years_range': 10
        })

    # ✅ CURRENT ACTIVITY instead of initial
    A0_bq = source.current_activity_bq()

    if not A0_bq:
        return render(request, 'dsrs/decay_chart.html', {
            'source': source,
            'error': "No current activity available",
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

        response_data = {'message': 'Model updated successfully'}
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

    queryset = DSRS.objects.select_related("Nuclide", "created_by")

    # apply same filters
    keys = request.GET.getlist("key")
    values = request.GET.getlist("value")

    for k, v in zip(keys, values):
        queryset = queryset.filter(**{f"{k}__icontains": v})

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="dsrs.csv"'

    writer = csv.writer(response)

    # -----------------------------
    # HEADER (ALL IMPORTANT FIELDS)
    # -----------------------------
    writer.writerow([
        "ID",
        "Source_Type",
        "Sso_Code",
        "Facility",
        "Origin_Type",
        "Date_received",
        "Origin_Facility",
        "Location",
        "Loc1",
        "Loc2",
        "Num",
        "Status",
        "Status_Date",
        "Responsible_Person",
        "Nuclide",
        "Activity_Input",
        "Activity_Unit",
        "Initial_Activity_Bq",
        "Current_Activity_MCi",
        "Category",
        "Activity_Reference_Date",
        "Serial_Number",
        "Dose_Rate_Surface_uSv",
        "Dose_Rate_1m_uSv",
        "Dose_Rate_Date",
        "Source_State",
        "Contamination_Bq_cm2",
        "Source_Physical_Form",
        "Source_Manufacturer",
        "Source_Model",
        "Source_Practice",
        "Device_Manufacturer",
        "Device_Model",
        "Device_Serial_Number",
        "Container_Type",
        "Dimension",
        "Comment",
        "Created_By",
        "Created_At"
    ])

    # -----------------------------
    # ROWS
    # -----------------------------
    for obj in queryset:
        writer.writerow([
            obj.id,
            obj.Source_Type,
            obj.Sso_Code,
            obj.Facility,
            obj.Origin_Type,
            obj.Date_received,
            obj.Origin_Facility,
            obj.Location,
            obj.Loc1,
            obj.Loc2,
            obj.Num,
            obj.Status,
            obj.Status_Date,
            obj.Responsible_Person,
            str(obj.Nuclide) if obj.Nuclide else None,
            obj.activity_input,
            obj.activity_unit,
            obj.initial_activity_bq,
            obj.current_activity_mci_value,
            obj.category_value,
            obj.Activity_reference_date,
            obj.serial_number,
            obj.Dose_rate_surface_uSv,
            obj.Dose_rate_1m_uSv,
            obj.Dose_rate_measurement_date,
            obj.source_state,
            obj.contamination_bq_cm2,
            obj.Source_Physical_Form,
            obj.Source_Manufacturer,
            obj.Source_Model,
            obj.Source_Practice,
            obj.Device_Manufacturer,
            obj.Device_Model,
            obj.Device_Serial_Number,
            obj.Container_Type,
            obj.Dimension,
            obj.Comment,
            obj.created_by.username if obj.created_by else None,
            obj.created_at
        ])

    return response


# views.py

def import_csv(request):
    if not request.user.groups.filter(name="DSRS Users").exists():
        return HttpResponseForbidden("No access")
        
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=400)

    try:
        data = json.loads(request.body)
        rows = data.get("rows", [])
    except Exception as e:
        return JsonResponse({"error": f"Invalid JSON: {str(e)}"}, status=400)

    created = 0
    errors = []

    def normalize_key(k):
        k = str(k).strip().lower()
        k = re.sub(r"[^\w]+", "_", k)
        k = re.sub(r"_+", "_", k)
        return k.strip("_")

    def get(normalized, *keys):
        for key in keys:
            key = normalize_key(key)
            if key in normalized:
                val = normalized[key]
                if val not in [None, ""]:
                    return str(val).strip()
        return None

    def match_choice(value, choices, field_name):
        if value is None:
            raise ValueError(f"{field_name}: empty value")

        value = str(value).strip().lower()

        for key, label in choices:
            if value in [str(key).lower(), str(label).lower()]:
                return key

        raise ValueError(f"{field_name}: invalid value '{value}'")

    for i, row in enumerate(rows, start=1):
        try:
            normalized = {
                normalize_key(k): v
                for k, v in row.items()
            }

            # -------------------------
            # REQUIRED FIELDS
            # -------------------------
            source_type = get(normalized, "source_type")
            serial = get(normalized, "serial_number")
            facility = get(normalized, "facility")
            origin_type = get(normalized, "origin_type")
            status = get(normalized, "status")
            # status_date_raw = get(normalized, "status_date")
            # status_date = parse_date(status_date_raw) if status_date_raw else None
            location = get(normalized, "location")
            responsible = get(normalized, "responsible_person")

            date_received = parse_date(get(normalized, "date_received"))
            ref_date = parse_date(get(normalized, "activity_reference_date"))

            status_date = parse_date(get(normalized, "status_date"))
            # date_received_raw = get(normalized, "date_received")
            # ref_date_raw = get(normalized, "activity_reference_date")

            # date_received = parse_date(date_received_raw) if date_received_raw else None
            # ref_date = parse_date(ref_date_raw) if ref_date_raw else None

            # -------------------------
            # VALIDATION
            # -------------------------
            missing = []
            if not source_type: missing.append("source_type")
            if not serial: missing.append("serial_Number")
            if not facility: missing.append("Facility")
            if not origin_type: missing.append("Origin_Type")
            if not status: missing.append("Status")
            if not status_date: missing.append("Status_Date")
            if not location: missing.append("Location")
            if not responsible: missing.append("Responsible_Person")
            if not date_received: missing.append("Date_received")
            if not ref_date: missing.append("Activity_reference_date")

            if missing:
                raise ValueError(f"Missing fields: {', '.join(missing)}")

            # -------------------------
            # CHOICES
            # -------------------------
            origin_type = match_choice(origin_type, OriginType.choices, "Origin_Type")
            status = match_choice(status, STATUS.choices, "Status")
            source_type = match_choice(source_type,SOURCE_TYPE.choices,"Source_Type")
            # -------------------------
            # NUCLIDE
            # -------------------------
            nuclide_name = get(normalized, "nuclide")
            nuclide = None
            if nuclide_name:
                nuclide = Nuclides.objects.filter(
                    name__iexact=nuclide_name.strip()
                ).first()

                if not nuclide:
                    raise ValueError(f"Nuclide '{nuclide_name}' not found")

            # -------------------------
            # OPTIONAL CORE FIELDS
            # -------------------------
            activity_input_raw = get(normalized, "activity_input")
            activity_input = None
            if activity_input_raw:
                activity_input = float(activity_input_raw.replace(",", ""))

            activity_unit = get(normalized, "activity_unit") or "Bq"
            sso_code = get(normalized, "sso_code")
            origin_facility = get(normalized, "origin_facility")

            # =====================================================
            # 🔥 NEW FIELDS (ADDED FROM YOUR MODEL)
            # =====================================================

            dose_surface = get(normalized, "dose_rate_surface_usv")
            dose_1m = get(normalized, "dose_rate_1m_usv")
            dose_date_raw = get(normalized, "dose_rate_measurement_date")

            dose_date = parse_date(dose_date_raw) if dose_date_raw else None

            source_state = get(normalized, "source_state")
            contamination = get(normalized, "contamination_bq_cm2")
            source_form = get(normalized, "source_physical_form")

            source_model = get(normalized, "source_model")
            source_practice = get(normalized, "source_practice")

            device_manufacturer = get(normalized, "device_manufacturer")
            device_model = get(normalized, "device_model")
            device_serial = get(normalized, "device_serial_number")

            container_type = get(normalized, "container_type")
            

            dimension = get(normalized, "dimension")
            comment = get(normalized, "comment")

            # attachments cannot be CSV-imported (ignored safely)
            # attachments = get(normalized, "attachments")

            # -------------------------
            # CREATE OBJECT
            # -------------------------
            obj = DSRS(
                Source_Type=source_type,
                Sso_Code=sso_code,
                Origin_Type=origin_type,
                Date_received=date_received,
                Origin_Facility=origin_facility,
                Location=location,
                Status=status,
                Status_Date=status_date,
                Responsible_Person=responsible,
                Nuclide=nuclide,
                activity_input=activity_input,
                activity_unit=activity_unit,
                Activity_reference_date=ref_date,
                serial_number=serial,
                Dose_rate_surface_uSv=dose_surface,
                Dose_rate_1m_uSv=dose_1m,
                Dose_rate_measurement_date=dose_date,

                source_state=source_state,
                contamination_bq_cm2=contamination,
                Source_Physical_Form=source_form,

                Source_Model=source_model,
                Source_Practice=source_practice,

                Device_Manufacturer=device_manufacturer,
                Device_Model=device_model,
                Device_Serial_Number=device_serial,

                Container_Type=container_type,
                Facility=facility,

                Dimension=dimension,

                Comment=comment,

                created_by=request.user
            )
            # obj._skip_contract = True   # 🔥 IMPORTANT FOR IMPORT
            # obj.save()

            created += 1

        except Exception as e:
            errors.append(f"Row {i}: {str(e)}")

    return JsonResponse({
        "created": created,
        "errors": errors
    })


def delete_dsrs_image(request, pk):
    img = get_object_or_404(DSRSImage, pk=pk)

    # optional security check (recommended)
    if not request.user.groups.filter(name="DSRS Users").exists():
        return HttpResponseForbidden("No access")

    dsrs_id = img.dsrs.id
    img.delete()

    return redirect("edit_source", pk=dsrs_id)