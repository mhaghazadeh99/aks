from crispy_forms.helper import FormHelper

from crispy_forms.layout import Layout, Field, Row, Column

from django import forms
from django.utils.translation import gettext_lazy as _
from django.forms import modelformset_factory
from facilities.models import FacilityModel
from django.utils import timezone
from dashboard.choices import ActivityUnit
from dashboard.models import SOURCE_STATUS
from .models import LicenseRequest,LicenseSource,LicenseSourceType
from reference.models import Nuclides

from dashboard.models import DSRS

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
                    "class": "form-control datepicker",
                    "autocomplete": "off",
                    "placeholder": _("Select letter date"),
                }
            ),

            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Add * to required fields
        for name, field in self.fields.items():
            if field.required:
                field.label = f"{field.label} *"

        # Standardize Bootstrap form-control
        for field in self.fields.values():
            existing = field.widget.attrs.get("class", "")
            if "form-control" not in existing:
                field.widget.attrs["class"] = (
                    f"{existing} form-control"
                ).strip()

        self.helper = FormHelper()
        self.helper.form_tag = False

        self.helper.layout = Layout(
            Row(
                Column(
                    Field("letter_number"),
                    css_class="col-md-2",
                ),
                Column(
                    Field("letter_date"),
                    css_class="col-md-2",
                ),
                css_class="g-3",
            ),

            Row(
                Column(
                    Field("description"),
                    css_class="col-md-6",
                ),
                css_class="g-3",
            ),
        )



