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

from operations.models import LicenseRequest,LicenseStatus, LicenseApproval,LicenseAttachmentType,LicenseAttachment

from django.contrib import messages
from django.utils.translation import gettext_lazy as _


from .models import LicenseContract
from .forms import LicenseContractForm,LicenseIssueForm
from django.utils import timezone
from operations.services.fulfillment import fulfill_license_sources
from django.db.models import Q

def issued_license_list(request):

    licenses = (
        LicenseRequest.objects
        .filter(
            Q(status=LicenseStatus.ISSUED) |
            Q(status=LicenseStatus.COMPLETED)
        )
        .select_related("facility")
        .order_by("-updated_at")
    )

    return render(
        request,
        "contract/issued_license_list.html",
        {
            "licenses": licenses,
        },
    )



def issue_license(request, pk):

    license_request = get_object_or_404(
        LicenseRequest,
        pk=pk,
        status=LicenseStatus.READY_TO_ISSUE,
    )

    if request.method == "POST":

        form = LicenseIssueForm(
            request.POST,
            request.FILES,
            instance=license_request,
        )

        if form.is_valid():

            license_request = form.save(commit=False)

            license_request.status = LicenseStatus.ISSUED
            license_request.status_date = timezone.now()

            license_request.save()

            uploaded_file = form.cleaned_data.get("license_attachment")

            if uploaded_file:

                attachment = license_request.attachments.filter(
                    attachment_type=LicenseAttachmentType.LICENSE
                ).first()

                if attachment:

                    attachment.file = uploaded_file
                    attachment.uploaded_by = request.user
                    attachment.save()

                else:

                    LicenseAttachment.objects.create(
                        license=license_request,
                        attachment_type=LicenseAttachmentType.LICENSE,
                        file=uploaded_file,
                        uploaded_by=request.user,
                    )

            # fulfill sources
            fulfill_license_sources(license_request, request.user)


            messages.success(request, _("License issued successfully."))

            return redirect("ready_to_issue_list")

    else:

        form = LicenseIssueForm(instance=license_request)

    return render(
            request,
            "contract/license_issue.html",
            {
                "license_request": license_request,
                "form": form,
            },
        )


def ready_to_issue_list(request):

    licenses = LicenseRequest.objects.filter(
        status=LicenseStatus.READY_TO_ISSUE
    ).select_related(
        "facility",
        "contract",
    )

    return render(
        request,
        "contract/ready_to_issue_list.html",
        {
            "licenses": licenses,
        }
    )

def contract_home(request):

    context = {
        "license_contract_count": (
            LicenseRequest.objects.filter(status=LicenseStatus.CONTRACTS).count()
        ),
        "ready_to_issue_count": (
            LicenseRequest.objects.filter(status=LicenseStatus.READY_TO_ISSUE).count()
        ),
        "issued_count": (
            LicenseRequest.objects.filter(
                Q(status=LicenseStatus.ISSUED) | Q(status=LicenseStatus.COMPLETED)
            ).count()
        ),
    }

    return render(
        request,
        "contract/contract_home.html",
        context,
    )

def license_contract_home(request):

    licenses = LicenseRequest.objects.filter(
        status=LicenseStatus.CONTRACTS
    ).select_related(
        "facility",
        "contract",
    )


    return render(
        request,
        "contract/license_contract_home.html",
        {
            "licenses": licenses
        }
    )




def license_contract_create(request, pk):

    license_request = get_object_or_404(
        LicenseRequest,
        pk=pk,
        status=LicenseStatus.CONTRACTS,
    )


    if hasattr(license_request, "contract"):

        return redirect(
            "license_contract_update",
            pk=license_request.contract.pk
        )


    if request.method == "POST":

        form = LicenseContractForm(
                request.POST,
                request.FILES,
            )

        if form.is_valid():

            contract = form.save(
                commit=False
            )

            contract.license = license_request

            contract.save()


            if (
                contract.send_to_financial
                and license_request.status == LicenseStatus.CONTRACTS
            ):

                license_request.status = LicenseStatus.FINANCE

                license_request.save(
                    update_fields=["status"]
                )

            uploaded_file = form.cleaned_data.get("contract_attachment")

            if uploaded_file:

                attachment = license_request.attachments.filter(
                    attachment_type=LicenseAttachmentType.CONTRACT
                ).first()

                if attachment:

                    attachment.file = uploaded_file
                    attachment.uploaded_by = request.user
                    attachment.save()

                else:

                    LicenseAttachment.objects.create(

                        license=license_request,

                        attachment_type=LicenseAttachmentType.CONTRACT,

                        file=uploaded_file,

                        uploaded_by=request.user,

                    )


            messages.success(
                request,
                _("Contract created successfully.")
            )


            return redirect(
                    "license_contract_home"
                )


    else:

        form = LicenseContractForm()


    history = LicenseApproval.objects.filter(
                license=license_request
            ).order_by("step")

    return render(
                request,
                "contract/license_contract_form.html",
                {
                    "form": form,
                    "license": license_request,
                    "history": history,
                    "page_title": _("Create License Contract"),
                    "submit_text": _("Create Contract"),
                },
            )




