import csv

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .forms import (
    AnalysisForm,
    LabReceiveForm,
    NuclideActivityFormSet,
    SampleForm,
)
from .models import Analysis, Sample, SampleStatus


# =====================================================
# HOME / QUEUES
# =====================================================

def lab_home(request):
    context = {
        "collected_count": Sample.objects.filter(status=SampleStatus.COLLECTED).count(),
        "sent_count": Sample.objects.filter(status=SampleStatus.SENT_TO_LAB).count(),
        "received_count": Sample.objects.filter(status=SampleStatus.RECEIVED_BY_LAB).count(),
        "in_analysis_count": Sample.objects.filter(status=SampleStatus.IN_ANALYSIS).count(),
        "completed_count": Sample.objects.filter(status=SampleStatus.COMPLETED).count(),
        "pending_review_count": Analysis.objects.filter(approved=False).count(),
        "urgent_count": Sample.objects.filter(
            urgent=True,
        ).exclude(status__in=[SampleStatus.COMPLETED, SampleStatus.REJECTED]).count(),
    }
    return render(request, "laboratory/lab_home.html", context)


def sample_list(request):

    queryset = (
        Sample.objects
        .select_related("batch", "collected_by")
        .prefetch_related("analysis__nuclide_activities__radionuclide")
        .order_by("-urgent", "-sampling_date", "-id")
    )

    search = request.GET.get("search", "")
    if search:
        queryset = queryset.filter(
            Q(sample_id__icontains=search)
            | Q(sample_code_barcode__icontains=search)
            | Q(description__icontains=search)
            | Q(batch__waste_id__icontains=search)
        )

    status = request.GET.get("status", "")
    if status:
        queryset = queryset.filter(status=status)

    kind = request.GET.get("kind", "")
    if kind == "standalone":
        queryset = queryset.filter(batch__isnull=True)
    elif kind == "batch":
        queryset = queryset.filter(batch__isnull=False)

    size = request.GET.get("size", "25")
    if size == "all":
        page_size = max(queryset.count(), 1)
    else:
        try:
            page_size = max(1, int(size))
        except (ValueError, TypeError):
            page_size = 25

    paginator = Paginator(queryset, page_size)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(request, "laboratory/sample_list.html", {
        "samples": page_obj,
        "page_obj": page_obj,
        "page_size": size,
        "search": search,
        "status": status,
        "kind": kind,
        "status_choices": SampleStatus.choices,
    })


# =====================================================
# SAMPLE CRUD
# =====================================================

def sample_create(request):
    """
    Creates a sample with or without a waste batch. A `batch` query
    param pre-selects one (used by the 'take a sample' link on a waste
    batch's detail page); omit it for a standalone sample.
    """

    initial = {}
    batch_id = request.GET.get("batch")
    if batch_id:
        initial["batch"] = batch_id

    if request.method == "POST":
        form = SampleForm(request.POST)
        if form.is_valid():
            sample = form.save(commit=False)
            sample.collected_by = request.user
            sample.status = SampleStatus.COLLECTED
            sample.save()
            messages.success(request, _("Sample created."))
            return redirect("sample_detail", pk=sample.pk)
    else:
        form = SampleForm(initial=initial)

    return render(request, "laboratory/sample_form.html", {
        "form": form,
        "page_title": _("New Sample"),
    })


def sample_edit(request, pk):

    sample = get_object_or_404(Sample, pk=pk)

    if request.method == "POST":
        form = SampleForm(request.POST, instance=sample)
        if form.is_valid():
            form.save()
            messages.success(request, _("Sample updated."))
            return redirect("sample_detail", pk=sample.pk)
    else:
        form = SampleForm(instance=sample)

    return render(request, "laboratory/sample_form.html", {
        "form": form,
        "sample": sample,
        "page_title": _("Edit Sample"),
    })


def sample_detail(request, pk):

    sample = get_object_or_404(
        Sample.objects.select_related("batch", "collected_by"),
        pk=pk,
    )

    analysis = getattr(sample, "analysis", None)

    return render(request, "laboratory/sample_detail.html", {
        "sample": sample,
        "analysis": analysis,
        "nuclide_activities": (
            analysis.nuclide_activities.select_related("radionuclide").all() if analysis else []
        ),
        "receive_form": LabReceiveForm(instance=sample),
    })


# =====================================================
# STATUS TRANSITIONS
# Collected -> Sent to Lab -> Received by Lab -> In Analysis -> Completed
# =====================================================

def sample_send_to_lab(request, pk):

    sample = get_object_or_404(Sample, pk=pk)

    if request.method == "POST":
        if sample.status != SampleStatus.COLLECTED:
            messages.error(request, _("Only a collected sample can be sent to the lab."))
        else:
            sample.send_to_lab(performed_by=request.user)
            messages.success(request, _("Sample sent to the lab."))

    return redirect("sample_detail", pk=pk)


def sample_lab_receive(request, pk):

    sample = get_object_or_404(Sample, pk=pk)

    if request.method == "POST":

        form = LabReceiveForm(request.POST, instance=sample)

        if form.is_valid():
            sample = form.save(commit=False)
            if not sample.lab_received_date:
                sample.lab_received_date = timezone.now().date()
            sample.status = SampleStatus.RECEIVED_BY_LAB
            sample.save()
            messages.success(request, _("Sample marked as received by the lab."))
        else:
            messages.error(request, _("Please correct the errors below."))

    return redirect("sample_detail", pk=pk)