class LicenseFacilityForm(forms.Form):

    facility = forms.ModelChoiceField(
        queryset=FacilityModel.objects.order_by("name"),
        label=_("Facility"),
        empty_label=_("Select Facility"),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["facility"].widget.attrs["class"] = "form-select"

        self.helper = FormHelper()
        self.helper.form_tag = False

        self.helper.layout = Layout(
            Row(
                Column(
                    Field("facility"),
                    css_class="col-md-6",
                ),
                css_class="g-3",
            ),
        )





class LicenseAttachmentForm(forms.Form):

    letter = MultipleFileField(
        required=False,
        label=_("Letter"),
        widget=MultipleFileInput(
            attrs={
                "class": "form-control",
            }
        ),
    )

    commitment = MultipleFileField(
        required=False,
        label=_("Commitment"),
        widget=MultipleFileInput(
            attrs={
                "class": "form-control",
            }
        ),
    )

    permit = MultipleFileField(
        required=False,
        label=_("Permit"),
        widget=MultipleFileInput(
            attrs={
                "class": "form-control",
            }
        ),
    )

    inquiry = MultipleFileField(
        required=False,
        label=_("DSRS Inquiry Form"),
        widget=MultipleFileInput(
            attrs={
                "class": "form-control",
            }
        ),
    )

    other = MultipleFileField(
        required=False,
        label=_("Other"),
        widget=MultipleFileInput(
            attrs={
                "class": "form-control",
            }
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_method = "post"
        self.helper.form_tag = False

        self.helper.layout = Layout(
            Row(
                Column(
                    Field("letter"),
                    css_class="col-md-6",
                ),
                Column(
                    Field("commitment"),
                    css_class="col-md-6",
                ),
                css_class="g-3",
            ),

            Row(
                Column(
                    Field("permit"),
                    css_class="col-md-6",
                ),
                Column(
                    Field("inquiry"),
                    css_class="col-md-6",
                ),
                css_class="g-3",
            ),

            Row(
                Column(
                    Field("other"),
                    css_class="col-md-6",
                ),
                css_class="g-3",
            ),
        )




class DSRSSelect(forms.Select):
    """
    Adds data-count / data-available attributes to each <option>, so the
    template's JS can filter/validate DSRS picks client-side (Reuse only
    allows source_count == 1; Recycled quantity can't exceed available_count)
    without a round-trip to the server. Built from a pre-fetched dict rather
    than querying per-option to avoid N+1 queries.
    """

    def __init__(self, *args, dsrs_meta=None, **kwargs):
        self.dsrs_meta = dsrs_meta or {}
        super().__init__(*args, **kwargs)

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        meta = self.dsrs_meta.get(str(value))
        if meta:
            option["attrs"]["data-count"] = meta[0]
            option["attrs"]["data-available"] = meta[1]
        return option


class LicenseSourceForm(forms.Form):
    """
    The "add source" picker used above the sources table on the create page.
    One shared set of fields is reused across all three source_type flows —
    which fields are visible/required is controlled entirely by JS in the
    template based on the selected source_type:

      NEW      -> nuclide + quantity          (unchanged from before)
      REUSED   -> source_dsrs only, quantity always 1, DSRS must have
                  source_count == 1 (enforced both here and via JS filtering
                  the dropdown options)
      RECYCLED -> source_dsrs + quantity used to stage multiple components
                  client-side (see template JS); nuclide + activity for the
                  combined result are entered once, at "finalize" time
    """

    source_type = forms.ChoiceField(
        choices=LicenseSourceType.choices,
        initial=LicenseSourceType.NEW,
        label=_("Source Type"),
    )

    nuclide = forms.ModelChoiceField(
        queryset=Nuclides.objects.order_by("name"),
        required=False,
        empty_label=_("Select Nuclide"),
        label=_("Nuclide"),
    )

    source_dsrs = forms.ModelChoiceField(
        queryset=DSRS.objects.none(),  # set in __init__ once we can build dsrs_meta from it
        required=False,
        empty_label=_("Select DSRS"),
        label=_("DSRS Source"),
    )

    quantity = forms.IntegerField(
        label=_("Quantity"),
        initial=1,
        min_value=1,
        required=False,
    )

    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)

        controlled_dsrs = list(
            DSRS.objects.filter(
                Status=SOURCE_STATUS.CONTROL,
            ).select_related("Nuclide").order_by("serial_number")
        )

        dsrs_meta = {
            str(d.pk): (d.source_count, d.available_count)
            for d in controlled_dsrs
        }

        self.fields["source_dsrs"].widget = DSRSSelect(dsrs_meta=dsrs_meta)
        self.fields["source_dsrs"].queryset = DSRS.objects.filter(
            pk__in=[d.pk for d in controlled_dsrs]
        )

        self.helper = FormHelper()
        self.helper.form_method = "post"
        self.helper.form_tag = False

        self.helper.layout = Layout(
            Field("source_type"),
            Field("nuclide"),
            Field("source_dsrs"),
            Field("quantity"),
        )

    def clean(self):

        cleaned = super().clean()

        source_type = cleaned.get("source_type")

        if source_type == LicenseSourceType.NEW:

            cleaned["source_dsrs"] = None

            if not cleaned.get("nuclide"):
                self.add_error("nuclide", _("Please select a nuclide."))

            if not cleaned.get("quantity"):
                self.add_error("quantity", _("Please enter a quantity."))

        elif source_type == LicenseSourceType.REUSED:

            cleaned["nuclide"] = None
            dsrs = cleaned.get("source_dsrs")

            if not dsrs:
                self.add_error("source_dsrs", _("Please select an existing DSRS."))
            elif dsrs.source_count != 1:
                self.add_error(
                    "source_dsrs",
                    _("Only single-count DSRS sources can be reused."),
                )

        elif source_type == LicenseSourceType.RECYCLED:

            dsrs = cleaned.get("source_dsrs")
            qty = cleaned.get("quantity")

            if not dsrs:
                self.add_error("source_dsrs", _("Please select a DSRS component."))

            if not qty:
                self.add_error("quantity", _("Please enter a quantity."))
            elif dsrs and qty > dsrs.available_count:
                self.add_error(
                    "quantity",
                    _("Quantity exceeds this DSRS's available count."),
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
                        "class": "form-control datepicker",
                        "placeholder": _("Select activity date"),
                    }
                ),
            }

        

    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.fields["source_dsrs"].required = False

        has_instance = self.instance and self.instance.pk
        source_type = self.instance.source_type if has_instance else None

        # source_type is fixed at creation (Step 3) — never editable here.
        self.fields["source_type"].disabled = True

        if source_type == LicenseSourceType.REUSED:

            # Everything comes from the linked DSRS — user shouldn't retype it.
            self.fields["source_dsrs"].disabled = True
            self.fields["serial_number"].disabled = True
            self.fields["activity"].disabled = True
            self.fields["activity_unit"].disabled = True
            self.fields["activity_date"].disabled = True

            # Pre-fill DISPLAY values from the live DSRS record, so the user sees
            # the real numbers on this page even before the object is re-saved
            # with them (the view is what actually copies these over on submit —
            # this is purely so the greyed-out boxes aren't blank on screen).
            if self.instance.source_dsrs_id:
                dsrs_obj = self.instance.source_dsrs
                self.initial["serial_number"] = self.instance.serial_number or dsrs_obj.serial_number
                self.initial["activity"] = (
                    self.instance.activity
                    if self.instance.activity is not None
                    else dsrs_obj.activity_input
                )
                self.initial["activity_unit"] = self.instance.activity_unit or dsrs_obj.activity_unit
                self.initial["activity_date"] = self.instance.activity_date or dsrs_obj.Activity_reference_date

        elif source_type == LicenseSourceType.RECYCLED:

            # No single DSRS to pick — this row is built from components
            # (LicenseSourceComponent), shown read-only in the template.
            self.fields["source_dsrs"].disabled = True

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

        if source_type == LicenseSourceType.REUSED and not source_dsrs:
            raise forms.ValidationError(_("Please select an existing source."))

        return cleaned
    
   


LicenseSourceSpecificationFormSet = modelformset_factory(
    LicenseSource,
    form=LicenseSourceSpecificationForm,
    extra=0,
    can_delete=True,
)