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
    AnalysisForm, CollectorRunForm,
    LabReceiveForm,
    NuclideActivityFormSet,
    SampleForm,
)
from .models import (
    AlphaBetaCountingRun, Analysis, AnalysisApproval, AnalysisAttachment, CounterType,
    LabApprovalRole, LabApprovalStatus, LabAttachmentType, Sample, SampleStatus,SampleStage,
)

import os
import tempfile

from django.core.files import File

from .models import (
    AlphaBetaCountingRun, AnalysisApproval, LabApprovalRole, LabApprovalStatus,
    LabAttachmentType, AnalysisAttachment, CounterType,
)
from .forms import AlphaBetaCountingRunForm, LabReportUploadForm
from .services.workflow import (
    create_analysis_approval_chain, create_counting_run_approval_chain,
    current_step_for, approve_step, reject_step,
)
from .services import report_generator, signature_service
from .services.report_generator import generate_gamma_report, generate_alpha_beta_report,ALPHA_BETA_ROWS_PER_PAGE
from .services.signature_service import PdfReportSigner # LabReportSigner

import datetime
from django.urls import reverse
from .services.workflow import pending_steps_for_role, rejected_steps

# ---- hook into your EXISTING analysis_edit, right after the analysis+formset save succeeds ----
# Add this block inside analysis_edit's `with transaction.atomic():`, right
# after `sample.save(update_fields=["status"])`:
#
#     if analysis.detector_type == CounterType.HPGE:
#         create_analysis_approval_chain(analysis)
#         generate_gamma_report(analysis, request.user)
#
# (Alpha/Beta analyses are NOT auto-reported here — they get added to a
# CountingRun separately, see below.)
def lab_home(request):
    return render(request, "laboratory/lab_home.html")

def counting_run_list(request):
    runs = AlphaBetaCountingRun.objects.order_by("-run_date", "-id")
    return render(request, "laboratory/counting_run_list.html", {"runs": runs})


def counting_run_create(request):

    if request.method == "POST":
        form = CollectorRunForm(request.POST)

        codes = request.POST.getlist("sample_code")
        masses = request.POST.getlist("sample_mass")
        volumes = request.POST.getlist("sample_volume")

        rows = []
        row_errors = []
        for i, code in enumerate(codes):
            code = code.strip()
            if not code:
                continue
            mass = masses[i].strip() if i < len(masses) else ""
            volume = volumes[i].strip() if i < len(volumes) else ""
            if not mass and not volume:
                row_errors.append(f"{code}: needs a mass or a volume")
                continue
            if Sample.objects.filter(sample_id=code).exists() or Sample.objects.filter(sample_code_barcode=code).exists():
                row_errors.append(f"{code}: this sample ID/barcode is already in use")
                continue
            rows.append({"code": code, "mass": mass or None, "volume": volume or None})

        if not rows:
            row_errors.append("Add at least one sample.")

        if form.is_valid() and not row_errors:
            with transaction.atomic():
                run = form.save(commit=False)
                run.created_by = request.user
                run.save()

                today = timezone.now().date()
                for row in rows:
                    sample = Sample.objects.create(
                        sample_id=row["code"],
                        sample_code_barcode=row["code"],
                        sample_stage=run.sample_stage or SampleStage.RECEIPT,
                        sampling_date=run.sampling_date_from or today,
                        sampling_location=run.sampling_location,
                        applicant_name=run.applicant_name,
                        sample_mass_kg=row["mass"],
                        sample_volume_ml=row["volume"],
                        status=SampleStatus.SENT_TO_LAB,
                        sent_to_lab_date=today,
                        analysis_type=CounterType.ALPHABETA,
                        collected_by=request.user,
                    )
                    Analysis.objects.create(
                        sample=sample, counting_run=run, detector_type=CounterType.ALPHABETA,
                    )

            messages.success(request, _("Run %(id)s created with %(n)s sample(s).") % {"id": run.run_id, "n": len(rows)})
            return redirect("counting_run_detail", pk=run.pk)
        else:
            for e in row_errors:
                messages.error(request, e)
    else:
        form = CollectorRunForm()

    return render(request, "laboratory/counting_run_form.html", {"form": form, "page_title": _("New Counting Run")})

