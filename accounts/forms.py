from django import forms
from django.utils.translation import gettext_lazy as _


class ViewPermissionImportForm(forms.Form):
    csv_file = forms.FileField(label=_("CSV File"))