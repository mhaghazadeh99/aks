from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext_lazy as _

from .forms import LicensePaymentForm
from .models import LicensePayment


from operations.models import (
    LicenseRequest,
    LicenseStatus,
)


PAYMENT_VISIBLE_STATUSES = [
    LicenseStatus.FINANCE,
    # LicenseStatus.READY_TO_ISSUE,
    # LicenseStatus.ISSUED,
    # LicenseStatus.COMPLETED,
]


def financial_home(request):
    context = {
        "license_Financial_count": (
            LicenseRequest.objects.filter(status=LicenseStatus.FINANCE).count()
        ),}
    return render(
        request,
        "financial/financial_home.html",context,
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
    license_request = get_object_or_404(LicenseRequest,pk=pk,)

    payment, created = LicensePayment.objects.get_or_create(license=license_request,)

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

            messages.success(
                request,
                _("Payment information saved successfully.")
            )

            return redirect("license_payment_list")
        else:
            messages.error(
                request,
                _("Please correct the errors below.")
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