from io import BytesIO
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _

from . import docx_export
from .forms_receipt import (MinutesForm, ReceiptForm, SignedMinutesForm, StartLineFormSet,
                            minutes_line_formset)
from .models import WasteType
from .models_receipt import ReceiptStatus, WasteReceipt
from .receipt_services import ReceiptError, finalize_receipt, planned_batch_count, receipt_to_context

PAGE_SIZES = ("10", "25", "50", "all")


def _can_complete(user, receipt):
    # the responsible person, or anyone holding the manage permission
    return user == receipt.received_by or user.has_perm("waste.manage_receipts")


@login_required
def receipt_list(request):
    qs = (WasteReceipt.objects
          .select_related("origin_facility", "facility", "received_by__profile")
          .annotate(line_count=Count("lines", distinct=True)))

    search = request.GET.get("search", "").strip()
    if search:
        qs = qs.filter(
            Q(letter_number__icontains=search) | Q(minutes_number__icontains=search)
            | Q(laboratory__icontains=search) | Q(lines__batch__waste_id__icontains=search)
            | Q(lines__packages__batch__waste_id__icontains=search)
        ).distinct()

    status = request.GET.get("status", "")
    if status in ReceiptStatus.values:
        qs = qs.filter(status=status)
    else:
        status = ""

    size = request.GET.get("size", "10")
    if size not in PAGE_SIZES:
        size = "10"
    per_page = max(qs.count(), 1) if size == "all" else int(size)
    page_obj = Paginator(qs, per_page).get_page(request.GET.get("page"))

    for r in page_obj:                      # per-row permission flag for the action icons
        r.can_complete = _can_complete(request.user, r)

    extra = {"size": size, "status": status, "search": search}
    extra_qs = urlencode({k: v for k, v in extra.items() if v})
    return render(request, "waste/receipt/list.html", {
        "page_obj": page_obj, "search": search, "current_status": status,
        "statuses": ReceiptStatus.choices, "page_size": size,
        "extra_qs": f"&{extra_qs}" if extra_qs else "", "S": ReceiptStatus,
    })


@login_required
def receipt_detail(request, pk):
    receipt = get_object_or_404(
        WasteReceipt.objects.select_related("origin_facility", "facility", "received_by__profile")
        .prefetch_related("nuclides"), pk=pk)
    return render(request, "waste/receipt/detail.html", {
        "receipt": receipt,
        "lines": receipt.lines.select_related("batch").prefetch_related("packages__batch"),
        "can_complete": _can_complete(request.user, receipt),
        "S": ReceiptStatus,
    })


@login_required
def receipt_create(request):                         # STEP 1
    if request.method == "POST":
        form = ReceiptForm(request.POST, request.FILES)
        if form.is_valid():
            receipt = form.save(commit=False)
            receipt.created_by = request.user
            formset = StartLineFormSet(request.POST, instance=receipt)
            if formset.is_valid():
                with transaction.atomic():
                    receipt.save()
                    formset.save()
                messages.success(request, _("Receipt registered. The responsible person can now complete the minutes."))
                return redirect("waste_receipt_detail", pk=receipt.pk)
        else:
            formset = StartLineFormSet(request.POST, instance=WasteReceipt(waste_type=request.POST.get("waste_type") or WasteType.SOLID))
    else:
        form = ReceiptForm()
        formset = StartLineFormSet(instance=WasteReceipt(waste_type=WasteType.SOLID))
    return render(request, "waste/receipt/create.html", {"form": form, "formset": formset})


@login_required
def receipt_minutes(request, pk):                    # STEP 2
    receipt = get_object_or_404(WasteReceipt, pk=pk)
    if not _can_complete(request.user, receipt):
        raise PermissionDenied
    if not receipt.is_editable:
        messages.error(request, _("This receipt is closed."))
        return redirect("waste_receipt_detail", pk=pk)

    LineFS = minutes_line_formset(receipt.waste_type)
    form = MinutesForm(request.POST or None, instance=receipt)
    formset = LineFS(request.POST or None, instance=receipt)
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        with transaction.atomic():
            form.save()
            formset.save()
            receipt.status = ReceiptStatus.MINUTES_READY
            receipt.save(update_fields=["status", "updated_at"])
        messages.success(request, _("Minutes data saved. Download the form, print it and get it signed."))
        return redirect("waste_receipt_detail", pk=pk)
    return render(request, "waste/receipt/minutes.html", {"receipt": receipt, "form": form, "formset": formset})


@login_required
def receipt_print(request, pk):                      # filled Word form, to print and sign
    receipt = get_object_or_404(WasteReceipt.objects.select_related("origin_facility", "received_by__profile")
        .prefetch_related("nuclides", "lines"), pk=pk)
    if receipt.status == ReceiptStatus.DRAFT:
        messages.error(request, _("Complete the minutes data first."))
        return redirect("waste_receipt_minutes", pk=pk)
    fill = docx_export.fill_liquid if receipt.waste_type == WasteType.LIQUID else docx_export.fill_solid
    buf = BytesIO()
    fill(receipt_to_context(receipt), buf)
    buf.seek(0)
    return FileResponse(buf, as_attachment=True, filename=f"minutes_{receipt.letter_number}.docx".replace("/", "-"))


@login_required
def receipt_finalize(request, pk):                   # STEP 3: signed copy + create waste records
    receipt = get_object_or_404(WasteReceipt, pk=pk)
    if not _can_complete(request.user, receipt):
        raise PermissionDenied
    if receipt.status != ReceiptStatus.MINUTES_READY:
        messages.error(request, _("Only a receipt with ready minutes can be finalized."))
        return redirect("waste_receipt_detail", pk=pk)
    form = SignedMinutesForm(request.POST or None, request.FILES or None, instance=receipt)
    if request.method == "POST" and form.is_valid():
        form.save()
        try:
            finalize_receipt(receipt.pk, request.user)
        except ReceiptError as e:
            messages.error(request, str(e))
        else:
            messages.success(request, _("Finalized - waste records created."))
            return redirect("waste_receipt_detail", pk=pk)
    return render(request, "waste/receipt/finalize.html", {
        "receipt": receipt, "form": form, "batch_count": planned_batch_count(receipt)})