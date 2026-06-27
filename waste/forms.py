from django import forms
from .models import WasteBatch, LiquidWasteDetails, WasteConditioning


class WasteBatchForm(forms.ModelForm):

    class Meta:
        model = WasteBatch
        fields = '__all__'
        exclude = ['created_by', 'created_at', 'updated_at', 'is_active']


class LiquidWasteForm(forms.ModelForm):

    class Meta:
        model = LiquidWasteDetails
        fields = '__all__'


class WasteConditioningForm(forms.ModelForm):

    class Meta:
        model = WasteConditioning
        fields = '__all__'