def license_contract_update(request, pk):

    contract = get_object_or_404(
        LicenseContract,
        pk=pk
    )


    if request.method == "POST":

        form = LicenseContractForm(
            request.POST,
            request.FILES,

            instance=contract
        )

        if form.is_valid():

            contract = form.save()
            if contract.send_to_financial:

                if contract.license.status == LicenseStatus.CONTRACTS:

                    contract.license.status = LicenseStatus.FINANCE

                    contract.license.save(
                        update_fields=["status"]
                    )

            uploaded_file = form.cleaned_data.get(
                "contract_attachment"
            )

            if uploaded_file:

                attachment = contract.license.attachments.filter(
                    attachment_type=LicenseAttachmentType.CONTRACT
                ).first()


                if attachment:

                    attachment.file = uploaded_file
                    attachment.uploaded_by = request.user
                    attachment.save()


                else:

                    LicenseAttachment.objects.create(

                        license=contract.license,

                        attachment_type=LicenseAttachmentType.CONTRACT,

                        file=uploaded_file,

                        uploaded_by=request.user,

                    )


            messages.success(
                request,
                _("Contract updated.")
            )

            return redirect(
                "license_contract_home"
            )

    else:

        form = LicenseContractForm(
            instance=contract
        )

    history = LicenseApproval.objects.filter(
            license=contract.license
        ).order_by("step")

    return render(
            request,
            "contract/license_contract_form.html",
            {
                "form": form,
                "contract": contract,
                "license": contract.license,
                "history": history,
                "page_title": _("Update License Contract"),
                "submit_text": _("Save Changes"),
            },
        )





def contract_index(request):

    contracts = (
        Contract.objects
        .select_related("dsrs__Nuclide", "dsrs__Facility", "dsrs__contract")
        .order_by("-created_at")
    )

    keys = request.GET.getlist("key")
    values = request.GET.getlist("value")

    for k, v in zip(keys, values):
        if not v:
            continue

        if k == "payment_done":
            if v.lower() in ["true", "1", "yes"]:
                contracts = contracts.filter(payment_done=True)
            elif v.lower() in ["false", "0", "no"]:
                contracts = contracts.filter(payment_done=False)
            continue

        if k == "payment_date":
            try:
                date_value = datetime.strptime(v, "%Y-%m-%d").date()
                contracts = contracts.filter(payment_date=date_value)
            except ValueError:
                continue
            continue

        # Everything else searches the linked DSRS instead of a field
        # on Contract itself.
        field_map = {
            "source_type": "dsrs__Source_Type",
            "serial_number": "dsrs__serial_number",
            "nuclide": "dsrs__Nuclide__name",
            "facility": "dsrs__Facility__name",
            "status": "dsrs__Status",
            "status_date": "dsrs__Status_Date",
            "contract_number": "dsrs__contract__contract_number",
        }

        lookup = field_map.get(k)
        if lookup:
            contracts = contracts.filter(**{f"{lookup}__icontains": v})

    size = request.GET.get("size", "25")

    if size == "all":
        page_size = contracts.count() or 1
    else:
        page_size = int(size)

    paginator = Paginator(contracts, page_size)
    page = request.GET.get("page")
    page_obj = paginator.get_page(page)

    return render(request, 'contract/index.html', {
        'page_obj': page_obj,
        "page_size": size,
    })




@login_required
def create_contract_bulk(request):
    """Despite the name (kept for URL/JS compatibility), this sends each
    selected DSRS to PI individually — one Contract row per source, not
    one shared record across all of them."""

    if request.method != "POST":
        return JsonResponse({"success": False, "message": _("Invalid request")})

    data = json.loads(request.body)
    ids = data.get("ids", [])

    if not ids:
        return JsonResponse({"success": False, "message": _("No sources selected")})

    sources = DSRS.objects.filter(id__in=ids)

    duplicate = sources.filter(pi_record__isnull=False)

    if duplicate.exists():
        serials = list(duplicate.values_list("serial_number", flat=True))
        return JsonResponse({
            "success": False,
            "message": _("Already sent to PI: %(serials)s") % {
                    "serials": ", ".join(serials)
                }
        })

    count = 0
    for source in sources:
        Contract.objects.create(dsrs=source)
        count += 1

    return JsonResponse({
        "success": True,
        "message": _("%(count)s source(s) sent to PI") % {
            "count": count
        }
    })



def contract_edit(request, pk):

    if not request.user.groups.filter(name="Contracts Users").exists():
        return HttpResponseForbidden(_("You dont have access to this page."))

    contract = get_object_or_404(Contract, pk=pk)

    if request.method == "POST":

        form = ContractForm(request.POST, instance=contract)

        if form.is_valid():
            form.save()
            return redirect("contract_index")

    else:
        form = ContractForm(instance=contract)

    return render(
        request,
        "contract/contract_edit.html",
        {
            "form": form,
            "contract": contract,
            "source": contract.dsrs,   # singular now, not a queryset
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

    queryset = Contract.objects.select_related("dsrs__Nuclide", "dsrs__Facility", "dsrs__contract")

    keys = request.GET.getlist("key")
    values = request.GET.getlist("value")
    for k, v in zip(keys, values):
        queryset = queryset.filter(**{f"{k}__icontains": v})

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="pi_records.csv"'
    response.write('\ufeff')

    writer = csv.writer(response)

    writer.writerow([
            _("ID"),
            _("Serial Number"),
            _("Nuclide"),
            _("Source Type"),
            _("Facility"),
            _("Status"),
            _("Status Date"),
            _("Contract Number"),
            _("Contract Date"),
            _("Payment Done"),
            _("Payment Date"),
            _("Created At"),
        ])

    for c in queryset:
        writer.writerow([
            c.id,
            c.dsrs.serial_number,
            str(c.dsrs.Nuclide) if c.dsrs.Nuclide else None,
            c.source_type,
            c.facility,
            c.status,
            c.status_date,
            c.contract_number,
            c.contract_date,
            c.payment_done,
            c.payment_date,
            c.created_at,
        ])

    return response