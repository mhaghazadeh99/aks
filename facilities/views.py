from django.utils.translation import gettext_lazy as _

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.shortcuts import render, redirect

from .forms import FacilityForm, FacilityImportForm
from .models import FacilityModel
import csv


def facility_list(request):

    search = request.GET.get("search", "")


    try:
        page_size = int(
            request.GET.get(
                "page_size",
                10
            )
        )

    except ValueError:
        page_size = 10



    queryset = FacilityModel.objects.all()



    # =========================
    # Global Search
    # =========================

    if search:

        queryset = queryset.filter(

            Q(name__icontains=search) |

            Q(responsible_person__icontains=search) |

            Q(telephone__icontains=search) |

            Q(email__icontains=search) |

            Q(address1__icontains=search) |

            Q(address2__icontains=search) |

            Q(postal_code__icontains=search) |

            Q(national_id__icontains=search) |

            Q(economic_code__icontains=search)

        )



    # =========================
    # Advanced Filters
    # =========================

    filter_fields = [

        "name",
        "responsible_person",
        "telephone",
        "email",
        "postal_code",
        "national_id",
        "economic_code",

    ]





    

    queryset = queryset.order_by(
        "name"
    )



    paginator = Paginator(
        queryset,
        page_size
    )


    facilities = paginator.get_page(
        request.GET.get("page")
    )



    params = request.GET.copy()

    params.pop(
        "page",
        None
    )


    context = {


        "facilities": facilities,

        "search": search,

        "page_size": page_size,


        "query_string":
            params.urlencode(),


        

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
        FacilityModel,
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

            next_url = request.GET.get("next")


            if next_url:
                return redirect(next_url)


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
        FacilityModel,
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








def facility_import(request):

    if request.method == "POST":

        form = FacilityImportForm(request.POST, request.FILES)

        if form.is_valid():

            csv_file = form.cleaned_data["csv_file"]
            decoded_file = csv_file.read().decode("utf-8-sig").splitlines()
            reader = csv.DictReader(decoded_file)

            count = 0
            skipped = []

            for row in reader:

                if None in row.values():
                    messages.error(
                        request,
                        _("Invalid CSV format near row: %(row)s") % {"row": row}
                    )
                    continue

                name = (row.get("name") or "").strip()

                if not name:
                    skipped.append(_("Row with blank name — skipped"))
                    continue

                if FacilityModel.objects.filter(name__iexact=name).exists():
                    skipped.append(name)
                    continue

                FacilityModel.objects.create(
                    name=name,
                    responsible_person=row.get("responsible_person"),
                    telephone=row.get("telephone"),
                    email=row.get("email"),
                    address1=row.get("address1"),
                    address2=row.get("address2"),
                    postal_code=row.get("postal_code") or None,
                    national_id=row.get("national_id") or None,
                    economic_code=row.get("economic_code") or None,
                )

                count += 1

            messages.success(
                request,
                _("%(count)s facilities imported successfully.") % {"count": count}
            )

            if skipped:
                messages.warning(
                    request,
                    _("Skipped %(n)s duplicate/invalid name(s): %(names)s") % {
                        "n": len(skipped),
                        "names": ", ".join(skipped[:15]) + ("..." if len(skipped) > 15 else ""),
                    }
                )

            return redirect("facility_list")

    else:
        form = FacilityImportForm()

    return render(request, "facilities/facility_import.html", {"form": form})
