from django.shortcuts import render,redirect
from django.contrib.auth.decorators import login_required
from .forms import ContractForm
# Create your views here.
from .models import Contract
from django.shortcuts import get_object_or_404
from django.http import HttpResponseForbidden
import json
from django.http import JsonResponse, response
import csv
from django.http import HttpResponse
from datetime import datetime
from django.core.paginator import Paginator
from dashboard.models import DSRS

from operations.models import LicenseRequest,LicenseStatus

def contract_home(request):

    licenses = LicenseRequest.objects.filter(
        status=LicenseStatus.CONTRACTS
    )

    return render(
        request,
        "contract/contract_home.html",
        {
            "licenses": licenses
        }
    )



def contract_index(request):
    contracts = Contract.objects.prefetch_related(
    "dsrs").order_by('-created_at')

# ...your filtering code...
     # ---------- FILTER SYSTEM ----------
    keys = request.GET.getlist("key")
    values = request.GET.getlist("value")

    for k, v in zip(keys, values):
        if not v:
            continue

        # -------- BOOLEAN FIELDS --------
        if k in ["payment_done", "contract_signed", "licence_valid"]:
            if v.lower() in ["true", "1", "yes"]:
                contracts = contracts.filter(**{k: True})
            elif v.lower() in ["false", "0", "no"]:
                contracts = contracts.filter(**{k: False})
            continue

        # -------- DATE FIELDS --------
        if k in ["payment_date", "contract_signed_date", "licence_issue_date", "created_at"]:
            try:
                date_value = datetime.strptime(v, "%Y-%m-%d").date()
                contracts = contracts.filter(**{k: date_value})
            except:
                # fallback: ignore bad date input instead of breaking
                continue
            continue

        # -------- TEXT / NORMAL FIELDS --------
        contracts = contracts.filter(**{f"{k}__icontains": v})

    # ---------- PAGE SIZE ----------

    size = request.GET.get("size", "25")

    if size == "all":
        page_size = contracts.count() or 1   # avoid 0 if table is empty
    else:
        page_size = int(size)

    # ---------- PAGINATION ----------
    paginator = Paginator(contracts, page_size)
    page = request.GET.get("page")
    page_obj = paginator.get_page(page)

    return render(request, 'contract/index.html', {
        'page_obj': page_obj,
        "page_size": size,
    })

@login_required
def create_contract_bulk(request):

    if request.method != "POST":
        return JsonResponse({
            "success":False,
            "message":"Invalid request"
        })


    data=json.loads(request.body)

    ids=data.get("ids",[])


    if not ids:
        return JsonResponse({
            "success":False,
            "message":"No sources selected"
        })


    sources = DSRS.objects.filter(
        id__in=ids
    )


    duplicate = sources.filter(
        contracts__isnull=False
    )


    if duplicate.exists():

        serials=list(
            duplicate.values_list(
                "serial_number",
                flat=True
            )
        )


        return JsonResponse({
            "success":False,
            "message":
            "Already contracted: "
            + ", ".join(serials)
        })


    first=sources.first()


    contract=Contract.objects.create(

        Source_Type=first.Source_Type,

        status=first.Status,

        status_date=first.Status_Date,

        facility=first.Facility,

    )


    contract.dsrs.set(
        sources
    )


    return JsonResponse({

        "success":True,

        "message":
        f"Contract created with {sources.count()} DSRS"

    })
def contract_edit(request, pk):

    if not request.user.groups.filter(name="Contracts Users").exists():
        return HttpResponseForbidden("No access")


    contract = get_object_or_404(
        Contract,
        pk=pk
    )


    if request.method == "POST":

        form = ContractForm(
            request.POST,
            instance=contract
        )

        if form.is_valid():

            form.save()

            return redirect(
                "contract_index"
            )

        else:
            print(form.errors)


    else:

        form = ContractForm(
            instance=contract
        )


    sources = contract.dsrs.all()


    return render(
        request,
        "contract/contract_edit.html",
        {
            "form":form,
            "contract":contract,
            "sources":sources,
        }
    )




def save_column(request):
    if request.method == "POST":
        data = json.loads(request.body)

        key = data["key"]
        value = data["value"]

        request.session.setdefault("columns", {})
        request.session["columns"][key] = value
        request.session.modified = True

        return JsonResponse({"ok": True})

def get_column(request):
    return JsonResponse(request.session.get("columns", {}))



import csv
from django.http import HttpResponse
from .models import Contract


def export_contracts_csv(request):
    queryset = Contract.objects.all()

    # OPTIONAL FILTERING (same system as DSRS export)
    keys = request.GET.getlist("key")
    values = request.GET.getlist("value")

    for k, v in zip(keys, values):
        queryset = queryset.filter(**{f"{k}__icontains": v})

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="contracts.csv"'

    writer = csv.writer(response)

    # -----------------------------
    # HEADER (ALL MODEL FIELDS)
    # -----------------------------
    writer.writerow([
        "ID",
        "DSRS_ID",
        "Source_Type",
        "Status",
        "Status_Date",
        "Facility",
        "Serial_Number",
        "Nuclide",
        "Activity",
        "Activity_Unit",
        "Activity_Date",
        "Contract_Signed",
        "Contract_Signed_Date",
        "Payment_Done",
        "Payment_Date",
        "Licence_Valid",
        "Licence_Issue_Date",
        "Created_At",
    ])

    # -----------------------------
    # ROWS
    # -----------------------------
    for c in queryset:
        writer.writerow([
            c.id,
            c.dsrs.id if c.dsrs else None,
            c.Source_Type,
            c.status,
            c.status_date,
            c.facility,
            c.serial_number,
            c.nuclide,
            c.activity,
            c.activity_unit,
            c.activity_date,
            c.contract_signed,
            c.contract_signed_date,
            c.payment_done,
            c.payment_date,
            c.licence_valid,
            c.licence_issue_date,
            c.created_at,
        ])

    return response
  