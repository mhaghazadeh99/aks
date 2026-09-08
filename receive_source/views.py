import os
import tempfile

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files import File
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render, reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from dashboard.models import DSRS, SOURCE_STATUS

from .forms import (
    ReceiveRequestForm,
    ReceiveFacilityForm,
    ReceiveAttachmentForm,
    ReceiveSourceForm,
    LicenseMatchChoiceForm,
    SpecificationUploadForm,
    ReceiveContractForm,
    ReceivePaymentForm,
    DSRSCharacterizationForm,
    CharacterizationDocForm,
)
from .models import (
    ReceiveRequest,
    ReceiveStatus,
    ReceiveSource,
    ReceiveItemType,
    ReceiveAttachment,
    ReceiveAttachmentType,
    ReceiveContract,
    ReceivePayment,
    ReceiveApproval,
)
from .services.workflow import (
    create_receive_workflow,
    maybe_add_ceo_step,
    snapshot_half_life,
    create_dsrs_for_receive_request,
    mark_source_stored,
)
from .services.license_check import (
    find_license_contract_match,
    annotate_source_with_match,
    confirm_match,
)


# =====================================================================
# HOME / QUEUES
# =====================================================================

def receiving_home(request):
    return render(request, "receive_source/receiving_home.html")


def receive_list(request):

    search = request.GET.get("search", "")
    page_size = request.GET.get("page_size", "10")

    queryset = (
        ReceiveRequest.objects
        .select_related("facility", "contract", "payment")
        .prefetch_related("sources__nuclide", "attachments")
        .order_by("-created_at")
    )

    if search:
        queryset = queryset.filter(
            Q(facility__name__icontains=search)
            | Q(inquiry_letter_number__icontains=search)
            | Q(sources__serial_number__icontains=search)
            | Q(sources__nuclide__name__icontains=search)
        ).distinct()

    paginator = Paginator(queryset, int(page_size))
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "receive_source/receive_list.html",
        {"page_obj": page_obj, "search": search, "page_size": int(page_size)},
    )


def _queue(request, status, page_title):
    queryset = (
        ReceiveRequest.objects
        .select_related("facility", "created_by")
        .prefetch_related("sources")
        .filter(status=status)
        .order_by("-created_at")
    )

    search = request.GET.get("search", "")
    if search:
        queryset = queryset.filter(
            Q(facility__name__icontains=search) | Q(inquiry_letter_number__icontains=search)
        )

    paginator = Paginator(queryset, 15)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "receive_source/receive_queue.html",
        {"page_title": page_title, "page_obj": page_obj, "search": search},
    )


def manager_input_queue(request):
    """Both Operation Manager and Operation Control Manager work from here
    during data entry — before either of them has anything to SIGN, they
    have data to FILL IN. This is distinct from manager_queue/control_queue
    below, which are for the later signature step."""
    return _queue(request, ReceiveStatus.WAITING_MANAGER_INPUT, _("Manager Data Entry"))


def manager_queue(request):
    return _queue(request, ReceiveStatus.WAITING_MANAGER, _("Operation Manager"))


def control_queue(request):
    return _queue(request, ReceiveStatus.WAITING_CONTROL, _("Operation Control Manager"))


def deputy_queue(request):
    return _queue(request, ReceiveStatus.WAITING_DEPUTY, _("Deputy Manager"))


def ceo_queue(request):
    return _queue(request, ReceiveStatus.WAITING_CEO, _("CEO"))


def contracts_queue(request):
    return _queue(request, ReceiveStatus.CONTRACTS, _("Contracts"))


def finance_queue(request):
    return _queue(request, ReceiveStatus.FINANCE, _("Finance"))


def receiving_queue(request):
    return _queue(request, ReceiveStatus.RECEIVING, _("Receiving / Characterization"))


# =====================================================================
# STEP 1+2 — CREATE REQUEST (header, facility, attachments) — DRAFT
# =====================================================================