def counting_run_edit(request, pk):
    run = get_object_or_404(AlphaBetaCountingRun, pk=pk)

    if run.approvals.exists():
        messages.error(request, _("This run is already in the signature chain and can't be edited."))
        return redirect("counting_run_detail", pk=pk)

    if request.method == "POST":
        form = AlphaBetaCountingRunForm(request.POST, instance=run)
        if form.is_valid():
            run = form.save()
            if run.counting_duration_seconds and (run.alpha_mda_mbq or run.beta_mda_mbq):
                run.counting_completed = True
                run.save(update_fields=["counting_completed"])
            messages.success(request, _("Counting data saved."))
            return redirect("counting_run_detail", pk=pk)
    else:
        form = AlphaBetaCountingRunForm(instance=run)

    return render(request, "laboratory/counting_run_edit.html", {"form": form, "run": run})

    
def counting_run_detail(request, pk):

    run = get_object_or_404(AlphaBetaCountingRun, pk=pk)

    unassigned = (
        Analysis.objects.filter(detector_type=CounterType.ALPHABETA, counting_run__isnull=True)
        .select_related("sample")
        .order_by("-analysis_date")
    )

    if request.method == "POST":

        action = request.POST.get("action")
        if action == "reopen":
            if run.approvals.filter(status=LabApprovalStatus.REJECTED).exists():
                run.approvals.all().delete()
                run.approved = False
                run.save(update_fields=["approved"])
                messages.success(request, _("Run reopened — fix the samples, then finalize again."))
            return redirect("counting_run_detail", pk=pk)
        if run.approvals.exists():
            messages.error(request, _("This run is finalized and can't be changed."))
            return redirect("counting_run_detail", pk=pk)

        if action == "add_analysis":
            analysis_id = request.POST.get("analysis_id")
            analysis = get_object_or_404(Analysis, pk=analysis_id, detector_type=CounterType.ALPHABETA, counting_run__isnull=True)
            analysis.counting_run = run
            analysis.save(update_fields=["counting_run"])
            messages.success(request, _("Sample added to the run."))
            return redirect("counting_run_detail", pk=pk)

        elif action == "remove_analysis":
            analysis_id = request.POST.get("analysis_id")
            analysis = get_object_or_404(Analysis, pk=analysis_id, counting_run=run)
            analysis.counting_run = None
            analysis.save(update_fields=["counting_run"])
            messages.success(request, _("Sample removed from the run."))
            return redirect("counting_run_detail", pk=pk)

        elif action == "finalize":
            if run.sample_count == 0:
                messages.error(request, _("Add at least one sample before finalizing."))
            else:
                unit = request.POST.get("unit", "KG")
                generate_alpha_beta_report(run, request.user, unit=unit)
                create_counting_run_approval_chain(run)
                messages.success(request, _("Report generated — now goes through the signature chain."))
            return redirect("counting_run_detail", pk=pk)

    report = run.attachments.filter(attachment_type=LabAttachmentType.REPORT).first()
    return render(request, "laboratory/counting_run_detail.html", {
        "run": run,
        "unassigned": unassigned,
        "analyses": run.analyses.select_related("sample").all(),
        "report": report,
        "rejected": run.approvals.filter(status=LabApprovalStatus.REJECTED).exists(),
        "locked": run.approvals.exists() and not run.approvals.filter(status=LabApprovalStatus.REJECTED).exists(),
        "rows_per_page": ALPHA_BETA_ROWS_PER_PAGE ,
    })


# =====================================================================
# SIGNING — one view handles BOTH report kinds via a `kind` URL param,
# since the underlying approve/reject/sign mechanics are identical; only
# the docx template + LabReportSigner row map differ.
# =====================================================================

