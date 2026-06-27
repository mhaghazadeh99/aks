from django import forms
from .models import Operation, OperationInput, OperationOutput


class OperationForm(forms.ModelForm):

    class Meta:
        model = Operation
        fields = [
            'operation_number',
            'operation_type',
            'operation_date',
            'remarks'
        ]


class OperationInputForm(forms.ModelForm):

    class Meta:
        model = OperationInput
        fields = [
            'batch',
            'mass_used_kg',
            'volume_used_m3'
        ]


class OperationOutputForm(forms.ModelForm):

    class Meta:
        model = OperationOutput
        fields = [
            'batch'
        ]