def receive_create(request, pk=None):

    instance = None
    if pk is not None:
        instance = get_object_or_404(ReceiveRequest, pk=pk)
        if instance.status != ReceiveStatus.DRAFT:
            messages.info(request, _("This request is no longer a draft and can't be edited here."))
            return redirect("receive_detail", pk=pk)

    def build_forms(post=None, files=None):
        return {
            "request_form": ReceiveRequestForm(post, instance=instance),
            "facility_form": ReceiveFacilityForm(
                post,
                initial=({"facility": instance.facility} if instance else None),
            ),
            "attachment_form": ReceiveAttachmentForm(post, files),
        }

    if request.method == "POST":

        forms = build_forms(request.POST, request.FILES)
        request_form = forms["request_form"]
        facility_form = forms["facility_form"]
        attachment_form = forms["attachment_form"]

        if request_form.is_valid() and facility_form.is_valid() and attachment_form.is_valid():

            with transaction.atomic():

                receive_request = request_form.save(commit=False)
                receive_request.facility = facility_form.cleaned_data["facility"]

                action = request.POST.get("action")

                if instance is None:
                    receive_request.created_by = request.user

                receive_request.status = (
                    ReceiveStatus.DRAFT if action == "draft" else ReceiveStatus.SPECIFICATION
                )
                receive_request.status_date = timezone.now()
                receive_request.save()

                if instance is None:
                    create_receive_workflow(receive_request)

                files = {
                    ReceiveAttachmentType.INQUIRY: attachment_form.cleaned_data.get("inquiry", []),
                    ReceiveAttachmentType.LETTER: attachment_form.cleaned_data.get("letter", []),
                    ReceiveAttachmentType.OTHER: attachment_form.cleaned_data.get("other", []),
                }
                for attachment_type, uploaded_files in files.items():
                    for uploaded_file in uploaded_files:
                        ReceiveAttachment.objects.create(
                            receive_request=receive_request,
                            attachment_type=attachment_type,
                            file=uploaded_file,
                            uploaded_by=request.user,
                        )

            messages.success(request, _("Receive request saved successfully."))

            if action == "draft":
                return redirect("receive_list")

            return redirect("receive_add_sources", pk=receive_request.pk)

    else:
        forms = build_forms()

    if instance is not None:
        forms["existing_attachments"] = instance.attachments.all()

    forms["instance"] = instance
    return render(request, "receive_source/receive_create.html", forms)


# =====================================================================
# STEP 3 — ADD SOURCES (coordinator), with license-contract check
# =====================================================================

