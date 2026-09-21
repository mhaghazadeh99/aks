import csv
import json

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from dashboard.models import HideShowFilterT

from .forms import (
    ConditionBatchForm,
    MergeBatchesForm,
    WasteBatchForm,
    WasteMovementForm,
)
from .models import (
    BatchStatus,
    WasteBatch,
    WasteBatchLineage,
    WasteMovementAttachment,
)
from .services.batch_ops import condition_batch, merge_batches, split_batch


# Same idea as dashboard.views.FIELD_FILTER_MAP: maps each filter key to
# a real Django lookup path, traversing FKs to their display field.
# Computed/related-only values (activity, nuclides) are deliberately
# absent — they can't be filtered at the DB level since they live in
# the laboratory app behind a decay calculation.
FIELD_FILTER_MAP = {
    "waste_id": "waste_id",
    "waste_type": "waste_type",
    "waste_class": "waste_class",
    "waste_state": "waste_state",
    "facility": "facility__name",
    "origin_facility": "origin_facility__name",
    "origin_of_waste": "origin_of_waste",
    "date_received": "date_received",
    "material": "material",
    "waste_arising_from": "waste_arising_from",
    "container_type": "container_type",
    "package_type": "package_type",
    "waste_matrix": "waste_matrix",
    "mass_kg": "mass_kg",
    "volume_m3": "volume_m3",
    "location": "location",
    "status": "status",
    "status_date": "status_date",
    "pretreatment": "pretreatment",
    "treatment": "treatment",
    "possible_pretreatment": "possible_pretreatment",
    "possible_treatment": "possible_treatment",
    "dose_rate_surface_uSv": "dose_rate_surface_uSv",
    "dose_rate_1m_uSv": "dose_rate_1m_uSv",
    "dose_rate_date": "dose_rate_date",
    "source_nuclide": "samples__analysis__nuclide_activities__radionuclide__name",
    "created_by": "created_by__username",
    "created_at": "created_at",
}


def waste_home(request):
    return render(request, "waste/waste_home.html", {
        "total": WasteBatch.objects.count(),
        "stored": WasteBatch.objects.filter(status=BatchStatus.STORED).count(),
        "in_treatment": WasteBatch.objects.filter(status=BatchStatus.IN_TREATMENT).count(),
    })


def waste_table(request):
    """Mirrors dashboard.views.tables_view — same search/filter/page-size/
    column-visibility behaviour, so the two inventory pages feel identical."""

    queryset = (
        WasteBatch.objects
        .select_related("facility", "origin_facility", "created_by")
        .prefetch_related(
            "movements__from_facility",
            "movements__to_facility",
            "samples__analysis__nuclide_activities__radionuclide",
        )
        .order_by("-created_at")
    )

    search = request.GET.get("search")
    if search:
        search_q = Q()
        for lookup in set(FIELD_FILTER_MAP.values()):
            search_q |= Q(**{f"{lookup}__icontains": search})
        queryset = queryset.filter(search_q)

    keys = request.GET.getlist("key")
    values = request.GET.getlist("value")

    for k, v in zip(keys, values):
        if not v:
            continue
        lookup = FIELD_FILTER_MAP.get(k)
        if not lookup:
            continue
        queryset = queryset.filter(**{f"{lookup}__icontains": v})

    # Hide batches already consumed by a merge/split/conditioning unless
    # explicitly asked for — they're history, not current inventory.
    if request.GET.get("show_consumed") != "1":
        queryset = queryset.exclude(status=BatchStatus.CONSUMED)

    if search or keys:
        queryset = queryset.distinct()

    size = request.GET.get("size", "10")
    if size == "all":
        page_size = max(queryset.count(), 1)
    else:
        try:
            page_size = max(1, int(size))
        except (ValueError, TypeError):
            page_size = 10

    paginator = Paginator(queryset, page_size)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(request, "waste/waste_table.html", {
        "batches": page_obj,
        "page_obj": page_obj,
        "page_size": size,
        "search": search,
        "keys": keys,
        "values": values,
        "show_consumed": request.GET.get("show_consumed") == "1",
    })


def waste_create(request):

    if request.method == "POST":
        form = WasteBatchForm(request.POST, request.FILES)
        if form.is_valid():
            batch = form.save(commit=False)
            batch.created_by = request.user
            batch.status_date = timezone.now().date()
            batch.save()
            messages.success(request, _("Waste batch created."))
            return redirect("waste_table")
    else:
        form = WasteBatchForm()

    return render(request, "waste/waste_form.html", {"form": form, "page_title": _("Add Waste Batch")})


