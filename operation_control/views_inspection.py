import csv

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _

from . import jalali_utils as ju
from . import conf, logic, services
from .forms import InspectionItemForm, InspectionRecordForm, InspectionYearForm
from .models import (
    InspectionAttachment, InspectionItem, InspectionPlanYear, InspectionRecord, RadiationWorker,
)

# TODO: swap login_required for your project's permission decorators.


def _pick_plan(request):
    years = list(InspectionPlanYear.objects.all())
    wanted = request.GET.get("year", "")
    plan = (next((y for y in years if str(y.year) == wanted), None)
            or next((y for y in years if y.year == ju.jalali_today()[0]), None)
            or (years[0] if years else None))
    return plan, years


@login_required
def inspection_plan(request):
    plan, years = _pick_plan(request)
    if not plan:
        return render(request, "operation_control/inspection_plan.html", {"no_plan": True})
    return render(request, "operation_control/inspection_plan.html", {
        "plan": plan, "years": years, **services.plan_matrix(plan),
        "workers": RadiationWorker.objects.filter(status=RadiationWorker.Status.ACTIVE).order_by("full_name"),
        "require_attachment": conf.INSPECTION_REQUIRE_ATTACHMENT})


@login_required
def inspection_report(request):
    plan, years = _pick_plan(request)
    if not plan:
        return redirect("oc_inspection_plan")
    return render(request, "operation_control/inspection_report.html",
                  {"plan": plan, "years": years, **services.plan_matrix(plan)})


@login_required
def inspection_year_create(request):
    form = InspectionYearForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        plan = form.save()
        messages.success(request, _("Plan year created. All active inspection items apply to it automatically."))
        return redirect(f"{reverse('oc_inspection_plan')}?year={plan.year}")
    return render(request, "operation_control/simple_form.html", {
        "form": form, "title": _("New plan year"), "cancel_url": "oc_inspection_plan",
        "subtitle": _("Inspection items are shared between years; only the done-marks are per year.")})


@login_required
def inspection_item_create(request):
    form = InspectionItemForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.created_by = request.user
        obj.save()
        messages.success(request, _("Inspection item saved."))
        return redirect("oc_inspection_plan")
    return render(request, "operation_control/simple_form.html", {
        "form": form, "title": _("Add inspection item"), "cancel_url": "oc_inspection_plan"})


@login_required
def inspection_item_edit(request, pk):
    item = get_object_or_404(InspectionItem, pk=pk)
    form = InspectionItemForm(request.POST or None, instance=item)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("Inspection item saved."))
        return redirect("oc_inspection_plan")
    return render(request, "operation_control/simple_form.html", {
        "form": form, "title": _("Edit inspection item"), "cancel_url": "oc_inspection_plan", "subtitle": str(item)})


@login_required
def inspection_record_edit(request, item_id, year, week):
    """
    Tick an inspection as done (or edit / remove the tick). Needs who did it, optionally a date (default today),
    a note and - unless disabled in settings - at least one evidence file.
    """
    item = get_object_or_404(InspectionItem, pk=item_id)
    plan = get_object_or_404(InspectionPlanYear, year=year)
    if not 1 <= week <= plan.total_weeks:
        return redirect("oc_inspection_plan")
    record = InspectionRecord.objects.filter(item=item, plan_year=plan, week_index=week).first()
    back = f"{reverse('oc_inspection_plan')}?year={plan.year}"

    if request.method == "POST" and "delete" in request.POST and record:
        record.delete()                                   # its evidence files go with it
        messages.success(request, _("Tick removed."))
        return redirect(back)

    posting = request.method == "POST"
    existing = list(record.attachments.all()) if record else []
    delete_ids = {int(x) for x in request.POST.getlist("delete_attachment") if x.isdigit()} if posting else set()
    kept = [a for a in existing if a.pk not in delete_ids]
    files = request.FILES.getlist("attachments") if posting else []

    form = InspectionRecordForm(request.POST if posting else None, instance=record,
                                initial={} if record else {"is_done": True},
                                new_files=files, kept_attachments=len(kept))
    if posting and form.is_valid():
        with transaction.atomic():
            obj = form.save(commit=False)
            obj.item, obj.plan_year, obj.week_index = item, plan, week
            if obj.is_done and not obj.done_date:
                obj.done_date = ju.today()
            if not obj.created_by_id:
                obj.created_by = request.user
            obj.save()
            form.save_m2m()
            for a in existing:
                if a.pk in delete_ids:
                    a.delete()
            for f in files:
                InspectionAttachment.objects.create(record=obj, file=f, uploaded_by=request.user)
        messages.success(request, _("Inspection recorded."))
        return redirect(back)

    month, slot = logic.week_to_month_slot(week, plan.first_month)
    return render(request, "operation_control/inspection_record_form.html", {
        "form": form, "item": item, "plan": plan, "record": record, "attachments": existing,
        "subtitle": f"{item} — {services.MONTH_NAMES[month - 1]} #{slot} ({plan.year})",
        "require_attachment": conf.INSPECTION_REQUIRE_ATTACHMENT, "back": back})


@login_required
def inspection_export_csv(request):
    """Progress report as CSV, plus the done weeks (re-importable with the inspection import)."""
    plan, _years = _pick_plan(request)
    if not plan:
        return redirect("oc_inspection_plan")
    state = services.plan_matrix(plan)
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="inspection_plan_{plan.year}.csv"'
    response.write("\ufeff")
    w = csv.writer(response)
    w.writerow(["title", "form_title", "form_code", "area", "period", "responsible", "is_active", "done_weeks",
                "plan_year", "due_so_far", "done", "percent", "overdue", "note"])
    for r in state["rows"]:
        i = r["item"]
        done = [c["week"] for c in r["cells"] if c["state"] == "done"]
        w.writerow([i.title, i.form_title, i.form_code, i.area, i.get_period_weeks_display(), i.responsible.personnel_code if i.responsible else "",
                    "yes" if i.is_active else "no", ",".join(map(str, done)), plan.year, r["due"], r["done"],
                    "" if r["percent"] is None else r["percent"], r["overdue"], r["note"]])
    return response