def receive_add_sources(request, pk):

    receive_request = get_object_or_404(ReceiveRequest, pk=pk)

    if receive_request.status not in (ReceiveStatus.SPECIFICATION,):
        messages.info(request, _("Sources can only be added while the request is in the Specification stage."))
        return redirect("receive_detail", pk=pk)

    sources = receive_request.sources.select_related("nuclide", "matched_license_dsrs").order_by("specification_order")

    session_key = f"receive_pending_match_{pk}"
    pending_match = request.session.get(session_key)
    candidates = []
    match_form = None

    if request.method == "POST":

        if "confirm_match" in request.POST:
            # Second step: resolving a fuzzy candidate list from session state
            match_form = LicenseMatchChoiceForm(request.POST, candidates=_rehydrate_candidates(pending_match))

            if match_form.is_valid():
                choice = match_form.cleaned_data["choice"]

                source = ReceiveSource.objects.create(
                    receive_request=receive_request,
                    item_type=pending_match["item_type"],
                    nuclide_id=pending_match["nuclide_id"],
                    serial_number=pending_match["serial_number"],
                    average_activity_mci=pending_match["average_activity_mci"] or None,
                    quantity=pending_match["quantity"],
                    specification_order=sources.count() + 1,
                )
                snapshot_half_life(source)

                if choice != LicenseMatchChoiceForm.NONE_VALUE:
                    chosen_dsrs = get_object_or_404(DSRS, pk=int(choice))
                    confirm_match(source, chosen_dsrs)

                del request.session[session_key]
                messages.success(request, _("Source added."))
                return redirect("receive_add_sources", pk=pk)

        else:

            source_form = ReceiveSourceForm(request.POST, facility=receive_request.facility)

            if source_form.is_valid():

                data = source_form.cleaned_data

                if data["source_origin"] == ReceiveSourceForm.SOURCE_ORIGIN_INVENTORY:

                    # Picked directly from the facility's contracted
                    # inventory — already an exact, certain match. No need
                    # to run the fuzzy-match check at all.
                    dsrs = data["inventory_dsrs"]

                    source = ReceiveSource.objects.create(
                        receive_request=receive_request,
                        item_type=data["item_type"],
                        nuclide=data["nuclide"],
                        serial_number=data["serial_number"],
                        average_activity_mci=data["average_activity_mci"],
                        quantity=data["quantity"],
                        specification_order=sources.count() + 1,
                    )
                    snapshot_half_life(source)
                    confirm_match(source, dsrs)  # matched_license_dsrs + description note

                    messages.success(request, _("Source added from inventory."))
                    return redirect("receive_add_sources", pk=pk)

                result = find_license_contract_match(
                    facility=receive_request.facility,
                    nuclide=data["nuclide"],
                    serial_number=data["serial_number"],
                )

                if result["exact"] or not result["candidates"]:
                    # Either an exact hit (auto-annotate) or nothing at all
                    # (no candidates to ask about) — create the row directly.
                    source = ReceiveSource.objects.create(
                        receive_request=receive_request,
                        item_type=data["item_type"],
                        nuclide=data["nuclide"],
                        serial_number=data["serial_number"],
                        average_activity_mci=data["average_activity_mci"],
                        quantity=data["quantity"],
                        specification_order=sources.count() + 1,
                    )
                    snapshot_half_life(source)
                    if result["exact"]:
                        annotate_source_with_match(source, receive_request.facility)

                    messages.success(request, _("Source added."))
                    return redirect("receive_add_sources", pk=pk)

                else:
                    # Fuzzy candidates found — stash the row's data in the
                    # session and ask the creator to confirm before creating it.
                    request.session[session_key] = {
                        "item_type": data["item_type"],
                        "nuclide_id": data["nuclide"].pk,
                        "serial_number": data["serial_number"],
                        "average_activity_mci": str(data["average_activity_mci"] or ""),
                        "quantity": data["quantity"],
                        "candidate_ids": [d.pk for d in result["candidates"]],
                    }
                    candidates = result["candidates"]
                    match_form = LicenseMatchChoiceForm(candidates=candidates)

    source_form = ReceiveSourceForm(facility=receive_request.facility)

    if pending_match and match_form is None:
        candidates = _rehydrate_candidates(pending_match)
        match_form = LicenseMatchChoiceForm(candidates=candidates)

    return render(
        request,
        "receive_source/receive_add_sources.html",
        {
            "receive_request": receive_request,
            "sources": sources,
            "source_form": source_form,
            "match_form": match_form,
        },
    )


def _rehydrate_candidates(pending_match):
    if not pending_match:
        return []
    return list(DSRS.objects.filter(pk__in=pending_match["candidate_ids"]).select_related("contract"))


def receive_finish_sources(request, pk):
    """Coordinator is done adding sources -> generate the specification
    doc now (identity fields filled; characterization columns + the
    whole logistics section left blank for hand-filling) and move to
    the creator's own fill-in-Word-then-sign stage."""

    receive_request = get_object_or_404(ReceiveRequest, pk=pk, status=ReceiveStatus.SPECIFICATION)

    if not receive_request.sources.exists():
        messages.error(request, _("Add at least one source before continuing."))
        return redirect("receive_add_sources", pk=pk)

    from .services.specification_generator import generate_receive_specification
    generate_receive_specification(receive_request, request.user)

    receive_request.status = ReceiveStatus.WAITING_CREATOR
    receive_request.status_date = timezone.now()
    receive_request.specification_completed = True
    receive_request.save(update_fields=["status", "status_date", "specification_completed"])

    messages.success(request, _("Specification generated — download it, fill in the source details, then sign."))
    return redirect("receive_sign", pk=pk)


# =====================================================================
# STEP 4 — MANAGER DATA ENTRY: fill the logistics section directly in
# the docx (shared access — either manager can upload), then move on
# to the Operation Manager's own signature. Nothing here is stored in
# the DB; the docx is the only record.
# =====================================================================

def receive_manager_input(request, pk):

    receive_request = get_object_or_404(ReceiveRequest, pk=pk, status=ReceiveStatus.WAITING_MANAGER_INPUT)

    specification = receive_request.attachments.filter(
        attachment_type=ReceiveAttachmentType.SPECIFICATION
    ).first()

    if request.method == "POST":

        upload_form = SpecificationUploadForm(request.POST, request.FILES)

        if upload_form.is_valid():

            if specification:
                specification.file.delete(save=False)
                specification.delete()

            ReceiveAttachment.objects.create(
                receive_request=receive_request,
                attachment_type=ReceiveAttachmentType.SPECIFICATION,
                file=upload_form.cleaned_data["file"],
                uploaded_by=request.user,
            )

            messages.success(request, _("Updated specification uploaded."))
            return redirect("receive_manager_input", pk=pk)

    else:
        upload_form = SpecificationUploadForm()

    return render(
        request,
        "receive_source/receive_manager_input.html",
        {
            "receive_request": receive_request,
            "specification": specification,
            "upload_form": upload_form,
        },
    )


