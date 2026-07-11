from django import forms
from .models import Contract
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit

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