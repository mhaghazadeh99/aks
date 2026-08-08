from django.shortcuts import render

# Create your views here.
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from dashboard.models import DSRS


def receive_source_list(request):

    search = request.GET.get("search", "").strip()

    try:
        page_size = int(request.GET.get("page_size", 10))
    except (TypeError, ValueError):
        page_size = 10

    if page_size not in [10, 25, 50]:
        page_size = 10

    sources = (
        DSRS.objects
        .select_related(
            "Facility",
            "Nuclide",
            "created_by",
        )
        .prefetch_related("movements")
        .order_by("-id")
    )

    if search:
        sources = sources.filter(
            Q(serial_number__icontains=search)
            | Q(Sso_Code__icontains=search)
            | Q(Responsible_Person__icontains=search)
            | Q(Location__icontains=search)
            | Q(Nuclide__name__icontains=search)
            | Q(Facility__name__icontains=search)
        )

    paginator = Paginator(sources, page_size)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "receive_source/receive_list.html",
        {
            "page_obj": page_obj,
            "search": search,
            "page_size": page_size,
        },
    )


def receive_source_create(request):
    # We will build this next.
    return render(
        request,
        "receive_source/create.html",
    )


def receive_source_detail(request, pk):
    source = get_object_or_404(
        DSRS.objects.select_related(
            "Facility",
            "Nuclide",
            "created_by",
        ),
        pk=pk,
    )

    return render(
        request,
        "receive_source/detail.html",
        {
            "source": source,
        },
    )