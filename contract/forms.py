from django import forms
from .models import Contract
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit
from django import forms
from django.utils.translation import gettext_lazy as _

from .models import LicenseContract


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
        ]



              
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




class ContractForm(forms.ModelForm):
    
    class Meta:
        model = Contract
        
        exclude = [
            'created_at',
            'history',
            'dsrs',
            'status',
            'status_date',
            'facility',
            'serial_number',
            'nuclide',
            'activity',
            'activity_unit',
            'activity_date',
        ]

        widgets = {
            'payment_date': forms.DateInput(
                attrs={'type':'date'}
            ),
            'contract_signed_date': forms.DateInput(
                attrs={'type':'date'}
            ),
            'licence_issue_date': forms.DateInput(
                attrs={'type':'date'}
            ),
        }


    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)

        for field in self.fields.values():
            field.widget.attrs.update({
                "class":"form-control"
            })