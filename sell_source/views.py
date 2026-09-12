
# Create your views here.
from django.contrib import messages
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from dashboard.models import DSRS

from .forms import SellRequestForm, SellSourceForm
from .models import SellRequest, SellRequestSource, SellRequestStatus


# =====================================================================
# HOME / LIST / QUEUE
# =====================================================================

def sell_home(request):
    context = {
        "specification_count": SellRequest.objects.filter(status=SellRequestStatus.SPECIFICATION).count(),
        "ceo_count": SellRequest.objects.filter(status=SellRequestStatus.WAITING_CEO).count(),
        "approved_count": SellRequest.objects.filter(status=SellRequestStatus.APPROVED).count(),
    }
    return render(request, "sell_source/sell_home.html", context)


def sell_list(request):

    search = request.GET.get("search", "")
    page_size = request.GET.get("page_size", "10")

    queryset = (
        SellRequest.objects
        .select_related("created_by", "ceo_approved_by")
        .prefetch_related("sources__nuclide")
        .order_by("-created_at")
    )

    if search:
        queryset = queryset.filter(sources__serial_number__icontains=search).distinct()

    paginator = Paginator(queryset, int(page_size))
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "sell_source/sell_list.html",
        {"page_obj": page_obj, "search": search, "page_size": int(page_size)},
    )


def sell_ceo_queue(request):

    queryset = (
        SellRequest.objects
        .filter(status=SellRequestStatus.WAITING_CEO)
        .select_related("created_by")
        .prefetch_related("sources__nuclide")
        .order_by("-created_at")
    )

    paginator = Paginator(queryset, 15)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(request, "sell_source/sell_ceo_queue.html", {"page_obj": page_obj})


# =====================================================================
# STEP 1 — UPLOAD THE SCANNED REQUEST FORM
# =====================================================================

def sell_create(request):

    if request.method == "POST":

        form = SellRequestForm(request.POST, request.FILES)

        if form.is_valid():

            sell_request = form.save(commit=False)
            sell_request.created_by = request.user
            sell_request.status = SellRequestStatus.SPECIFICATION
            sell_request.status_date = timezone.now()
            sell_request.save()

            messages.success(request, _("Request form uploaded — now add the sources."))
            return redirect("sell_add_sources", pk=sell_request.pk)

    else:
        form = SellRequestForm()

    return render(request, "sell_source/sell_create.html", {"form": form})


# =====================================================================
# STEP 2 — ADD SOURCES FROM INVENTORY
# =====================================================================

def sell_add_sources(request, pk):

    sell_request = get_object_or_404(SellRequest, pk=pk, status=SellRequestStatus.SPECIFICATION)

    sources = sell_request.sources.select_related("nuclide", "dsrs").order_by("id")

    if request.method == "POST":

        source_form = SellSourceForm(request.POST)

        if source_form.is_valid():

            dsrs = source_form.cleaned_data["dsrs"]

            SellRequestSource.objects.create(
                sell_request=sell_request,
                dsrs=dsrs,
                nuclide=dsrs.Nuclide,
                serial_number=dsrs.serial_number,
                manufacture_date=dsrs.Activity_reference_date,
                recorded_activity_mci=dsrs.current_activity_mci(),
                physical_characteristics=source_form.cleaned_data.get("physical_characteristics", ""),
                remarks=source_form.cleaned_data.get("remarks", ""),
            )

            messages.success(request, _("Source added."))
            return redirect("sell_add_sources", pk=pk)

    else:
        source_form = SellSourceForm()

    return render(
        request,
        "sell_source/sell_add_sources.html",
        {"sell_request": sell_request, "sources": sources, "source_form": source_form},
    )


def sell_remove_source(request, pk, source_pk):

    sell_request = get_object_or_404(SellRequest, pk=pk, status=SellRequestStatus.SPECIFICATION)

    if request.method == "POST":
        get_object_or_404(SellRequestSource, pk=source_pk, sell_request=sell_request).delete()
        messages.success(request, _("Source removed."))

    return redirect("sell_add_sources", pk=pk)


def sell_finish_sources(request, pk):

    sell_request = get_object_or_404(SellRequest, pk=pk, status=SellRequestStatus.SPECIFICATION)

    if not sell_request.sources.exists():
        messages.error(request, _("Add at least one source before continuing."))
        return redirect("sell_add_sources", pk=pk)

    sell_request.status = SellRequestStatus.WAITING_CEO
    sell_request.status_date = timezone.now()
    sell_request.save(update_fields=["status", "status_date"])

    messages.success(request, _("Sent to the CEO for signature."))
    return redirect("sell_detail", pk=pk)


# =====================================================================
# STEP 3 — CEO SIGNATURE (a plain approval record — nothing is stamped
# onto the scanned jpeg; the final page shows the approver's name,
# signature image, and timestamp alongside the original scan instead)
# =====================================================================

def sell_sign(request, pk):

    sell_request = get_object_or_404(SellRequest, pk=pk, status=SellRequestStatus.WAITING_CEO)

    if request.method == "POST":

        sell_request.ceo_approved_by = request.user
        sell_request.ceo_approved_at = timezone.now()
        sell_request.status = SellRequestStatus.APPROVED
        sell_request.status_date = timezone.now()
        sell_request.save(update_fields=["ceo_approved_by", "ceo_approved_at", "status", "status_date"])

        messages.success(request, _("Approved and signed."))
        return redirect("sell_detail", pk=pk)

    return render(request, "sell_source/sell_sign.html", {"sell_request": sell_request})


# =====================================================================
# FINAL VIEW — scanned form + source table + signature block + Send to PI
# =====================================================================

def sell_detail(request, pk):

    sell_request = get_object_or_404(
        SellRequest.objects.select_related("created_by", "ceo_approved_by"),
        pk=pk,
    )

    sources = sell_request.sources.select_related("nuclide", "dsrs").order_by("id")

    # Whether every DSRS here has already been sent to PI — purely to
    # decide whether to still show the button; the existing
    # create_contract_bulk endpoint already guards against double-sending
    # on its own, this is just for a cleaner UI.
    dsrs_ids = list(sources.values_list("dsrs_id", flat=True))
    already_sent = DSRS.objects.filter(pk__in=dsrs_ids, pi_record__isnull=False).exists() if dsrs_ids else False

    return render(
        request,
        "sell_source/sell_detail.html",
        {
            "sell_request": sell_request,
            "sources": sources,
            "dsrs_ids": dsrs_ids,
            "already_sent": already_sent,
        },
    )