def _sign_target(kind, pk):
    if kind == "gamma":
        analysis = get_object_or_404(Analysis, pk=pk)
        report_type = "GAMMA"
        target_kwargs = {"analysis": analysis}
        obj = analysis
    else:
        obj = get_object_or_404(AlphaBetaCountingRun, pk=pk)
        report_type = "ALPHA_BETA"
        target_kwargs = {"counting_run": obj}
    return obj, report_type, target_kwargs


def lab_report_sign(request, kind, pk):

    obj, report_kind, target_kwargs = _sign_target(kind, pk)

    approvals = AnalysisApproval.objects.filter(**target_kwargs).order_by("order")
    approval = current_step_for(approvals)

    if approval is None:
        messages.info(request, _("This report is not waiting for a signature."))
        return redirect("lab_home")

    report = AnalysisAttachment.objects.filter(attachment_type=LabAttachmentType.REPORT, **target_kwargs).first()

    upload_form = LabReportUploadForm()

    if request.method == "POST":

        if request.POST.get("action") == "upload":
            upload_form = LabReportUploadForm(request.POST, request.FILES)
            if upload_form.is_valid():
                if report:
                    report.file.delete(save=False)
                    report.delete()
                report = AnalysisAttachment.objects.create(
                    attachment_type=LabAttachmentType.REPORT, uploaded_by=request.user, **target_kwargs,
                )
                report.file.save(os.path.basename(upload_form.cleaned_data["file"].name), upload_form.cleaned_data["file"], save=True)
                messages.success(request, _("Updated report uploaded."))
                return redirect("lab_report_sign", kind=kind, pk=pk)

        elif "reject" in request.POST:
            reject_step(approval, request.user, request.POST.get("comment", ""))
            messages.warning(request, _("Report rejected."))
            return redirect("lab_home")

        elif "approve" in request.POST:
            profile = request.user.profile
            if not profile.signature_image:
                messages.error(request, _("Please upload your signature image first."))
                return redirect("profile")

            from .services.signature_service import PdfReportSigner
            signer = PdfReportSigner(report.file.path, approvals)
            signer.sign(approval, profile)   # mutates the attachment's file in place

            approve_step(approval, request.user, request.POST.get("comment", ""))
            messages.success(request, _("Signed successfully."))
            return redirect("lab_home")

    return render(request, "laboratory/lab_report_sign.html", {
        "kind": kind, "object": obj, "approval": approval, "approvals": approvals,
        "report": report, "upload_form": upload_form,
    })
# =====================================================
# HOME / QUEUES
# =====================================================

def sample_reject(request, pk):
    sample = get_object_or_404(Sample, pk=pk)

    if request.method == "POST":
        if sample.status in (SampleStatus.COMPLETED, SampleStatus.REJECTED):
            messages.error(request, _("This sample can't be rejected in its current status."))
        else:
            sample.status = SampleStatus.REJECTED
            sample.rejection_reason = request.POST.get("reason", "").strip()
            sample.rejected_by = request.user
            sample.rejected_at = timezone.now()
            sample.rejection_seen = False          # <- this is the notification
            sample.save(update_fields=["status", "rejection_reason", "rejected_by", "rejected_at", "rejection_seen"])
            messages.success(request, _("Sample rejected. The collector will be notified."))

    return redirect("sample_detail", pk=pk)


def sample_resubmit(request, pk):
    sample = get_object_or_404(Sample, pk=pk, status=SampleStatus.REJECTED)
    if request.method == "POST":
        sample.status = SampleStatus.COLLECTED
        sample.rejection_seen = True
        sample.save(update_fields=["status", "rejection_seen"])
        messages.success(request, _("Sample resubmitted as Collected."))
    return redirect("sample_detail", pk=pk)


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
    mine = "1" if request.GET.get("mine") else ""
    if mine:
        queryset = queryset.filter(collected_by=request.user)
    atype = request.GET.get("type", "")
    if atype:
        queryset = queryset.filter(analysis_type=atype)
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
        "atype":atype,
        "mine":mine,
        "status_choices": SampleStatus.choices,
    })


