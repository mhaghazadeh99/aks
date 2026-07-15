from django.utils.translation import gettext_lazy as _

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.shortcuts import render

from .forms import FacilityForm
from .models import Facility


def facility_list(request):

    search = request.GET.get("search", "")

    page_size = int(
        request.GET.get("page_size", 10)
    )

    queryset = Facility.objects.all()

    if search:

        queryset = queryset.filter(

            Q(name__icontains=search) |

            Q(responsible_person__icontains=search) |

            Q(telephone__icontains=search)

        )

    paginator = Paginator(
        queryset,
        page_size
    )

    page = request.GET.get("page")

    facilities = paginator.get_page(page)

    context = {

        "facilities": facilities,

        "search": search,

        "page_size": page_size,

    }

    return render(
        request,
        "facilities/facility_list.html",
        context
    )


def facility_create(request):

    if request.method == "POST":

        form = FacilityForm(
            request.POST
        )

        if form.is_valid():

            form.save()

            messages.success(
                request,
                _("Facility created successfully.")
            )

            return redirect(
                "facility_list"
            )

    else:

        form = FacilityForm()

    return render(
        request,
        "facilities/facility_create.html",
        {
            "form": form
        }
    )


def facility_update(request, pk):

    facility = get_object_or_404(
        Facility,
        pk=pk
    )

    if request.method == "POST":

        form = FacilityForm(
            request.POST,
            instance=facility
        )

        if form.is_valid():

            form.save()

            messages.success(
                request,
                _("Facility updated successfully.")
            )

            return redirect(
                "facility_list"
            )

    else:

        form = FacilityForm(
            instance=facility
        )

    return render(
        request,
        "facilities/facility_update.html",
        {
            "form": form,
            "facility": facility,
        }
    )


def facility_delete(request, pk):

    facility = get_object_or_404(
        Facility,
        pk=pk
    )

    if request.method == "POST":

        facility.delete()

        messages.success(
            request,
            _("Facility deleted.")
        )

        return redirect(
            "facility_list"
        )

    return render(
        request,
        "facilities/facility_delete.html",
        {
            "facility": facility
        }
    )