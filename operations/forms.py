from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Field
from django import forms
from django.utils.translation import gettext_lazy as _

from facilities.models import Facility

from .models import LicenseRequest
from reference.models import Nuclides

class LicenseRequestForm(forms.ModelForm):

    facility = forms.ModelChoiceField(

        queryset=Facility.objects.order_by("name"),

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

                    "type": "text",

                    "class": "datepicker",

                }

            ),

        }

    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)

        # Add * to required fields
        for name, field in self.fields.items():

            if field.required:

                field.label = f"{field.label} *"

        self.helper = FormHelper()

        self.helper.form_method = "post"

        self.helper.layout = Layout(

            Field("letter_number"),

            Field("letter_date"),

            Field("facility"),

        )



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

    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)

        self.helper = FormHelper()

        self.helper.form_method = "post"

        self.helper.form_tag = False

        self.helper.layout = Layout(

            Field("letter"),

            Field("commitment"),

            Field("permit"),

            Field("inquiry"),

            Field("other"),

        )





class LicenseSourceForm(forms.Form):

    nuclide = forms.ModelChoiceField(

        queryset=Nuclides.objects.order_by(
            "name"
        ),

        required=False,

        empty_label=_("Select Nuclide"),

        label=_("Nuclide"),

    )

    quantity = forms.IntegerField(

        label=_("Number of Sources"),

        initial=1,

        min_value=1,

    )

    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)

        self.helper = FormHelper()

        self.helper.form_method = "post"

        self.helper.form_tag = False

        self.helper.layout = Layout(

            Field("nuclide"),

            Field("quantity"),

        )