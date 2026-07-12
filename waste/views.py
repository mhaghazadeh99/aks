from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.contrib import messages

from .models import (
    WasteBatch,
    WasteType,
    LiquidWasteDetails,
    WasteConditioning,
)

from .forms import (
    WasteBatchForm,
    LiquidWasteForm,
    WasteConditioningForm,
)

@login_required
def waste_create(request):

    if request.method == "POST":

        batch_form = WasteBatchForm(request.POST, request.FILES)

        liquid_form = LiquidWasteForm(request.POST)

        conditioning_form = WasteConditioningForm(request.POST)

        if (
            batch_form.is_valid()
            and conditioning_form.is_valid()
            and (
                request.POST.get("waste_type") != WasteType.LIQUID
                or liquid_form.is_valid()
            )
        ):

            batch = batch_form.save(commit=False)

            batch.created_by = request.user

            batch.save()

            conditioning = conditioning_form.save(commit=False)

            conditioning.batch = batch

            conditioning.save()

            if batch.waste_type == WasteType.LIQUID:

                liquid = liquid_form.save(commit=False)

                liquid.batch = batch

                liquid.save()

            messages.success(request, "Waste batch created.")

            return redirect("waste_detail", batch.pk)

    else:

        batch_form = WasteBatchForm()

        liquid_form = LiquidWasteForm()

        conditioning_form = WasteConditioningForm()

    return render(

        request,

        "waste/create.html",

        {

            "form": batch_form,

            "liquid_form": liquid_form,

            "conditioning_form": conditioning_form,

        },

    )
@login_required
def waste_edit(request, pk):

    batch = get_object_or_404(
        WasteBatch,
        pk=pk,
        is_active=True
    )

    liquid_instance = getattr(batch, "liquid_details", None)
    conditioning_instance = getattr(batch, "conditioning", None)

    if request.method == "POST":

        batch_form = WasteBatchForm(
            request.POST,
            request.FILES,
            instance=batch
        )

        liquid_form = LiquidWasteForm(
            request.POST,
            instance=liquid_instance
        )

        conditioning_form = WasteConditioningForm(
            request.POST,
            instance=conditioning_instance
        )

        liquid_valid = (
            batch_form.data.get("waste_type") != "LIQUID"
            or liquid_form.is_valid()
        )

        if (
            batch_form.is_valid()
            and conditioning_form.is_valid()
            and liquid_valid
        ):

            batch = batch_form.save()

            if batch.waste_type == "LIQUID":

                liquid = liquid_form.save(commit=False)
                liquid.batch = batch
                liquid.save()

            if conditioning_form.has_changed():

                conditioning = conditioning_form.save(commit=False)
                conditioning.batch = batch
                conditioning.save()

            messages.success(
                request,
                "Waste batch updated successfully."
            )

            return redirect(
                "waste_detail",
                batch.pk
            )

    else:

        batch_form = WasteBatchForm(
            instance=batch
        )

        liquid_form = LiquidWasteForm(
            instance=liquid_instance
        )

        conditioning_form = WasteConditioningForm(
            instance=conditioning_instance
        )

    return render(

        request,

        "waste/edit.html",

        {

            "form": batch_form,
            "liquid_form": liquid_form,
            "conditioning_form": conditioning_form,
            "batch": batch,

        },

    )
# ---------------------------
# Waste Detail
# ---------------------------
@login_required
def waste_detail(request, pk):

    batch = get_object_or_404(

        WasteBatch.objects.select_related(

            "created_by",
            "liquid_details",
            "conditioning",

        ),

        pk=pk,
        is_active=True,

    )

    return render(

        request,

        "waste/detail.html",

        {

            "batch": batch

        },

    )

# ---------------------------
# Waste List
# ---------------------------
@login_required
def waste_list(request):

    queryset = (
        WasteBatch.objects
        .filter(is_active=True)
        .select_related(
            "liquid_details",
            "conditioning",
            "created_by",
        )
        .order_by("-created_at")
    )

    search = request.GET.get("search")

    if search:

        queryset = queryset.filter(

            Q(waste_id__icontains=search) |
            Q(material__icontains=search) |
            Q(location__icontains=search) |
            Q(origin_facility__icontains=search) |
            Q(facility__icontains=search) |
            Q(status__icontains=search)

        )

    page_size = request.GET.get("size", "25")

    if page_size == "all":

        batches = queryset

        page_obj = None

    else:

        paginator = Paginator(queryset, int(page_size))

        page_number = request.GET.get("page")

        page_obj = paginator.get_page(page_number)

        batches = page_obj.object_list

    return render(
        request,
        "waste/list.html",
        {
            "batches": batches,
            "page_obj": page_obj,
            "page_size": page_size,
            "search": search,
        },
    )

@login_required
def waste_delete(request, pk):

    batch = get_object_or_404(
        WasteBatch,
        pk=pk
    )

    batch.is_active = False

    batch.save()

    messages.success(
        request,
        "Waste batch deleted."
    )

    return redirect(
        "waste_list"
    )