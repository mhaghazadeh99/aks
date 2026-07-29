from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Field, Submit, Div
from django import forms
from django.utils.translation import gettext_lazy as _
from contract.models import LicenseContract
from .models import DSRS, SourceMovement, MovementType, SOURCE_TYPE

class DSRSForm(forms.ModelForm):

    class Meta:
        model = DSRS

        exclude = [
            "created_by",
            "created_at",
            "initial_activity_bq",
            "Facility",
            "Status",
            "Status_Date",
            # source_count / available_count / is_divisible stay INCLUDED, per your note
        ]

        widgets = {
            "Date_received": forms.DateInput(attrs={"type": "text", "class": "datepicker"}),
            "Activity_reference_date": forms.DateInput(attrs={"type": "text", "class": "datepicker"}),
            "Status_Date": forms.DateInput(attrs={"type": "text", "class": "datepicker"}),
            "Dose_rate_measurement_date": forms.DateInput(attrs={"type": "text", "class": "datepicker"}),
            "Comment": forms.Textarea(attrs={"rows": 3}),
        }

        labels = {
            "activity_input": _("Activity"),
            "Dose_rate_surface_uSv": _("Surface Dose Rate (µSv/h)"),
            "Dose_rate_1m_uSv": _("1m Dose Rate (µSv/h)"),
            "contamination_bq_cm2": _("Contamination (Bq/cm²)"),
            "source_count": _("Source Count"),
            "available_count": _("Available Count"),
            "is_divisible": _("Divisible"),
        }

    def __init__(self, *args, **kwargs):

        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        if srs != dsrs:
            self.fields["Source_Type"].widget = forms.HiddenInput()

            if srs:
                self.initial["Source_Type"] = SOURCE_TYPE.NEW
            else:
                self.initial["Source_Type"] = SOURCE_TYPE.DSRS

        for name, field in self.fields.items():
            if field.required:
                field.label = f"{field.label} *"

        self.helper = FormHelper()
        self.helper.form_tag = False

        self.helper.layout = Layout(
            Div(
                Field("Source_Type"),
                Field("Sso_Code"),
                Field("serial_number"),
                Field("Nuclide"),
                css_class="row"
            ),
            Div(
                Field("Origin_Type"),
                css_class="row"
            ),
            Div(
                Field("Date_received"),
                Field("Responsible_Person"),
                Field("Location"),
                css_class="row"
            ),
            Div(
                Field("activity_input"),
                Field("activity_unit"),
                Field("Activity_reference_date"),
                css_class="row"
            ),
            Div(
                Field("source_state"),
                css_class="row",
            ),
            Div(
                Field("Dose_rate_surface_uSv"),
                Field("Dose_rate_1m_uSv"),
                Field("Dose_rate_measurement_date"),
                css_class="row"
            ),
            Field("contamination_bq_cm2"),
            Div(
                Field("Source_Physical_Form"),
                Field("Source_Manufacturer"),
                Field("Source_Model"),
                css_class="row"
            ),
            Field("Source_Practice"),
            Div(
                Field("Device_Manufacturer"),
                Field("Device_Model"),
                Field("Device_Serial_Number"),
                css_class="row"
            ),
            Div(
                Field("Container_Type"),
                Field("Dimension"),
                css_class="row"
            ),
            Div(
                Field("is_divisible"),
                Field("source_count"),
                Field("available_count"),
                css_class="row"
            ),
            Field("Comment"),
        )

        if user:
            srs = user.groups.filter(name="SRS Users").exists()
            dsrs = user.groups.filter(name="DSRS Users").exists()

            if srs != dsrs:
                self.fields["Source_Type"].widget = forms.HiddenInput()
                self.initial["Source_Type"] = "SRS" if srs else "DSRS"

    def clean_activity_input(self):
        value = self.cleaned_data.get("activity_input")
        if value is not None and value <= 0:
            raise forms.ValidationError(_("Activity must be positive."))
        return value

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("activity_input") and not cleaned.get("Nuclide"):
            raise forms.ValidationError(_("Nuclide is required when activity is entered."))
        return cleaned


class ContractSelect(forms.Select):
    """Adds data-facility to each <option> so the template's JS can filter
    the dropdown to only the contracts belonging to the currently-selected
    to_facility — mirrors DSRSSelect in operations/forms.py."""

    def __init__(self, *args, facility_map=None, **kwargs):
        self.facility_map = facility_map or {}
        super().__init__(*args, **kwargs)

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        facility_id = self.facility_map.get(str(value))
        if facility_id:
            option["attrs"]["data-facility"] = facility_id
        return option





class SourceMovementForm(forms.ModelForm):

    class Meta:
        model = SourceMovement

        fields = [
            "movement_type",
            "from_facility",
            "to_facility",
            "movement_date",
            "source_count",
            "remarks",
        ]

        labels = {
            "movement_type": _("Movement Type"),
            "from_facility": _("From Facility"),
            "to_facility": _("To Facility"),
            "movement_date": _("Movement Date"),
            "source_count": _("Quantity"),
            "remarks": _("Remarks"),
        }

        widgets = {
            "movement_date": forms.DateInput(attrs={"type": "text", "class": "datepicker"}),
            "remarks": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_tag = False

        self.helper.layout = Layout(
            Div(Field("movement_type"), Field("movement_date"), css_class="row"),
            Div(Field("from_facility"), Field("to_facility"), css_class="row"),
            Div(Field("source_count"), css_class="row"),
            Field("remarks"),
        )