def receive_manager_input_done(request, pk):
    """Either manager marks the logistics section done -> Operation
    Manager's own signature step."""

    receive_request = get_object_or_404(ReceiveRequest, pk=pk, status=ReceiveStatus.WAITING_MANAGER_INPUT)

    receive_request.status = ReceiveStatus.WAITING_MANAGER
    receive_request.status_date = timezone.now()
    receive_request.save(update_fields=["status", "status_date"])

    messages.success(request, _("Data entry complete — ready for the Operation Manager's signature."))
    return redirect("receive_detail", pk=pk)


# =====================================================================
# STEP 5 — SIGNATURES (Creator -> [manager data entry] -> Manager ->
# Control -> Deputy -> [CEO])
# =====================================================================

STATUS_TO_STEP = {
    ReceiveStatus.WAITING_CREATOR: ReceiveApproval.ApprovalStep.CREATOR,
    ReceiveStatus.WAITING_MANAGER: ReceiveApproval.ApprovalStep.MANAGER,
    ReceiveStatus.WAITING_CONTROL: ReceiveApproval.ApprovalStep.CONTROL,
    ReceiveStatus.WAITING_DEPUTY: ReceiveApproval.ApprovalStep.DEPUTY,
    ReceiveStatus.WAITING_CEO: ReceiveApproval.ApprovalStep.CEO,
}

# Creator signs -> managers get the docx to fill logistics into BEFORE
# the Operation Manager's own signature (WAITING_MANAGER_INPUT sits
# between CREATOR and MANAGER, not before CREATOR like before).
NEXT_STATUS = {
    ReceiveApproval.ApprovalStep.CREATOR: ReceiveStatus.WAITING_MANAGER_INPUT,
    ReceiveApproval.ApprovalStep.MANAGER: ReceiveStatus.WAITING_CONTROL,
    ReceiveApproval.ApprovalStep.CONTROL: ReceiveStatus.WAITING_DEPUTY,
    ReceiveApproval.ApprovalStep.DEPUTY: ReceiveStatus.CONTRACTS,
    ReceiveApproval.ApprovalStep.CEO: ReceiveStatus.FINANCE,
}

QUEUE_REDIRECT = {
    ReceiveApproval.ApprovalStep.CREATOR: "receive_manager_input_queue",
    ReceiveApproval.ApprovalStep.MANAGER: "receive_manager_queue",
    ReceiveApproval.ApprovalStep.CONTROL: "receive_control_queue",
    ReceiveApproval.ApprovalStep.DEPUTY: "receive_deputy_queue",
    ReceiveApproval.ApprovalStep.CEO: "receive_ceo_queue",
}


