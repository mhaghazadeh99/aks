import csv

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import ProtectedError
from django.template.loader import render_to_string
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator
from django.db.models import F, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _

from . import conf, logic
from . import jalali_utils as ju
from .forms import CalibrationRecordForm, EquipmentForm
from .models import CalibrationRecord, Equipment, EquipmentApplication

# TODO: swap login_required for your project's permission decorators.


# ------------------------------------------------------------------ equipment list
TEXT_FILTERS = {
    "equipment_id": "equipment_id__icontains",
    "name": "name__icontains",
    "model_name": "model_name__icontains",
    "serial_number": "serial_number__icontains",
    "manufacturer": "manufacturer__icontains",
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
        elif key == "application":                       # id (from the Applications screen / dropdown) or a name
            qs = qs.filter(application_id=int(value)) if value.isdigit() else qs.filter(application__name__icontains=value)
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
        text("manufacturer", _("Manufacturer")),
        choice("application", _("Application"), [(a.pk, a.name) for a in EquipmentApplication.objects.all()]),
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
    return render(request, "operation_control/equipment_detail.html", {
        "e": obj, "calibrations": obj.calibrations.all(),
        "assessment": obj.latest_assessment, "assessment_count": obj.assessments.count()})


@login_required
def calibration_add(request, pk):
    equipment = get_object_or_404(Equipment, pk=pk)
    form = CalibrationRecordForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        rec = form.save(commit=False)
        rec.equipment, rec.created_by = equipment, request.user
        rec.save()
        messages.success(request, _("Calibration recorded. Due date updated."))
        fresh = Equipment.objects.get(pk=equipment.pk)
        if fresh.status in (Equipment.Status.WAITING_FOR_CALIBRATION, Equipment.Status.SENT_FOR_CALIBRATION):
            fresh.status = Equipment.Status.ACTIVE            # calibrated: it is back in service
            fresh.save()
            messages.info(request, _("The device was waiting / in calibration and is now Active again."))
        return redirect("oc_equipment_detail", pk=equipment.pk)
    return render(request, "operation_control/calibration_form.html", {"form": form, "equipment": equipment})


@login_required
def calibration_edit(request, pk):
    rec = get_object_or_404(CalibrationRecord.objects.select_related("equipment"), pk=pk)
    form = CalibrationRecordForm(request.POST or None, request.FILES or None, instance=rec)
    if request.method == "POST" and form.is_valid():
        form.save()                      # model.save() refreshes the equipment's last date / due date
        messages.success(request, _("Calibration updated. Due date recalculated."))
        return redirect("oc_equipment_detail", pk=rec.equipment_id)
    return render(request, "operation_control/calibration_form.html",
                  {"form": form, "equipment": rec.equipment, "editing": True})


@login_required
@require_POST
def calibration_delete(request, pk):
    rec = get_object_or_404(CalibrationRecord, pk=pk)
    equipment_id = rec.equipment_id
    rec.delete()                         # model.delete() recalculates the equipment's due date
    messages.success(request, _("Calibration record deleted. Due date recalculated."))
    return redirect("oc_equipment_detail", pk=equipment_id)


@login_required
@require_POST
def equipment_delete(request, pk):
    obj = get_object_or_404(Equipment, pk=pk)
    try:
        obj.delete()
    except ProtectedError:
        messages.error(request, _("This equipment has dose records and cannot be deleted. Set its status to Inactive instead."))
        return redirect("oc_equipment_detail", pk=pk)
    messages.success(request, _("Equipment deleted."))
    return redirect("oc_equipment_list")


# ------------------------------------------------------------------ calibration workflow
# Active -> (Prepare) Waiting for calibration -> (Send) In calibration -> (a calibration record is added) Active
def _split_eligible(ids):
    ok, blocked = [], []
    for d in Equipment.objects.filter(pk__in=ids).order_by("name", "serial_number", "equipment_id"):
        reason = logic.calibration_block_reason(d.status)
        (blocked.append((d, reason)) if reason else ok.append(d))
    return ok, blocked


def _tell_about_blocked(request, blocked):
    if blocked:
        text = {"inactive": _("inactive"), "loan": _("on loan"), "in_calibration": _("already in calibration")}   # translated per request
        messages.warning(request, _("Skipped: %(list)s") % {"list": "، ".join(
            f"{d.equipment_id} ({text[reason]})" for d, reason in blocked)})


def _posted_ids(request):
    return [int(x) for x in request.POST.getlist("ids") if x.isdigit()]


@login_required
@require_POST
def calibration_prepare(request):
    """Selected devices -> 'Waiting for calibration', then show the request letter for them."""
    ids = _posted_ids(request)
    if not ids:
        messages.warning(request, _("Select at least one device."))
        return redirect("oc_equipment_list")
    ok, blocked = _split_eligible(ids)
    for d in ok:
        if d.status != Equipment.Status.WAITING_FOR_CALIBRATION:
            d.status = Equipment.Status.WAITING_FOR_CALIBRATION
            d.save()
    _tell_about_blocked(request, blocked)
    if not ok:
        return redirect("oc_equipment_list")
    messages.success(request, _("%(n)s device(s) are now “Waiting for calibration”.") % {"n": len(ok)})
    return redirect(f"{reverse('oc_calibration_request')}?ids={','.join(str(d.pk) for d in ok)}")


@login_required
@require_POST
def calibration_send(request):
    """Selected devices -> 'In calibration'."""
    ids = _posted_ids(request)
    if not ids:
        messages.warning(request, _("Select at least one device."))
        return redirect("oc_equipment_list")
    ok, blocked = _split_eligible(ids)
    for d in ok:
        d.status = Equipment.Status.SENT_FOR_CALIBRATION
        d.save()
    _tell_about_blocked(request, blocked)
    if ok:
        messages.success(request, _("%(n)s device(s) are now “In calibration”.") % {"n": len(ok)})
    return redirect("oc_equipment_list")


def _request_devices(request):
    ids = [int(x) for x in request.GET.get("ids", "").split(",") if x.strip().isdigit()]
    return Equipment.objects.filter(pk__in=ids).order_by("name", "serial_number", "equipment_id")


@login_required
def calibration_request(request):
    """The letter: a sentence, then a table (row, device, serial number) - to copy into Word."""
    devices = list(_request_devices(request))
    if not devices:
        messages.warning(request, _("Select at least one device."))
        return redirect("oc_equipment_list")
    return render(request, "operation_control/calibration_request.html", {
        "devices": devices, "text": conf.CALIBRATION_REQUEST_TEXT,
        "ids": ",".join(str(d.pk) for d in devices)})


@login_required
def calibration_request_doc(request):
    """The same letter as a file Word opens (HTML saved as .doc), right-to-left."""
    devices = list(_request_devices(request))
    if not devices:
        return redirect("oc_equipment_list")
    html = render_to_string("operation_control/calibration_request_doc.html",
                            {"devices": devices, "text": conf.CALIBRATION_REQUEST_TEXT}, request=request)
    response = HttpResponse("\ufeff" + html, content_type="application/msword; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="calibration_request.doc"'
    return response
