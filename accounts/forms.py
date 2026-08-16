from django import forms
from django.utils.translation import gettext_lazy as _

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Field

from .models import UserProfile


class UserProfileForm(forms.ModelForm):

    class Meta:
        model = UserProfile
        fields = ["full_name", "position", "signature_image"]

        labels = {
            "full_name": _("Full Name"),
            "position": _("Position"),
            "signature_image": _("Signature Image"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_tag = False

        self.helper.layout = Layout(
            Field("full_name"),
            Field("position"),
            Field("signature_image"),
        )


class ViewPermissionImportForm(forms.Form):

    csv_file = forms.FileField(label=_("CSV File"))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_tag = False

        self.helper.layout = Layout(
            Field("csv_file"),
        )