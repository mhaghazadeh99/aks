import csv

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import ProtectedError
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from . import conf, logic, services
from .forms import (
    OnlineDoseFormSet, personal_dosimeters_defined, OperationDoseSessionForm, RadiationWorkerForm,
    TLDPasteForm, TLDReadingFormSet, TLDReportForm,
)
from .models import (
    EnvironmentalPoint, OperationDoseSession, OperationType, RadiationWorker, Season,
    TLDReading, TLDReport,
)

# TODO: swap login_required for your project's permission decorators.


def _paginate(request, qs, per_page=25):
    page_obj = Paginator(qs, per_page).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    return page_obj, params.urlencode()


def _simple_form(request, form, title, cancel_url, multipart=False, subtitle=""):
    return render(request, "operation_control/simple_form.html", {
        "form": form, "title": title, "cancel_url": cancel_url, "multipart": multipart, "subtitle": subtitle})


# ------------------------------------------------------------------ home
@login_required
def dosimetry_home(request):
    year, season = services.current_year_season()
    return render(request, "operation_control/dosimetry_home.html", {
        "year": year, "season_label": Season(season).label,
        "over_count": services.over_limit_count(year, season),
        "worker_count": RadiationWorker.objects.filter(status=RadiationWorker.Status.ACTIVE).count(),
        "limit": conf.SEASON_DOSE_LIMIT_MSV,
        "last_report": TLDReport.objects.first(),
        "session_count": OperationDoseSession.objects.filter(year=year, season=season).count(),
    })


# ------------------------------------------------------------------ workers
@login_required
def worker_list(request):
    qs = RadiationWorker.objects.all()
    term, status = request.GET.get("search", "").strip(), request.GET.get("status", "")
    if term:
        qs = qs.filter(Q(full_name__icontains=term) | Q(personnel_code__icontains=term) | Q(unit__icontains=term))
    if status in RadiationWorker.Status.values:
        qs = qs.filter(status=status)
    page_obj, qstr = _paginate(request, qs)
    return render(request, "operation_control/worker_list.html", {
        "page_obj": page_obj, "qs": qstr, "search": term, "status": status,
        "statuses": RadiationWorker.Status.choices})


@login_required
def worker_create(request):
    form = RadiationWorkerForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.created_by = request.user
        obj.save()
        messages.success(request, _("Worker saved."))
        return redirect("oc_worker_detail", pk=obj.pk)
    return _simple_form(request, form, _("Add Worker"), "oc_worker_list")


@login_required
def worker_edit(request, pk):
    obj = get_object_or_404(RadiationWorker, pk=pk)
    form = RadiationWorkerForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("Worker saved."))
        return redirect("oc_worker_detail", pk=obj.pk)
    return _simple_form(request, form, _("Edit Worker"), "oc_worker_list", subtitle=str(obj))


@login_required
def worker_detail(request, pk):
    worker = get_object_or_404(RadiationWorker, pk=pk)
    this_year = services.current_year_season()[0]
    try:
        year = int(request.GET.get("year") or this_year)
    except ValueError:
        year = this_year
    trend = services.worker_trend(worker, year - 2, year)
    chart = {
        "labels": [r["label"] for r in trend],
        "tld": [float(r["tld_body"]) for r in trend],
        "online": [float(r["online"]) for r in trend],
        "limit": float(conf.SEASON_DOSE_LIMIT_MSV),
    }
    return render(request, "operation_control/worker_detail.html", {
        "w": worker, "year": year, "trend": trend, "chart": chart, "limit": conf.SEASON_DOSE_LIMIT_MSV,
        "tld_readings": worker.tld_readings.select_related("report").order_by("-report__year", "-report__season")[:30],
        "online_records": worker.online_doses.select_related("session__operation_type", "device")
                                .order_by("-session__performed_date")[:30],
    })


