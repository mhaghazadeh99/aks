"""Calibration-interval assessments (OIML D10 scoring)."""
import csv

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from . import assessment
from . import jalali_utils as ju
from .forms import CalibrationAssessmentForm
from .models import CalibrationAssessment, Equipment

# TODO: swap login_required for your project's permission decorators.

_COPY_FIELDS = ("assessed_by_id", "device_type", "has_maker_recommendation", "maker_recommendation",
                "accuracy", "environment", "importance", "wear", "cost")


def _filtered(request):
    qs = CalibrationAssessment.objects.select_related("equipment", "assessed_by")
    term, level = request.GET.get("search", "").strip(), request.GET.get("level", "")
    if term:
        qs = qs.filter(Q(equipment__equipment_id__icontains=term) | Q(equipment__name__icontains=term)
                       | Q(equipment__serial_number__icontains=term))
    if level.isdigit():
        qs = qs.filter(level=int(level))
    if not request.GET.get("all"):                       # default: only the newest assessment of each device
        seen, keep = set(), []
        for pk, eq_id in qs.order_by("-assessment_date", "-id").values_list("pk", "equipment_id"):
            if eq_id not in seen:
                seen.add(eq_id)
                keep.append(pk)
        qs = qs.filter(pk__in=keep)
    return qs


@login_required
def assessment_list(request):
    qs = _filtered(request)
    page_obj = Paginator(qs, 25).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    return render(request, "operation_control/assessment_list.html", {
        "page_obj": page_obj, "qs": params.urlencode(), "search": request.GET.get("search", ""),
        "level": request.GET.get("level", ""), "show_all": bool(request.GET.get("all")),
        "unassessed": Equipment.objects.exclude(status=Equipment.Status.INACTIVE).filter(assessments__isnull=True).count()})


def _form_view(request, equipment, instance, title):
    initial = {}
    if instance is None:
        last = equipment.latest_assessment            # start from the previous answers: usually little changes
        initial = {f: getattr(last, f) for f in _COPY_FIELDS} if last else {}
        initial["assessment_date"] = ju.today()
    form = CalibrationAssessmentForm(request.POST or None, instance=instance, initial=initial)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.equipment = equipment
        if not obj.created_by_id:
            obj.created_by = request.user
        obj.save()
        if form.cleaned_data.get("apply_now"):
            obj.apply_to_equipment()
            messages.success(request, _("Assessment saved and the interval was applied to the equipment."))
        else:
            messages.success(request, _("Assessment saved."))
        return redirect("oc_assessment_detail", pk=obj.pk)
    return render(request, "operation_control/assessment_form.html", {
        "form": form, "equipment": equipment, "title": title,
        "score_table": assessment.js_table(), "levels": assessment.LEVELS})


@login_required
def assessment_create(request, equipment_pk):
    return _form_view(request, get_object_or_404(Equipment, pk=equipment_pk), None, _("New calibration interval assessment"))


@login_required
def assessment_edit(request, pk):
    a = get_object_or_404(CalibrationAssessment.objects.select_related("equipment"), pk=pk)
    return _form_view(request, a.equipment, a, _("Edit calibration interval assessment"))


@login_required
def assessment_detail(request, pk):
    a = get_object_or_404(CalibrationAssessment.objects.select_related("equipment", "assessed_by"), pk=pk)
    return render(request, "operation_control/assessment_detail.html", {
        "a": a, "e": a.equipment, "max_score": 100, "levels": assessment.LEVELS})


@login_required
@require_POST
def assessment_apply(request, pk):
    a = get_object_or_404(CalibrationAssessment, pk=pk)
    a.apply_to_equipment()
    messages.success(request, _("Calibration period set to %(m)s months. The due date was recalculated.") % {"m": a.interval_months})
    return redirect("oc_assessment_detail", pk=pk)


@login_required
@require_POST
def assessment_delete(request, pk):
    a = get_object_or_404(CalibrationAssessment, pk=pk)
    equipment_id = a.equipment_id
    a.delete()
    messages.success(request, _("Assessment deleted."))
    return redirect("oc_equipment_detail", pk=equipment_id)


@login_required
def assessment_export_csv(request):
    """Same columns as the import template (codes), plus the computed result."""
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="calibration_assessments.csv"'
    response.write("\ufeff")
    w = csv.writer(response)
    w.writerow(["equipment_id", "assessment_date", "assessed_by", "has_maker_recommendation", "device_type",
                "maker_recommendation", "accuracy", "environment", "importance", "wear", "cost", "notes",
                "total_score", "level", "interval_months"])
    for a in _filtered(request):
        w.writerow([a.equipment.equipment_id, a.assessment_date,
                    a.assessed_by.personnel_code if a.assessed_by else "", "yes" if a.has_maker_recommendation else "no",
                    a.device_type, a.maker_recommendation, a.accuracy, a.environment, a.importance, a.wear, a.cost,
                    a.notes, a.total_score, a.level, a.interval_months])
    return response
