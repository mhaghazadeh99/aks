from django import forms
from .models import Contract
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit
from django import forms
from django.utils.translation import gettext_lazy as _

from .models import LicenseContract


from operations.models import LicenseRequest



class LicenseContractForm(forms.ModelForm):
    contract_attachment = forms.FileField(
                required=False,
                label="Contract Document",
            )
    class Meta:

        model = LicenseContract

        fields = [
            "contract_number",
            "contract_date",
            "contract_cost",
            "draft_sent_to_customer",
            "draft_sent_date",
            "notification_letter_number",
            "notification_letter_date",
            "source_owner",
            "contract_accountable",
            "amendment_notes",
            "send_to_financial",
        ]


        labels = {
            "send_to_financial": _("Send to Financial"),
        }
              
        widgets = {

                "contract_date": forms.DateInput(
                    attrs={
                        "type": "text",
                        "class": "datepicker",
                        "autocomplete": "off",

                    }
                ),

                "draft_sent_date": forms.DateInput(
                    attrs={
                        "type": "text",

                        "class": "datepicker",
                        "autocomplete": "off",
                    }
                ),

                "notification_letter_date": forms.DateInput(
                    attrs={
                        "type": "text",

                        "class": "datepicker",
                    }
                ),

                "amendment_notes": forms.Textarea(
                    attrs={
                        "rows":4
                    }
                ),

            }
            
    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)

        self.helper = FormHelper()

        self.helper.form_tag = False




class LicenseIssueForm(forms.ModelForm):

    license_attachment = forms.FileField(
        required=False,
        label=_("License Letter"),
    )

    class Meta:

        model = LicenseRequest

        fields = [
            "letter_number",
            "letter_date",
        ]

        widgets = {
            "letter_date": forms.DateInput(
                attrs={
                    "type": "text",
                    "class": "datepicker",
                    "autocomplete": "off",
                }
            ),
        }

    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_tag = False




class ContractForm(forms.ModelForm):

    class Meta:
        model = Contract
        fields = ["payment_done", "payment_date"]

        widgets = {
            "payment_date": forms.DateInput(
                attrs={"type": "text", "class": "datepicker"}
            ),
        }

        labels = {
            "payment_done": _("Payment Done"),
            "payment_date": _("Payment Date"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            existing = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"{existing} form-control".strip()