# ------------------------------------------------------------------ TLD reports
@login_required
def tld_report_list(request):
    qs = TLDReport.objects.annotate(n_readings=Count("readings"))
    page_obj, qstr = _paginate(request, qs, 20)
    return render(request, "operation_control/tld_report_list.html", {"page_obj": page_obj, "qs": qstr})


@login_required
def tld_report_create(request):
    form = TLDReportForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.created_by = request.user
        obj.save()
        messages.success(request, _("TLD report saved. Now add the readings."))
        return redirect("oc_tld_report_detail", pk=obj.pk)
    return _simple_form(request, form, _("New TLD report"), "oc_tld_report_list", multipart=True)


@login_required
def tld_report_edit(request, pk):
    obj = get_object_or_404(TLDReport, pk=pk)
    form = TLDReportForm(request.POST or None, request.FILES or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("TLD report saved."))
        return redirect("oc_tld_report_detail", pk=obj.pk)
    return _simple_form(request, form, _("Edit TLD report"), "oc_tld_report_list", multipart=True, subtitle=str(obj))


@login_required
def tld_report_detail(request, pk):
    report = get_object_or_404(TLDReport, pk=pk)
    readings = report.readings.select_related("worker", "env_point").order_by(
        "position", "worker__full_name", "env_point__name", "tld_code")
    return render(request, "operation_control/tld_report_detail.html", {"report": report, "readings": readings})


@login_required
def tld_readings_edit(request, pk):
    report = get_object_or_404(TLDReport, pk=pk)
    formset = TLDReadingFormSet(request.POST or None, instance=report, prefix="readings")
    if request.method == "POST" and formset.is_valid():
        with transaction.atomic():
            for obj in formset.save(commit=False):
                if not obj.created_by_id:
                    obj.created_by = request.user
                obj.save()
            for obj in formset.deleted_objects:
                obj.delete()
        messages.success(request, _("Readings saved."))
        return redirect("oc_tld_report_detail", pk=report.pk)
    return render(request, "operation_control/tld_readings_form.html", {"report": report, "formset": formset})


@login_required
def tld_paste(request, pk):
    """Paste rows straight from the lab's report/Excel. All-or-nothing: any bad line blocks the save."""
    report = get_object_or_404(TLDReport, pk=pk)
    form = TLDPasteForm(request.POST or None)
    errors = []
    if request.method == "POST" and form.is_valid():
        rows, errors = logic.parse_tld_paste(form.cleaned_data["pasted"])
        workers_by_code = {w.personnel_code: w for w in RadiationWorker.objects.all()}
        workers_by_name = {w.full_name.casefold(): w for w in workers_by_code.values()}
        points = {p.name.casefold(): p for p in EnvironmentalPoint.objects.all()}
        resolved = []
        for r in rows:
            if r["position"] == "ENV":
                target = points.get(r["ref"].casefold())
                if not target:
                    errors.append((r["line"], _("Unknown environmental point '%(ref)s'") % {"ref": r["ref"]}))
                    continue
                resolved.append((r, None, target))
            else:
                target = workers_by_code.get(r["ref"]) or workers_by_name.get(r["ref"].casefold())
                if not target:
                    errors.append((r["line"], _("Unknown worker '%(ref)s'") % {"ref": r["ref"]}))
                    continue
                resolved.append((r, target, None))
        if not errors and not resolved:
            errors.append((0, _("Nothing to import.")))
        if not errors:
            created = updated = 0
            with transaction.atomic():
                for r, worker, point in resolved:
                    _obj, was_created = TLDReading.objects.update_or_create(
                        report=report, tld_code=r["tld_code"],
                        defaults={"position": r["position"], "worker": worker, "env_point": point,
                                  "gamma_msv": r["gamma"], "neutron_msv": r["neutron"],
                                  "remarks": r["remarks"], "created_by": request.user})
                    created, updated = created + was_created, updated + (not was_created)
            messages.success(request, _("%(c)s readings added, %(u)s updated.") % {"c": created, "u": updated})
            return redirect("oc_tld_report_detail", pk=report.pk)
        errors.sort()
    return render(request, "operation_control/tld_paste.html", {"report": report, "form": form, "errors": errors})


