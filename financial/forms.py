from django import forms
from django.utils.translation import gettext_lazy as _

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Field

from .models import LicensePayment

class LicensePaymentForm(forms.ModelForm):

    class Meta:

        model = LicensePayment

        fields = [
            "payment_done",
            "payment_date",
            "amount_paid",
            "notes",
        ]


        widgets = {
                "payment_date": forms.DateInput(
                    attrs={
                        "type": "text",
                        "class": "datepicker",
                        "autocomplete": "off",
                        "placeholder": _("Select payment date"),
                    }
                ),
                "amount_paid": forms.NumberInput(
                    attrs={
                        "placeholder": _("Enter amount paid"),
                    }
                ),
                "notes": forms.Textarea(
                    attrs={
                        "rows": 4,
                        "placeholder": _("Additional notes"),
                    }
                ),
            }


    def __init__(self,*args,**kwargs):

        super().__init__(*args,**kwargs)


        self.helper = FormHelper()

        self.helper.form_tag = False

        self.helper.layout = Layout(

            Field("payment_done"),

            Field("payment_date"),

            Field("amount_paid"),

            Field("notes"),

        )


        for field in self.fields.values():
            existing = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"{existing} form-control".strip()

        self.fields["payment_done"].widget.attrs["class"] = "form-check-input"


      