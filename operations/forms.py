from django import forms
from django.utils.translation import gettext_lazy as _

from facilities.models import Facility

from reference.models import Nuclides
from .models import LicenseRequest


class LicenseRequestForm(forms.ModelForm):

    facility = forms.ModelChoiceField(

        queryset=Facility.objects.order_by(
            "name"
        ),

        label=_("Facility"),

        empty_label=_("Select Facility"),
    )

    class Meta:

        model = LicenseRequest

        fields = [

            "letter_number",

            "letter_date",

            "facility",

        ]

        widgets = {

            "letter_date": forms.DateInput(

                attrs={

                    "type": "date",

                }

            ),

        }




class LicenseAttachmentForm(forms.Form):

    letter = forms.FileField(

        required=False,

        label=_("Letter"),
    )

    commitment = forms.FileField(

        required=False,

        label=_("Commitment"),
    )

    permit = forms.FileField(

        required=False,

        label=_("Permit"),
    )

    inquiry = forms.FileField(

        required=False,

        label=_("DSRS Inquiry Form"),
    )

    other = forms.FileField(

        required=False,

        label=_("Other"),
    )






class LicenseNuclideForm(forms.Form):

    nuclide = forms.ModelChoiceField(

        queryset=Nuclides.objects.order_by(
            "name"
        ),

        required=False,

        empty_label=_(
            "Select Nuclide"
        ),

        label=_(
            "Nuclide"
        ),
    )