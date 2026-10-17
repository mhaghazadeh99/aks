from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _

from . import jalali_utils as ju
from . import logic, services
from .forms import InspectionItemForm, InspectionRecordForm, InspectionYearForm
from .models import InspectionItem, InspectionPlanYear, InspectionRecord

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
    return render(request, "operation_control/inspection_plan.html",
                  {"plan": plan, "years": years, **services.plan_matrix(plan)})


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
    item = get_object_or_404(InspectionItem, pk=item_id)
    plan = get_object_or_404(InspectionPlanYear, year=year)
    if not 1 <= week <= plan.total_weeks:
        return redirect("oc_inspection_plan")
    record = InspectionRecord.objects.filter(item=item, plan_year=plan, week_index=week).first()
    back = f"{reverse('oc_inspection_plan')}?year={plan.year}"

    if request.method == "POST" and "delete" in request.POST and record:
        record.delete()
        messages.success(request, _("Record removed."))
        return redirect(back)

    initial = {} if record else {"is_done": True, "done_date": ju.today(), "done_by": request.user.pk}
    form = InspectionRecordForm(request.POST or None, request.FILES or None, instance=record, initial=initial)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.item, obj.plan_year, obj.week_index = item, plan, week
        if not obj.created_by_id:
            obj.created_by = request.user
        obj.save()
        messages.success(request, _("Inspection recorded."))
        return redirect(back)

    month, slot = logic.week_to_month_slot(week, plan.first_month)
    subtitle = f"{item} — {services.MONTH_NAMES[month - 1]} #{slot} ({plan.year})"
    return render(request, "operation_control/simple_form.html", {
        "form": form, "title": _("Record inspection"), "subtitle": subtitle, "multipart": True,
        "cancel_url_raw": back, "delete_label": _("Remove record") if record else ""})