def sample_start_analysis(request, pk):

    sample = get_object_or_404(Sample, pk=pk)

    if request.method == "POST":
        sample.status = SampleStatus.IN_ANALYSIS
        sample.save(update_fields=["status"])
        messages.success(request, _("Sample moved into analysis."))
        return redirect("analysis_edit", pk=sample.pk)

    return redirect("sample_detail", pk=pk)


def sample_reject(request, pk):

    sample = get_object_or_404(Sample, pk=pk)

    if request.method == "POST":
        sample.status = SampleStatus.REJECTED
        sample.lab_comments = request.POST.get("reason", sample.lab_comments)
        sample.save(update_fields=["status", "lab_comments"])
        messages.success(request, _("Sample rejected."))

    return redirect("sample_detail", pk=pk)


# =====================================================
# ANALYSIS ENTRY
# =====================================================

def analysis_edit(request, pk):
    """
    Enters (or edits) the analysis result for a sample, including the
    per-nuclide alpha/beta/gamma rows. Creating/saving an Analysis for a
    BATCH-linked sample automatically makes it that batch's `is_latest`
    (handled in Analysis.save), which is what drives the waste batch's
    activity figures.
    """

    sample = get_object_or_404(Sample.objects.select_related("batch"), pk=pk)
    analysis = getattr(sample, "analysis", None)

    if request.method == "POST":

        form = AnalysisForm(request.POST, instance=analysis)

        if form.is_valid():

            with transaction.atomic():
                analysis = form.save(commit=False)
                analysis.sample = sample
                if not analysis.analyst_id:
                    analysis.analyst = request.user
                analysis.save()

                formset = NuclideActivityFormSet(request.POST, instance=analysis)

                if formset.is_valid():
                    formset.save()
                else:
                    # Roll the Analysis save back too — a half-saved
                    # result with rejected nuclide rows is worse than none.
                    transaction.set_rollback(True)
                    messages.error(request, _("Please correct the nuclide rows below."))
                    return render(request, "laboratory/analysis_form.html", {
                        "sample": sample,
                        "form": form,
                        "formset": formset,
                    })

                if sample.status != SampleStatus.COMPLETED:
                    sample.status = SampleStatus.COMPLETED
                    sample.save(update_fields=["status"])

            messages.success(request, _("Analysis saved."))
            return redirect("sample_detail", pk=sample.pk)

        formset = NuclideActivityFormSet(request.POST, instance=analysis)

    else:
        form = AnalysisForm(instance=analysis)
        formset = NuclideActivityFormSet(instance=analysis)

    return render(request, "laboratory/analysis_form.html", {
        "sample": sample,
        "analysis": analysis,
        "form": form,
        "formset": formset,
    })


def analysis_approve(request, pk):
    """Review/approve step — separate person from the analyst."""

    analysis = get_object_or_404(Analysis.objects.select_related("sample"), pk=pk)

    if request.method == "POST":
        analysis.approved = True
        analysis.reviewed_by = request.user
        analysis.review_date = timezone.now().date()
        analysis.save(update_fields=["approved", "reviewed_by", "review_date"])
        messages.success(request, _("Analysis approved."))

    return redirect("sample_detail", pk=analysis.sample.pk)


def analysis_review_queue(request):

    queryset = (
        Analysis.objects
        .filter(approved=False)
        .select_related("sample", "sample__batch", "analyst")
        .order_by("-analysis_date")
    )

    paginator = Paginator(queryset, 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(request, "laboratory/analysis_review_queue.html", {"page_obj": page_obj})


# =====================================================
# EXPORT
# =====================================================

def sample_export_csv(request):

    queryset = (
        Sample.objects
        .select_related("batch", "collected_by")
        .prefetch_related("analysis__nuclide_activities__radionuclide")
    )

    status = request.GET.get("status")
    if status:
        queryset = queryset.filter(status=status)

    response = HttpResponse(content_type="text/csv; charset=utf-8-sig")
    response["Content-Disposition"] = 'attachment; filename="samples.csv"'
    writer = csv.writer(response)

    writer.writerow([
        "Sample_ID", "Barcode", "Waste_Batch", "Description", "Stage", "Sampling_Date",
        "Mass_kg", "Volume_L", "Urgent", "Status", "Collected_By",
        "Sent_To_Lab", "Lab_Received", "Analysis_Date", "Total_Alpha_Bq", "Total_Beta_Bq",
        "Approved", "Nuclides",
    ])

    for s in queryset:
        analysis = getattr(s, "analysis", None)
        nuclides = ""
        if analysis:
            nuclides = "; ".join(
                f"{na.radionuclide}({na.get_radiation_type_display()})={na.activity_bq}"
                for na in analysis.nuclide_activities.all()
            )

        writer.writerow([
            s.sample_id, s.sample_code_barcode,
            s.batch.waste_id if s.batch else "",
            s.description, s.sample_stage, s.sampling_date,
            s.sample_mass_kg, s.sample_volume_l, s.urgent, s.status,
            s.collected_by.username if s.collected_by else "",
            s.sent_to_lab_date, s.lab_received_date,
            analysis.analysis_date if analysis else "",
            analysis.total_alpha if analysis else "",
            analysis.total_beta if analysis else "",
            analysis.approved if analysis else "",
            nuclides,
        ])

    return response