# ------------------------------------------------------------------ online dose sessions
@login_required
def session_list(request):
    qs = OperationDoseSession.objects.select_related("operation_type").annotate(n_records=Count("records", distinct=True))
    f = {k: request.GET.get(k, "") for k in ("year", "season", "operation_type", "search")}
    if f["year"].isdigit():
        qs = qs.filter(year=int(f["year"]))
    if f["season"].isdigit():
        qs = qs.filter(season=int(f["season"]))
    if f["operation_type"].isdigit():
        qs = qs.filter(operation_type_id=int(f["operation_type"]))
    if f["search"].strip():
        qs = qs.filter(Q(location__icontains=f["search"]) | Q(description__icontains=f["search"])
                       | Q(records__worker__full_name__icontains=f["search"])).distinct()
    page_obj, qstr = _paginate(request, qs)
    return render(request, "operation_control/session_list.html", {
        "page_obj": page_obj, "qs": qstr, "f": f, "seasons": Season.choices,
        "operation_types": OperationType.objects.all()})


def _session_form_view(request, session, title):
    form = OperationDoseSessionForm(request.POST or None, instance=session)
    formset = OnlineDoseFormSet(request.POST or None, instance=session, prefix="records")
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        with transaction.atomic():
            obj = form.save(commit=False)
            if not obj.created_by_id:
                obj.created_by = request.user
            obj.save()
            formset.instance = obj
            formset.save()
        messages.success(request, _("Operation and doses saved."))
        return redirect("oc_session_detail", pk=obj.pk)
    return render(request, "operation_control/session_form.html", {
        "form": form, "formset": formset, "title": title, "session": session if session.pk else None,
        "no_dosimeter_application": not personal_dosimeters_defined()})


@login_required
def session_create(request):
    return _session_form_view(request, OperationDoseSession(), _("New operation dose record"))


@login_required
def session_edit(request, pk):
    return _session_form_view(request, get_object_or_404(OperationDoseSession, pk=pk), _("Edit operation dose record"))


@login_required
def session_detail(request, pk):
    s = get_object_or_404(OperationDoseSession.objects.select_related("operation_type"), pk=pk)
    return render(request, "operation_control/session_detail.html", {
        "s": s, "records": s.records.select_related("worker", "device")})


@login_required
@require_POST
def session_delete(request, pk):
    get_object_or_404(OperationDoseSession, pk=pk).delete()
    messages.success(request, _("Operation record deleted."))
    return redirect("oc_session_list")


# ------------------------------------------------------------------ reports
@login_required
def dose_report(request):
    this_year, this_season = services.current_year_season()
    try:
        year = int(request.GET.get("year") or this_year)
        season = int(request.GET.get("season") or this_season)
    except ValueError:
        year, season = this_year, this_season
    if season not in services.SEASONS:
        season = this_season
    rows = services.season_report(year, season)

    if request.GET.get("export") == "csv":
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="dose_{year}_{season}.csv"'
        response.write("\ufeff")
        w = csv.writer(response)
        w.writerow([_("Personnel code"), _("Full name"),
                    _("TLD body gamma (mSv)"), _("TLD body neutron (mSv)"), _("TLD body total (mSv)"),
                    _("TLD hand gamma (mSv)"), _("TLD hand neutron (mSv)"),
                    _("Online gamma (mSv)"), _("Online neutron (mSv)"), _("Online total (mSv)")])
        for r in rows:
            w.writerow([r["worker"].personnel_code, r["worker"].full_name,
                        r["t"]["body_gamma"], r["t"]["body_neutron"], r["body_total"],
                        r["t"]["hand_gamma"], r["t"]["hand_neutron"],
                        r["o"]["gamma"], r["o"]["neutron"], r["online_total"]])
        return response

    return render(request, "operation_control/dose_report.html", {
        "year": year, "season": season, "seasons": Season.choices,
        "season_label": Season(season).label,
        "rows": [r for r in rows if r["has_data"]] if request.GET.get("only_data") else rows,
        "only_data": bool(request.GET.get("only_data")),
        "year_rows": services.year_report(year), "env_rows": services.env_report(year),
        "limit": conf.SEASON_DOSE_LIMIT_MSV, "annual_limit": conf.ANNUAL_DOSE_LIMIT_MSV,
    })