def receive_sign(request, pk):

    receive_request = get_object_or_404(ReceiveRequest, pk=pk)

    current_step = STATUS_TO_STEP.get(receive_request.status)

    if current_step is None:
        messages.info(request, _("This request is not waiting for a signature."))
        return redirect("receive_detail", pk=pk)

    specification = get_object_or_404(
        ReceiveAttachment,
        receive_request=receive_request,
        attachment_type=ReceiveAttachmentType.SPECIFICATION,
    )

    approval = get_object_or_404(ReceiveApproval, receive_request=receive_request, step=current_step)
    history = ReceiveApproval.objects.filter(receive_request=receive_request).order_by("order")

    upload_form = SpecificationUploadForm()

    if request.method == "POST":

        if request.POST.get("action") == "upload":

            upload_form = SpecificationUploadForm(request.POST, request.FILES)

            if upload_form.is_valid():
                specification.file.delete(save=False)
                specification.delete()

                specification = ReceiveAttachment.objects.create(
                    receive_request=receive_request,
                    attachment_type=ReceiveAttachmentType.SPECIFICATION,
                    file=upload_form.cleaned_data["file"],
                    uploaded_by=request.user,
                )

                messages.success(request, _("Updated specification uploaded."))
                return redirect("receive_sign", pk=pk)

        else:

            profile = request.user.profile

            if not profile.signature_image:
                messages.error(request, _("Please upload your signature image first."))
                return redirect(f"{reverse('profile')}?next={request.path}")

            # Receive-specific signer — the license app's SpecificationSigner is
            # hardcoded to a different template layout (row 15/16, only 3 steps)
            # and is NOT reusable here. See services/signature_service.py.
            from .services.signature_service import ReceiveSpecificationSigner

            tmp = tempfile.NamedTemporaryFile(suffix=".docx", delete=False)
            tmp.close()

            signer = ReceiveSpecificationSigner(specification.file.path)
            signer.sign(profile, current_step.name)
            signer.save(tmp.name)

            with open(tmp.name, "rb") as f:
                specification.file.save(os.path.basename(specification.file.name), File(f), save=False)
            specification.save()
            os.remove(tmp.name)

            with transaction.atomic():
                approval.status = ReceiveApproval.ApprovalStatus.APPROVED
                approval.approver = request.user
                approval.approved_at = timezone.now()
                approval.save()

                receive_request.status = NEXT_STATUS[current_step]
                receive_request.status_date = timezone.now()
                receive_request.save(update_fields=["status", "status_date"])

            messages.success(request, _("Specification signed successfully."))
            return redirect(QUEUE_REDIRECT[current_step])

    return render(
        request,
        "receive_source/receive_sign.html",
        {
            "receive_request": receive_request,
            "specification": specification,
            "approval": approval,
            "history": history,
            "upload_form": upload_form,
            "contract": getattr(receive_request, "contract", None),
        },
    )


# =====================================================================
# STEP 6 — CONTRACT (discount decides whether CEO signs)
# =====================================================================

def receive_contract_create(request, pk):

    receive_request = get_object_or_404(ReceiveRequest, pk=pk, status=ReceiveStatus.CONTRACTS)

    if hasattr(receive_request, "contract"):
        return redirect("receive_contract_update", pk=receive_request.contract.pk)

    if request.method == "POST":

        form = ReceiveContractForm(request.POST, request.FILES)

        if form.is_valid():

            contract = form.save(commit=False)
            contract.receive_request = receive_request
            contract.save()

            maybe_add_ceo_step(receive_request)

            messages.success(request, _("Cost declaration saved."))
            return redirect("receive_contracts_queue")

    else:
        form = ReceiveContractForm()

    history = ReceiveApproval.objects.filter(receive_request=receive_request).order_by("order")
    sources = receive_request.sources.select_related("nuclide", "matched_license_dsrs").all()
    specification = receive_request.attachments.filter(attachment_type=ReceiveAttachmentType.SPECIFICATION).first()

    return render(
        request,
        "receive_source/receive_contract_form.html",
        {
            "form": form,
            "receive_request": receive_request,
            "history": history,
            "sources": sources,
            "specification": specification,
            "page_title": _("Declare Waste Management Cost"),
            "submit_text": _("Save"),
        },
    )


def receive_contract_update(request, pk):

    contract = get_object_or_404(ReceiveContract, pk=pk)
    receive_request = contract.receive_request

    if request.method == "POST":

        form = ReceiveContractForm(request.POST, request.FILES, instance=contract)

        if form.is_valid():

            contract = form.save()

            if receive_request.status == ReceiveStatus.CONTRACTS:
                maybe_add_ceo_step(receive_request)

            messages.success(request, _("Cost declaration updated."))
            return redirect("receive_contracts_queue")

    else:
        form = ReceiveContractForm(instance=contract)

    history = ReceiveApproval.objects.filter(receive_request=receive_request).order_by("order")
    sources = receive_request.sources.select_related("nuclide", "matched_license_dsrs").all()
    specification = receive_request.attachments.filter(attachment_type=ReceiveAttachmentType.SPECIFICATION).first()

    return render(
        request,
        "receive_source/receive_contract_form.html",
        {
            "form": form,
            "contract": contract,
            "receive_request": receive_request,
            "history": history,
            "sources": sources,
            "specification": specification,
            "page_title": _("Update Waste Management Cost"),
            "submit_text": _("Save Changes"),
        },
    )


# =====================================================================
# STEP 7 — FINANCE / PAYMENT
# =====================================================================

