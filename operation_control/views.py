import csv

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import F, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _

from . import conf
from . import jalali_utils as ju
from .forms import CalibrationRecordForm, EquipmentForm
from .models import Equipment, EquipmentApplication

# TODO: swap login_required for your project's permission decorators.


# ------------------------------------------------------------------ hub
@login_required
def hub(request):
    today = ju.today()
    active = Equipment.objects.filter(status=Equipment.Status.ACTIVE)
    soon = ju.add_days(today, conf.CALIBRATION_WARNING_DAYS)
    return render(request, "operation_control/hub.html", {
        "calibration_expired": active.filter(due_date__lt=today).count(),
        "calibration_due_soon": active.filter(due_date__gte=today, due_date__lte=soon).count(),
    })


# ------------------------------------------------------------------ equipment list
TEXT_FILTERS = {
    "equipment_id": "equipment_id__icontains",
    "name": "name__icontains",
    "model_name": "model_name__icontains",
    "serial_number": "serial_number__icontains",
    "manufacturer": "manufacturer__icontains",
    "application": "application__name__icontains",
    "current_location": "current_location__icontains",
}
CHOICE_FILTERS = {"status": "status", "center": "center", "current_label": "current_label"}


def _apply_calibration_status(qs, value):
    today = ju.today()
    soon = ju.add_days(today, conf.CALIBRATION_WARNING_DAYS)
    return {
        "expired": lambda: qs.filter(due_date__lt=today),
        "due_soon": lambda: qs.filter(due_date__gte=today, due_date__lte=soon),
        "valid": lambda: qs.filter(due_date__gt=soon),
        "unknown": lambda: qs.filter(due_date__isnull=True),
    }.get(value, lambda: qs)()


def _filtered_equipment(request):
    qs = Equipment.objects.select_related("application")
    term = request.GET.get("search", "").strip()
    if term:
        qs = qs.filter(Q(name__icontains=term) | Q(equipment_id__icontains=term)
                       | Q(serial_number__icontains=term) | Q(model_name__icontains=term))
    for key, value in zip(request.GET.getlist("key"), request.GET.getlist("value")):
        value = value.strip()
        if not value:
            continue
        if key in TEXT_FILTERS:
            qs = qs.filter(**{TEXT_FILTERS[key]: value})
        elif key in CHOICE_FILTERS:
            qs = qs.filter(**{CHOICE_FILTERS[key]: value})
        elif key == "calibration_status":
            qs = _apply_calibration_status(qs, value)
    return qs.order_by(F("due_date").asc(nulls_last=True), "equipment_id")


def _filter_defs():
    text = lambda key, label: {"key": key, "label": str(label), "choices": None}
    choice = lambda key, label, choices: {"key": key, "label": str(label),
                                          "choices": [[str(v), str(l)] for v, l in choices]}
    return [
        text("equipment_id", _("Equipment ID")), text("name", _("Device name")),
        text("model_name", _("Model")), text("serial_number", _("Serial number")),
        text("manufacturer", _("Manufacturer")), text("application", _("Application")),
        choice("status", _("Status"), Equipment.Status.choices),
        choice("center", _("Center"), Equipment.Center.choices),
        text("current_location", _("Current location")),
        choice("current_label", _("Current label"), Equipment.Label.choices),
        choice("calibration_status", _("Calibration status"), Equipment.CalStatus.choices),
    ]


@login_required
def equipment_list(request):
    qs = _filtered_equipment(request)
    size = request.GET.get("size", "25")
    per_page = max(qs.count(), 1) if size == "all" else int(size) if size in ("10", "25", "50") else 25
    page_obj = Paginator(qs, per_page).get_page(request.GET.get("page"))

    params = request.GET.copy()
    params.pop("page", None)
    return render(request, "operation_control/equipment_list.html", {
        "page_obj": page_obj,
        "equipment_list": page_obj.object_list,
        "page_size": size,
        "qs": params.urlencode(),            # keeps filters/search/size when paging
        "filter_defs": _filter_defs(),
        "search": request.GET.get("search", ""),
    })


@login_required
def equipment_export_csv(request):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="equipment_calibration.csv"'
    response.write("\ufeff")                  # BOM so Excel reads Persian correctly
    w = csv.writer(response)
    w.writerow([_("Equipment ID"), _("Device name"), _("Model"), _("Serial number"), _("Manufacturer"),
                _("Application"), _("Status"), _("Center"), _("Current location"),
                _("Last calibration"), _("Calibration period (months)"), _("Calibration due date"),
                _("Days remaining"), _("Calibration status"), _("Current label"), _("Notes / action")])
    for e in _filtered_equipment(request):
        w.writerow([e.equipment_id, e.name, e.model_name, e.serial_number, e.manufacturer,
                    e.application or "", e.get_status_display() + (f" ({e.loan_to})" if e.loan_to else ""),
                    e.get_center_display(), e.current_location,
                    e.last_calibration_display, e.calibration_period_months, e.due_date_display,
                    "" if e.days_remaining is None else e.days_remaining,
                    e.calibration_status.label, e.get_current_label_display(), e.notes])
    return response


# ------------------------------------------------------------------ equipment CRUD
@login_required
def equipment_create(request):
    form = EquipmentForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.created_by = request.user
        obj.save()
        messages.success(request, _("Equipment saved."))
        return redirect("oc_equipment_detail", pk=obj.pk)
    return render(request, "operation_control/equipment_form.html", {"form": form, "title": _("Add Equipment")})


@login_required
def equipment_edit(request, pk):
    obj = get_object_or_404(Equipment, pk=pk)
    form = EquipmentForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("Equipment saved."))
        return redirect("oc_equipment_detail", pk=obj.pk)
    return render(request, "operation_control/equipment_form.html",
                  {"form": form, "title": _("Edit Equipment"), "equipment": obj})


@login_required
def equipment_detail(request, pk):
    obj = get_object_or_404(Equipment.objects.select_related("application"), pk=pk)
    return render(request, "operation_control/equipment_detail.html",
                  {"e": obj, "calibrations": obj.calibrations.all()})


@login_required
def calibration_add(request, pk):
    equipment = get_object_or_404(Equipment, pk=pk)
    form = CalibrationRecordForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        rec = form.save(commit=False)
        rec.equipment, rec.created_by = equipment, request.user
        rec.save()
        messages.success(request, _("Calibration recorded. Due date updated."))
        return redirect("oc_equipment_detail", pk=equipment.pk)
    return render(request, "operation_control/calibration_form.html", {"form": form, "equipment": equipment})