# ------------------------------------------------------------------ deletes
@login_required
@require_POST
def worker_delete(request, pk):
    obj = get_object_or_404(RadiationWorker, pk=pk)
    try:
        obj.delete()
    except ProtectedError:
        messages.error(request, _("This worker has dose records and cannot be deleted. Set the status to Left instead."))
        return redirect("oc_worker_detail", pk=pk)
    messages.success(request, _("Worker deleted."))
    return redirect("oc_worker_list")


@login_required
@require_POST
def tld_report_delete(request, pk):
    get_object_or_404(TLDReport, pk=pk).delete()          # its readings go with it
    messages.success(request, _("TLD report and its readings deleted."))
    return redirect("oc_tld_report_list")


# ------------------------------------------------------------------ CSV exports
def _csv_response(filename):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.write("\ufeff")
    return response, csv.writer(response)


@login_required
def worker_export_csv(request):
    response, w = _csv_response("radiation_workers.csv")
    w.writerow(["personnel_code", "full_name", "unit", "position", "status", "exit_date", "notes"])
    for x in RadiationWorker.objects.all():
        w.writerow([x.personnel_code, x.full_name, x.unit, x.position, x.status, x.exit_date or "", x.notes])
    return response


@login_required
def tld_export_csv(request):
    """Same columns as the TLD import template, so an export can be edited and re-imported."""
    qs = TLDReading.objects.select_related("report", "worker", "env_point").order_by(
        "report__year", "report__season", "position", "tld_code")
    if request.GET.get("report", "").isdigit():
        qs = qs.filter(report_id=int(request.GET["report"]))
    if request.GET.get("year", "").isdigit():
        qs = qs.filter(report__year=int(request.GET["year"]))
    response, w = _csv_response("tld_readings.csv")
    w.writerow(["year", "season", "report_number", "received_date", "tld_code", "personnel_code", "full_name",
                "env_point", "position", "gamma_msv", "neutron_msv", "unit", "remarks"])
    for r in qs:
        w.writerow([r.report.year, r.report.season, r.report.report_number, r.report.received_date or "", r.tld_code,
                    r.worker.personnel_code if r.worker else "", r.worker.full_name if r.worker else "",
                    r.env_point.name if r.env_point else "", r.get_position_display(),
                    "" if r.gamma_msv is None else r.gamma_msv, "" if r.neutron_msv is None else r.neutron_msv,
                    "mSv", r.remarks])
    return response


@login_required
def session_export_csv(request):
    """Same columns as the online-dose import template."""
    from .models import OnlineDoseRecord
    qs = OnlineDoseRecord.objects.select_related("session__operation_type", "worker", "device").order_by(
        "session__performed_date", "session_id", "worker__full_name")
    if request.GET.get("year", "").isdigit():
        qs = qs.filter(session__year=int(request.GET["year"]))
    if request.GET.get("season", "").isdigit():
        qs = qs.filter(session__season=int(request.GET["season"]))
    response, w = _csv_response("online_doses.csv")
    w.writerow(["date", "operation", "location", "operation_duration_min", "description", "personnel_code",
                "device", "dose_type", "dose_value", "unit", "exposure_minutes"])
    for r in qs:
        s = r.session
        w.writerow([s.performed_date, s.operation_type.name, s.location, s.duration_minutes or "", s.description,
                    r.worker.personnel_code, r.device.equipment_id, r.dose_type.lower(), r.dose_value,
                    r.get_dose_unit_display(), r.exposure_minutes or ""])
    return response
