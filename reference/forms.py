# reference/forms.py

from django import forms
from .models import Nuclides
from django import forms
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit
from django.utils.translation import gettext_lazy as _


class NuclideForm(forms.ModelForm):
    class Meta:
        model = Nuclides
        fields = "__all__"


# reference/forms.py




class CSVImportForm(forms.Form):
    file = forms.FileField(label=_("CSV file"))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_method = "post"
        self.helper.add_input(Submit("submit", _("Upload")))