SIGNATURE_PAGES = {
    "analyst": (LabApprovalRole.ANALYST, _("Waiting for the Analysis Lab Expert")),
    "lab-manager": (LabApprovalRole.LAB_MANAGER, _("Waiting for the Lab Manager")),
    "ops-manager": (LabApprovalRole.OPS_MANAGER, _("Waiting for Operations / Operations Control Manager")),
}


def signature_queue(request, role_key):
    role, title = SIGNATURE_PAGES[role_key]
    items = [
        {
            "step": step,
            "kind": "gamma" if step.analysis_id else "alpha-beta",
            "target": step.analysis or step.counting_run,
            "pk": step.analysis_id or step.counting_run_id,
        }
        for step in pending_steps_for_role(role)
    ]
    return render(request, "laboratory/signature_queue.html", {
        "items": items,
        "title": title,
        "role_key": role_key,
        "rejected": rejected_steps() if role_key == "analyst" else [],
    })


def finalized_reports(request):
    search = request.GET.get("search", "").strip()
    kind = request.GET.get("kind", "")

    gamma = (
        Analysis.objects.filter(approved=True, approvals__isnull=False)
        .select_related("sample").prefetch_related("attachments", "approvals__user").distinct()
    )
    runs = AlphaBetaCountingRun.objects.filter(approved=True).prefetch_related("attachments", "approvals__user")
    if search:
        gamma = gamma.filter(Q(sample__sample_id__icontains=search) | Q(sample__sample_code_barcode__icontains=search))
        runs = runs.filter(run_id__icontains=search)

    def finalized_on(approvals):
        return max((s.signed_date for s in approvals if s.signed_date), default=None)

    rows = []
    if kind in ("", "gamma"):
        for a in gamma:
            approvals = list(a.approvals.all())
            rows.append({
                "kind": "gamma", "label": a.sample.sample_id, "extra": "",
                "url": reverse("sample_detail", args=[a.sample_id]),
                "date": a.analysis_date, "finalized_on": finalized_on(approvals),
                "approvals": approvals, "attachments": a.attachments.all(),
            })
    if kind in ("", "alpha-beta"):
        for r in runs:
            approvals = list(r.approvals.all())
            rows.append({
                "kind": "alpha-beta", "label": r.run_id, "extra": f"({r.sample_count})",
                "url": reverse("counting_run_detail", args=[r.pk]),
                "date": r.run_date, "finalized_on": finalized_on(approvals),
                "approvals": approvals, "attachments": r.attachments.all(),
            })

    rows.sort(key=lambda r: r["finalized_on"] or datetime.date.min, reverse=True)
    page_obj = Paginator(rows, 25).get_page(request.GET.get("page"))
    return render(request, "laboratory/finalized_reports.html", {"page_obj": page_obj, "search": search, "kind": kind})
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
    if (
        sample.status == SampleStatus.REJECTED
        and not sample.rejection_seen
        and sample.collected_by_id == request.user.id):

            sample.rejection_seen = True
            sample.save(update_fields=["rejection_seen"])
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
    sample = get_object_or_404(Sample.objects.select_related("batch"), pk=pk)
    analysis = getattr(sample, "analysis", None)

    if not sample.analysis_type:
        messages.error(request, _("Set the analysis type (Gamma or Alpha/Beta) on the sample first."))
        return redirect("sample_edit", pk=sample.pk)

    detector_type = sample.analysis_type
    is_gamma = detector_type == CounterType.HPGE

    # Once anybody has signed, the report is frozen.
    if analysis and (
        analysis.approved
        or analysis.approvals.filter(status=LabApprovalStatus.APPROVED).exists()
        or (analysis.counting_run_id and analysis.counting_run.approvals.exists())
    ):
        messages.error(request, _("This analysis is already in/through the signature chain and can't be edited."))
        return redirect("sample_detail", pk=sample.pk)

    if request.method == "POST":
        form = AnalysisForm(request.POST, instance=analysis, detector_type=detector_type)

        if form.is_valid():
            with transaction.atomic():
                analysis = form.save(commit=False)
                analysis.sample = sample
                analysis.detector_type = detector_type
                if not analysis.analyst_id:
                    analysis.analyst = request.user
                analysis.save()

                formset = None
                if is_gamma:
                    formset = NuclideActivityFormSet(request.POST, instance=analysis)
                    if not formset.is_valid():
                        transaction.set_rollback(True)
                        messages.error(request, _("Please correct the nuclide rows below."))
                        return render(request, "laboratory/analysis_form.html", {
                            "sample": sample, "form": form, "formset": formset,
                        })
                    formset.save()

                if sample.status != SampleStatus.COMPLETED:
                    sample.status = SampleStatus.COMPLETED
                    sample.save(update_fields=["status"])

                def _analysis_locked(analysis):
                    if not analysis:
                        return False
                    steps = list(analysis.approvals.all())
                    if any(s.status == LabApprovalStatus.REJECTED for s in steps):
                        return False                       # rejected -> allowed to rework
                    if any(s.status == LabApprovalStatus.APPROVED for s in steps):
                        return True                        # someone already signed
                    run = analysis.counting_run
                    if run and run.approvals.exists() and not run.approvals.filter(status=LabApprovalStatus.REJECTED).exists():
                        return True
                    return analysis.approved
                if _analysis_locked(analysis):
                    messages.error(request, _("This analysis is already in/through the signature chain and can't be edited."))
                    return redirect("sample_detail", pk=sample.pk)
                if is_gamma:
                    analysis.approvals.all().delete()
                    if form.cleaned_data.get("generate_report"):
                        create_analysis_approval_chain(analysis)
                        unit = request.POST.get("unit", "KG")
                        generate_gamma_report(analysis, request.user, unit=unit)
                    else:
                        for att in analysis.attachments.filter(attachment_type=LabAttachmentType.REPORT):
                            att.file.delete(save=False)
                            att.delete()

            if is_gamma:
                messages.success(request, _("Analysis saved — report generated, waiting for signatures."))
            elif analysis.counting_run_id:
                messages.success(request, _("Analysis saved and added to the counting run."))
            else:
                messages.warning(request, _("Analysis saved. Add it to a counting run to get a report."))
            return redirect("sample_detail", pk=sample.pk)

        formset = NuclideActivityFormSet(request.POST, instance=analysis) if is_gamma else None

    else:
        form = AnalysisForm(instance=analysis, detector_type=detector_type)
        formset = NuclideActivityFormSet(instance=analysis) if is_gamma else None

    return render(request, "laboratory/analysis_form.html", {
        "sample": sample, "analysis": analysis, "form": form, "formset": formset,
    })
    

def analysis_generate_report(request, pk):
    analysis = get_object_or_404(Analysis.objects.select_related("sample"), pk=pk, detector_type=CounterType.HPGE)
    if request.method == "POST":
        if analysis.approvals.exists():
            messages.info(request, _("This analysis already has a report."))
        elif analysis.approved:
            messages.error(request, _("This analysis was already approved without a report."))
        else:
            with transaction.atomic():
                create_analysis_approval_chain(analysis)
                unit = request.POST.get("unit", "KG")
                generate_gamma_report(analysis, request.user, unit=unit)
            messages.success(request, _("Report generated — waiting for signatures."))
    return redirect("sample_detail", pk=analysis.sample_id)


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
            s.sample_mass_kg, s.sample_volume_ml, s.urgent, s.status,
            s.collected_by.username if s.collected_by else "",
            s.sent_to_lab_date, s.lab_received_date,
            analysis.analysis_date if analysis else "",
            analysis.total_alpha if analysis else "",
            analysis.total_beta if analysis else "",
            analysis.approved if analysis else "",
            nuclides,
        ])

    return response