def receive_payment_update(request, pk):

    receive_request = get_object_or_404(ReceiveRequest, pk=pk)
    payment, _created = ReceivePayment.objects.get_or_create(receive_request=receive_request)

    if request.method == "POST":

        form = ReceivePaymentForm(request.POST, request.FILES, instance=payment)

        if form.is_valid():

            payment = form.save()

            if payment.payment_done and receive_request.status == ReceiveStatus.FINANCE:
                receive_request.status = ReceiveStatus.READY_TO_RECEIVE
                receive_request.status_date = timezone.now()
                receive_request.save(update_fields=["status", "status_date"])

                # Source records get created here — right after payment —
                # per current policy, status IN_USE until characterized+stored.
                create_dsrs_for_receive_request(receive_request, performed_by=request.user)

            messages.success(request, _("Payment information saved successfully."))
            return redirect("receive_finance_queue")

    else:
        form = ReceivePaymentForm(instance=payment)

    return render(
        request,
        "receive_source/receive_payment_form.html",
        {"form": form, "receive_request": receive_request, "contract": getattr(receive_request, "contract", None), "payment": payment},
    )


# =====================================================================
# STEP 8 — RECEIVING / CHARACTERIZATION
# =====================================================================

def receive_characterization(request, pk):

    # No status filter here — marking the last source stored can complete
    # the whole request mid-visit (see dsrs_mark_stored below), and this
    # page should still render (read-only-ish) rather than 404.
    receive_request = get_object_or_404(ReceiveRequest, pk=pk)

    sources = (
        receive_request.sources
        .select_related("nuclide", "matched_license_dsrs")
        .prefetch_related("result_dsrs")
        .order_by("specification_order")
    )

    # Flatten to one row per DSRS — a source with quantity > 1 has
    # several independently-editable DSRS records, not one shared row.
    rows = []
    for source in sources:
        dsrs_list = list(source.result_dsrs.all())
        if dsrs_list:
            for dsrs in dsrs_list:
                rows.append({"source": source, "dsrs": dsrs})
        else:
            rows.append({"source": source, "dsrs": None})

    return render(
        request,
        "receive_source/receive_characterization.html",
        {"receive_request": receive_request, "rows": rows},
    )


def dsrs_characterization_update(request, pk, dsrs_pk):

    receive_request = get_object_or_404(ReceiveRequest, pk=pk)
    dsrs = get_object_or_404(DSRS, pk=dsrs_pk)

    if request.method == "POST":

        form = DSRSCharacterizationForm(request.POST, instance=dsrs)
        doc_form = CharacterizationDocForm(request.POST, request.FILES)

        if form.is_valid() and doc_form.is_valid():

            form.save()

            for uploaded_file in doc_form.cleaned_data.get("files", []):
                ReceiveAttachment.objects.create(
                    receive_request=receive_request,
                    attachment_type=ReceiveAttachmentType.CHARACTERIZATION,
                    file=uploaded_file,
                    uploaded_by=request.user,
                )

            messages.success(request, _("Characterization saved."))
            return redirect("receive_characterization", pk=pk)

    else:
        form = DSRSCharacterizationForm(instance=dsrs)
        doc_form = CharacterizationDocForm()

    return render(
        request,
        "receive_source/dsrs_characterization_form.html",
        {"receive_request": receive_request, "dsrs": dsrs, "form": form, "doc_form": doc_form},
    )


def dsrs_mark_stored(request, pk, dsrs_pk):

    receive_request = get_object_or_404(ReceiveRequest, pk=pk)
    dsrs = get_object_or_404(DSRS, pk=dsrs_pk)

    if request.method == "POST":
        mark_source_stored(dsrs, receive_request, performed_by=request.user)
        messages.success(request, _("Source marked as stored."))

        receive_request.refresh_from_db(fields=["status"])
        if receive_request.status == ReceiveStatus.COMPLETED:
            messages.success(request, _("All sources stored — this request is now complete."))
            return redirect("receive_detail", pk=pk)

    return redirect("receive_characterization", pk=pk)


# =====================================================================
# DETAIL
# =====================================================================

def receive_detail(request, pk):

    receive_request = get_object_or_404(
        ReceiveRequest.objects
        .select_related("facility", "created_by")
        .prefetch_related("attachments", "sources__nuclide", "sources__result_dsrs", "approvals"),
        pk=pk,
    )

    return render(request, "receive_source/receive_detail.html", {"receive_request": receive_request})