def waste_edit(request, pk):

    batch = get_object_or_404(WasteBatch, pk=pk)

    if request.method == "POST":

        if request.POST.get("action") == "add_movement":

            form = WasteBatchForm(instance=batch)
            movement_form = WasteMovementForm(request.POST)

            if movement_form.is_valid():
                movement = batch.register_movement(
                    movement_type=movement_form.cleaned_data["movement_type"],
                    to_facility=movement_form.cleaned_data["to_facility"],
                    from_facility=movement_form.cleaned_data.get("from_facility"),
                    performed_by=request.user,
                    remarks=movement_form.cleaned_data.get("remarks", ""),
                    movement_date=movement_form.cleaned_data["movement_date"],
                    mass_kg=movement_form.cleaned_data.get("mass_kg"),
                    volume_m3=movement_form.cleaned_data.get("volume_m3"),
                )
                for f in request.FILES.getlist("movement_attachments"):
                    WasteMovementAttachment.objects.create(movement=movement, file=f)

                messages.success(request, _("Movement recorded."))
                return redirect("waste_edit", pk=batch.pk)

        else:
            form = WasteBatchForm(request.POST, request.FILES, instance=batch)
            movement_form = WasteMovementForm(initial={"from_facility": batch.facility})

            if form.is_valid():
                form.save()
                messages.success(request, _("Waste batch updated."))
                return redirect("waste_table")

    else:
        form = WasteBatchForm(instance=batch)
        movement_form = WasteMovementForm(initial={"from_facility": batch.facility})

    movements = (
        batch.movements
        .select_related("from_facility", "to_facility", "performed_by")
        .prefetch_related("attachments")
        .order_by("-movement_date", "-id")
    )

    return render(request, "waste/waste_form.html", {
        "form": form,
        "movement_form": movement_form,
        "movements": movements,
        "batch": batch,
        "page_title": _("Edit Waste Batch"),
        "parent_links": batch.parent_links.select_related("parent").all(),
        "child_links": batch.child_links.select_related("child").all(),
    })


def waste_detail(request, pk):

    batch = get_object_or_404(
        WasteBatch.objects.select_related("facility", "origin_facility", "created_by"),
        pk=pk,
    )

    return render(request, "waste/waste_detail.html", {
        "batch": batch,
        "movements": batch.movements.select_related("from_facility", "to_facility").order_by("-movement_date"),
        "nuclide_activities": batch.nuclide_activities(),
        "analysis": batch.latest_analysis,
        "parent_links": batch.parent_links.select_related("parent").all(),
        "child_links": batch.child_links.select_related("child").all(),
        "samples": batch.samples.all(),
    })


# =====================================================
# Bulk actions from the table (selected checkboxes)
# =====================================================

def waste_merge(request):

    ids = request.POST.getlist("ids") or request.GET.getlist("ids")
    batches = list(WasteBatch.objects.filter(pk__in=ids))

    if request.method == "POST" and request.POST.get("action") == "confirm":

        form = MergeBatchesForm(request.POST)

        if form.is_valid():
            data = form.cleaned_data
            overrides = {}
            for key in ("mass_kg", "volume_m3", "container_type", "location"):
                if data.get(key):
                    overrides[key] = data[key]

            try:
                child = merge_batches(
                    batches,
                    new_waste_id=data["new_waste_id"],
                    performed_by=request.user,
                    remarks=data.get("remarks", ""),
                    **overrides,
                )
            except ValueError as exc:
                messages.error(request, str(exc))
                return redirect("waste_table")

            messages.success(
                request,
                _("Merged %(count)s batches into %(id)s.") % {"count": len(batches), "id": child.waste_id},
            )
            return redirect("waste_detail", pk=child.pk)

    else:
        form = MergeBatchesForm()

    if len(batches) < 2:
        messages.error(request, _("Select at least two batches to merge."))
        return redirect("waste_table")

    return render(request, "waste/waste_merge.html", {"batches": batches, "form": form, "ids": ids})


def waste_split(request, pk):

    batch = get_object_or_404(WasteBatch, pk=pk)

    if request.method == "POST":

        # Portions come from a dynamic JS table (see template), posted as
        # parallel lists — same pattern as the license app's source rows.
        waste_ids = request.POST.getlist("portion_waste_id")
        masses = request.POST.getlist("portion_mass")
        volumes = request.POST.getlist("portion_volume")

        portions = []
        for i, waste_id in enumerate(waste_ids):
            if not waste_id.strip():
                continue
            portion = {"waste_id": waste_id.strip()}
            if i < len(masses) and masses[i]:
                portion["mass_kg"] = masses[i]
            if i < len(volumes) and volumes[i]:
                portion["volume_m3"] = volumes[i]
            portions.append(portion)

        try:
            children = split_batch(
                batch, portions, performed_by=request.user,
                remarks=request.POST.get("remarks", ""),
            )
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect("waste_split", pk=pk)

        messages.success(request, _("Split into %(count)s batches.") % {"count": len(children)})
        return redirect("waste_table")

    return render(request, "waste/waste_split.html", {"batch": batch})


