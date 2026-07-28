from django.shortcuts import render

from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.shortcuts import render


from .forms import LicensePaymentForm
from .models import LicensePayment
from django.db.models import Q

from operations.models import (
    LicenseRequest,
    LicenseStatus,
)


PAYMENT_VISIBLE_STATUSES = [
    LicenseStatus.FINANCE,
    LicenseStatus.READY_TO_ISSUE,
    LicenseStatus.ISSUED,
    LicenseStatus.COMPLETED,
]


def financial_home(request):
    return render(
        request,
        "financial/financial_home.html",
    )





def license_payment_list(request):

    licenses = (
        LicenseRequest.objects
        .select_related(
            "facility",
            
        )
        .filter(
            status__in=PAYMENT_VISIBLE_STATUSES
        )
        .order_by("-id")
    )

    rows = []

    for license_request in licenses:

        payment = LicensePayment.objects.filter(
            license=license_request
        ).first()

        rows.append(
            {
                "license": license_request,
                "payment": payment,
            }
        )

    return render(
        request,
        "financial/license_payment_list.html",
        {
            "rows": rows,
        },
    )




def license_payment_update(request, pk):

    print("=== PAYMENT UPDATE VIEW CALLED ===")
    print(request.method)
    license_request = get_object_or_404(
        LicenseRequest,
        pk=pk,
    )

    payment, created = LicensePayment.objects.get_or_create(
        license=license_request,
    )

    if request.method == "POST":

        form = LicensePaymentForm(
            request.POST,
            instance=payment,
        )

        if form.is_valid():
            

            payment = form.save()

            if (
                payment.payment_done
                and license_request.status == LicenseStatus.FINANCE
            ):
                license_request.status = LicenseStatus.READY_TO_ISSUE
                license_request.save(
                    update_fields=["status"]
                )

            return redirect(
                "license_payment_list"
            )
            

    else:

        form = LicensePaymentForm(
            instance=payment,
        )

    return render(
        request,
        "financial/license_payment_form.html",
        {
            "form": form,
            "license_request": license_request,
        },)