from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit
from django import forms
from .models import Contract

from crispy_forms.layout import Layout, Row, Column, Field


class ContractForm(forms.ModelForm):

    class Meta:
        model = Contract
        exclude = ['created_by','created_at','status', 'status_date','facility','serial_number',
                   'nuclide','activity','activity_unit','activity_date']
        widgets = {
            'payment_date': forms.DateInput(attrs={'type': 'date'}),
            'contract_signed_date': forms.DateInput(attrs={'type': 'date'}),
            'licence_issue_date': forms.DateInput(attrs={'type': 'date'}),
        }
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['dsrs'].disabled = True
        self.fields['Source_Type'].disabled = True
        for field in self.fields.values():
            field.widget.attrs.update({'class': 'form-control'})
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.add_input(Submit('submit', 'Save Contract'))

        self.helper.layout = Layout(
            'source_type',

            Row(
                Column(Field('contract_signed'), css_class='col-md-3'),
                Column(Field('contract_signed_date'), css_class='col-md-9'),
            ),

            Row(
                Column(Field('payment_done'), css_class='col-md-3'),
                Column(Field('payment_date'), css_class='col-md-9'),
            ),

            Row(
                Column(Field('licence_valid'), css_class='col-md-3'),
                Column(Field('licence_issue_date'), css_class='col-md-9'),
            ),
        )
                