def waste_condition(request, pk):

    batch = get_object_or_404(WasteBatch, pk=pk)

    if request.method == "POST":

        form = ConditionBatchForm(request.POST)

        if form.is_valid():
            data = form.cleaned_data
            overrides = {
                key: data[key]
                for key in (
                    "pretreatment", "treatment", "package_type", "waste_matrix",
                    "waste_to_matrix_ratio", "package_mass_kg", "package_volume_m3",
                    "mass_kg", "volume_m3", "location",
                )
                if data.get(key)
            }

            try:
                child = condition_batch(
                    batch,
                    new_waste_id=data["new_waste_id"],
                    performed_by=request.user,
                    remarks=data.get("remarks", ""),
                    **overrides,
                )
            except ValueError as exc:
                messages.error(request, str(exc))
                return redirect("waste_condition", pk=pk)

            messages.success(
                request, _("Conditioned into %(id)s.") % {"id": child.waste_id}
            )
            return redirect("waste_detail", pk=child.pk)

    else:
        form = ConditionBatchForm()

    return render(request, "waste/waste_condition.html", {"batch": batch, "form": form})


def waste_send_to_analysis(request):
    """
    Creates a Sample for each selected batch and marks it sent to the
    lab. Local import: laboratory imports waste, so importing it at
    module level here would be circular.
    """

    from laboratory.models import Sample, SampleStage, SampleStatus

    if request.method != "POST":
        return redirect("waste_table")

    ids = request.POST.getlist("ids")
    batches = WasteBatch.objects.filter(pk__in=ids)

    if not batches:
        messages.error(request, _("Select at least one batch."))
        return redirect("waste_table")

    created = []
    today = timezone.now().date()

    for batch in batches:
        sample_id = f"{batch.waste_id}-S{batch.samples.count() + 1}"
        sample = Sample.objects.create(
            sample_id=sample_id,
            batch=batch,
            sample_stage=SampleStage.RECEIPT,
            sampling_date=today,
            status=SampleStatus.SENT_TO_LAB,
            sent_to_lab_date=today,
            collected_by=request.user,
        )
        created.append(sample)

    messages.success(
        request, _("%(count)s sample(s) created and sent to the lab.") % {"count": len(created)}
    )
    return redirect("waste_table")


# =====================================================
# Column visibility + CSV export (same contract as dashboard's)
# =====================================================

def waste_save_column(request):
    if request.method == "POST":
        data = json.loads(request.body)
        HideShowFilterT.objects.update_or_create(
            parent="waste", key=data["key"], defaults={"value": data["value"]}
        )
        return JsonResponse({"status": "ok"})
    return JsonResponse({"error": "bad"}, status=400)


def waste_get_column(request):
    data = list(HideShowFilterT.objects.filter(parent="waste").values("key", "value"))
    return JsonResponse(data, safe=False)


def waste_export_csv(request):

    queryset = (
        WasteBatch.objects
        .select_related("facility", "origin_facility", "created_by")
        .prefetch_related("samples__analysis__nuclide_activities__radionuclide")
    )

    keys = request.GET.getlist("key")
    values = request.GET.getlist("value")
    for k, v in zip(keys, values):
        lookup = FIELD_FILTER_MAP.get(k)
        if lookup:
            queryset = queryset.filter(**{f"{lookup}__icontains": v})

    response = HttpResponse(content_type="text/csv; charset=utf-8-sig")
    response["Content-Disposition"] = 'attachment; filename="waste.csv"'
    writer = csv.writer(response)

    writer.writerow([
        "Waste_ID", "Waste_Type", "Waste_Class", "Waste_State", "Facility", "Origin_Facility",
        "Origin_Of_Waste", "Date_Received", "Material", "Container_Type", "Package_Type",
        "Waste_Matrix", "Mass_kg", "Volume_m3", "Location", "Status", "Status_Date",
        "Pretreatment", "Treatment", "Possible_Pretreatment", "Possible_Treatment",
        "Dose_Surface_uSv", "Dose_1m_uSv", "Dose_Date",
        "pH", "Density", "Total_Solids", "Suspended_Solids", "Soluble_Solids",
        "Waste_To_Matrix_Ratio", "Waste_Mass_kg", "Package_Mass_kg", "Package_Volume_m3",
        "Total_Alpha_Bq", "Total_Beta_Bq", "Current_Gamma_Bq", "Current_Total_Activity_Bq",
        "Nuclides", "Created_By", "Created_At",
    ])

    for b in queryset:
        writer.writerow([
            b.waste_id, b.waste_type, b.waste_class, b.waste_state,
            b.facility.name if b.facility else None,
            b.origin_facility.name if b.origin_facility else None,
            b.origin_of_waste, b.date_received, b.material, b.container_type, b.package_type,
            b.waste_matrix, b.mass_kg, b.volume_m3, b.location, b.status, b.status_date,
            b.pretreatment, b.treatment, b.possible_pretreatment, b.possible_treatment,
            b.dose_rate_surface_uSv, b.dose_rate_1m_uSv, b.dose_rate_date,
            b.ph, b.density, b.total_solids, b.suspended_solids, b.soluble_solids,
            b.waste_to_matrix_ratio, b.waste_mass_kg, b.package_mass_kg, b.package_volume_m3,
            b.total_alpha_bq, b.total_beta_bq, b.current_gamma_bq_value,
            b.current_total_activity_bq_value, b.nuclide_summary,
            b.created_by.username if b.created_by else None, b.created_at,
        ])

    return response
