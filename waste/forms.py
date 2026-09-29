from django import forms
from django.utils.translation import gettext_lazy as _

from crispy_forms.helper import FormHelper

from .models import (
    WasteBatch,
    WasteMovement,
    WasteState,
    WasteType,
    ConditioningMaterial,
)

def _bootstrap(fields):
    for field in fields.values():
        existing = field.widget.attrs.get("class", "")
        if "form-control" not in existing and "form-select" not in existing:
            field.widget.attrs["class"] = f"{existing} form-control".strip()


# Which fields only apply to which waste_type / waste_state. Used by
# both the form (to relax validation) and the template JS (to show/hide
# live as the user changes the dropdowns), so the two can't drift apart.
LIQUID_ONLY_FIELDS = ["ph", "density", "total_solids", "suspended_solids", "soluble_solids"]
UNPROCESSED_ONLY_FIELDS = ["possible_pretreatment", "possible_treatment"]
PROCESSED_ONLY_FIELDS = ["pretreatment", "treatment", "package_type", "waste_matrix"]
PROCESSED_LIQUID_ONLY_FIELDS = [
    "waste_to_matrix_ratio",
    "waste_mass_kg",
    "package_mass_kg",
    "package_volume_m3",
]


class WasteBatchForm(forms.ModelForm):

    class Meta:
        model = WasteBatch
        fields = [
            "waste_id",
            "waste_type",
            "waste_class",
            "waste_state",
            "facility",
            "origin_facility",
            "origin_of_waste",
            "date_received",
            "description",
            "waste_arising_from",
            "material",
            "container_type",
            "waste_appearance",
            "mass_kg",
            "volume_m3",
            "dose_rate_surface_uSv",
            "dose_rate_1m_uSv",
            "dose_rate_date",
            "alpha_contamination_bq_cm2",
            "beta_gamma_contamination_bq_cm2",
            # liquid
            "ph", "density", "total_solids", "suspended_solids", "soluble_solids",
            # unprocessed
            "possible_pretreatment", "possible_treatment",
            # processed
            "pretreatment", "treatment", "package_type", "waste_matrix",
            # processed + liquid
            "waste_to_matrix_ratio", "waste_mass_kg", "package_mass_kg", "package_volume_m3",
            "location",
            "attachment",
        ]
        widgets = {
            "date_received": forms.DateInput(
                attrs={"type": "text", "class": "form-control datepicker", "autocomplete": "off"}
            ),
            "dose_rate_date": forms.DateInput(
                attrs={"type": "text", "class": "form-control datepicker", "autocomplete": "off"}
            ),
            "description": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _bootstrap(self.fields)
        self.helper = FormHelper()
        self.helper.form_tag = False

        # Tag each conditional field so the template JS can find and
        # toggle it without hardcoding a second copy of these lists.
        for name in LIQUID_ONLY_FIELDS:
            self.fields[name].widget.attrs["data-show-when-type"] = "LIQUID"
        for name in UNPROCESSED_ONLY_FIELDS:
            self.fields[name].widget.attrs["data-show-when-state"] = "UNPROCESSED"
        for name in PROCESSED_ONLY_FIELDS:
            self.fields[name].widget.attrs["data-show-when-state"] = "PROCESSED"
        for name in PROCESSED_LIQUID_ONLY_FIELDS:
            self.fields[name].widget.attrs["data-show-when-state"] = "PROCESSED"
            self.fields[name].widget.attrs["data-show-when-type"] = "LIQUID"

    def clean(self):
        """
        Blank out any field that doesn't apply to the chosen type/state,
        so a user who fills something in, then switches the dropdown,
        doesn't silently leave stale irrelevant data behind on the record.
        """
        cleaned = super().clean()

        waste_type = cleaned.get("waste_type")
        waste_state = cleaned.get("waste_state")

        if waste_type != WasteType.LIQUID:
            for name in LIQUID_ONLY_FIELDS:
                cleaned[name] = None

        if waste_state == WasteState.PROCESSED:
            for name in UNPROCESSED_ONLY_FIELDS:
                cleaned[name] = None
        else:
            for name in PROCESSED_ONLY_FIELDS:
                cleaned[name] = None

        if not (waste_state == WasteState.PROCESSED and waste_type == WasteType.LIQUID):
            for name in PROCESSED_LIQUID_ONLY_FIELDS:
                cleaned[name] = None

        return cleaned


class WasteMovementForm(forms.ModelForm):

    class Meta:
        model = WasteMovement
        fields = [
            "movement_type",
            "from_facility",
            "to_facility",
            "movement_date",
            "mass_kg",
            "volume_m3",
            "remarks",
        ]
        widgets = {
            "movement_date": forms.DateInput(
                attrs={"type": "text", "class": "form-control datepicker", "autocomplete": "off"}
            ),
            "remarks": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _bootstrap(self.fields)
        self.helper = FormHelper()
        self.helper.form_tag = False


class MergeBatchesForm(forms.Form):

    new_waste_id = forms.CharField(label=_("New Batch ID"), max_length=100)
    mass_kg = forms.DecimalField(
        label=_("Measured Mass (kg)"), required=False,
        help_text=_("Leave blank to use the sum of the merged batches."),
    )
    volume_m3 = forms.DecimalField(
        label=_("Measured Volume (m³)"), required=False,
        help_text=_("Leave blank to use the sum of the merged batches."),
    )
    container_type = forms.CharField(label=_("Container Type"), max_length=100, required=False)
    location = forms.CharField(label=_("Storage Location"), max_length=100, required=False)
    remarks = forms.CharField(label=_("Remarks"), widget=forms.Textarea(attrs={"rows": 2}), required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _bootstrap(self.fields)
        self.helper = FormHelper()
        self.helper.form_tag = False


class ConditionBatchForm(forms.Form):
    """Conditioning always outputs a PROCESSED SOLID batch — these are
    the processed-only fields the operator fills in for it."""

    new_waste_id = forms.CharField(label=_("New Batch ID"), max_length=100)
    pretreatment = forms.ChoiceField(label=_("Pre-Treatment Applied"), required=False)
    treatment = forms.ChoiceField(label=_("Treatment Applied"), required=False)
    package_type = forms.CharField(label=_("Package Type"), max_length=100, required=False)
    waste_matrix = forms.CharField(label=_("Waste Matrix"), max_length=100, required=False)
    waste_to_matrix_ratio = forms.DecimalField(label=_("Waste to Matrix Ratio"), required=False)
    package_mass_kg = forms.DecimalField(label=_("Package Mass (kg)"), required=False)
    package_volume_m3 = forms.DecimalField(label=_("Package Volume (m³)"), required=False)
    mass_kg = forms.DecimalField(label=_("Resulting Mass (kg)"), required=False)
    volume_m3 = forms.DecimalField(label=_("Resulting Volume (m³)"), required=False)
    location = forms.CharField(label=_("Storage Location"), max_length=100, required=False)
    remarks = forms.CharField(label=_("Remarks"), widget=forms.Textarea(attrs={"rows": 2}), required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from .models import PreTreatmentOption, TreatmentOption

        self.fields["pretreatment"].choices = [("", "---------")] + list(PreTreatmentOption.choices)
        self.fields["treatment"].choices = [("", "---------")] + list(TreatmentOption.choices)

        _bootstrap(self.fields)
        self.helper = FormHelper()
        self.helper.form_tag = False
