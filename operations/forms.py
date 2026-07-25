from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Field
from django import forms
from django.utils.translation import gettext_lazy as _
from django.forms import modelformset_factory
from facilities.models import Facility
from django.utils import timezone
from dashboard.choices import ActivityUnit
from dashboard.models import SOURCE_STATUS
from .models import LicenseRequest,LicenseSource,LicenseSourceType
from reference.models import Nuclides

class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):

    def clean(self, data, initial=None):

        if not data:
            return []

        if isinstance(data, (list, tuple)):
            files = data
        else:
            files = [data]

        cleaned_files = []

        for file in files:
            cleaned_files.append(
                super().clean(file, initial)
            )

        return cleaned_files

class LicenseRequestForm(forms.ModelForm):

    

    class Meta:

        model = LicenseRequest

        fields = [

            "letter_number",

            "letter_date",
            "description",

            

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

        self.helper.form_tag = False

        self.helper.layout = Layout(

            Field("letter_number"),

            Field("letter_date"),
            Field("description"),

            

        )


class LicenseFacilityForm(forms.Form):

    facility = forms.ModelChoiceField(

        queryset=Facility.objects.order_by("name"),

        label=_("Facility"),

        empty_label=_("Select Facility"),

    )

    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)

        self.helper = FormHelper()

        self.helper.form_tag = False

        self.helper.layout = Layout(

            Field("facility"),

        )



class LicenseAttachmentForm(forms.Form):

    letter = MultipleFileField(
        required=False,
        label=_("Letter"),
        widget=MultipleFileInput(),
    )

    commitment = MultipleFileField(
        required=False,
        label=_("Commitment"),
        widget=MultipleFileInput(),
    )

    permit = MultipleFileField(
        required=False,
        label=_("Permit"),
        widget=MultipleFileInput(),
    )

    inquiry = MultipleFileField(
        required=False,
        label=_("DSRS Inquiry Form"),
        widget=MultipleFileInput(),
    )

    other = MultipleFileField(
        required=False,
        label=_("Other"),
        widget=MultipleFileInput(),
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




from dashboard.models import DSRS

class LicenseSourceForm(forms.Form):

    source_type = forms.ChoiceField(
        choices=LicenseSourceType.choices,
        initial=LicenseSourceType.NEW,
        label=_("Source Type"),
    )

    source_dsrs = forms.ModelChoiceField(
                    queryset=DSRS.objects.filter(Status=SOURCE_STATUS.STORED,
                ).select_related("Nuclide",).order_by("serial_number",))

    nuclide = forms.ModelChoiceField(
        queryset=Nuclides.objects.order_by("name"),
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

            Field("source_type"),

            Field("source_dsrs"),

            Field("nuclide"),

            Field("quantity"),

        )

    def clean(self):

        cleaned = super().clean()

        source_type = cleaned.get("source_type")
        dsrs = cleaned.get("source_dsrs")
        nuclide = cleaned.get("nuclide")

        if source_type == LicenseSourceType.NEW:

            if not nuclide:

                self.add_error(
                    "nuclide",
                    _("Please select a nuclide."),
                )

        else:

            if not dsrs:

                self.add_error(
                    "source_dsrs",
                    _("Please select an existing DSRS."),
                )

        return cleaned



class LicenseSourceSpecificationForm(forms.ModelForm):

    class Meta:

        model = LicenseSource

        fields = [

            "source_type",

            "source_dsrs",

            "serial_number",

            "activity",

            "activity_unit",

            "activity_date",

            "description",

        ]

        widgets = {

            "activity_date": forms.DateInput(

                attrs={

                    "type": "text",

                    "class": "datepicker",

                }

            ),

        }

    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)

        self.helper = FormHelper()

        self.helper.form_tag = False

        self.helper.layout = Layout(

            Field("source_type"),

            Field("source_dsrs"),

            Field("serial_number"),

            Field("activity"),

            Field("activity_unit"),

            Field("activity_date"),

            Field("description"),

        )
    def clean(self):

        cleaned = super().clean()

        source_type = cleaned.get("source_type")
        source_dsrs = cleaned.get("source_dsrs")

        if source_type != LicenseSourceType.NEW and not source_dsrs:

            raise forms.ValidationError(
                _("Please select an existing source.")
            )

        return cleaned
    
   



LicenseSourceSpecificationFormSet = modelformset_factory(

        LicenseSource,

        form=LicenseSourceSpecificationForm,

        extra=0,

    )