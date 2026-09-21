from django import forms
from django.forms import inlineformset_factory
from django.utils.translation import gettext_lazy as _

from crispy_forms.helper import FormHelper

from reference.models import Nuclides
from waste.models import WasteBatch

from .models import Analysis, NuclideActivity, Sample, SampleStatus


def _bootstrap(fields):
    for field in fields.values():
        existing = field.widget.attrs.get("class", "")
        if "form-control" not in existing and "form-select" not in existing:
            field.widget.attrs["class"] = f"{existing} form-control".strip()


class SampleForm(forms.ModelForm):
    """
    Works for BOTH standalone samples and batch-linked ones. `batch` is
    optional — leave it blank for an independent sample (smear,
    environmental, incoming material), in which case `description`
    becomes the thing that identifies what was sampled.
    """

    class Meta:
        model = Sample
        fields = [
            "sample_id",
            "batch",
            "description",
            "sample_stage",
            "sampling_date",
            "sample_mass_kg",
            "sample_volume_l",
            "urgent",
            "sample_code_barcode",
            "remarks",
        ]
        widgets = {
            "sampling_date": forms.DateInput(
                attrs={"type": "text", "class": "form-control datepicker", "autocomplete": "off"}
            ),
            "remarks": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Consumed batches can't be sampled — they no longer physically exist.
        self.fields["batch"].queryset = (
            WasteBatch.objects.exclude(status="CONSUMED").order_by("waste_id")
        )
        self.fields["batch"].required = False
        self.fields["batch"].empty_label = _("— Standalone sample (no waste batch) —")

        _bootstrap(self.fields)
        self.helper = FormHelper()
        self.helper.form_tag = False

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("batch") and not cleaned.get("description"):
            self.add_error(
                "description",
                _("A standalone sample needs a description saying what was sampled."),
            )
        return cleaned


class LabReceiveForm(forms.ModelForm):
    """Used by the lab when physically taking delivery of a sample."""

    class Meta:
        model = Sample
        fields = ["lab_received_date", "lab_comments"]
        widgets = {
            "lab_received_date": forms.DateInput(
                attrs={"type": "text", "class": "form-control datepicker", "autocomplete": "off"}
            ),
            "lab_comments": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _bootstrap(self.fields)
        self.helper = FormHelper()
        self.helper.form_tag = False


class AnalysisForm(forms.ModelForm):

    class Meta:
        model = Analysis
        fields = ["analysis_date", "total_alpha", "total_beta", "analysis_notes"]
        widgets = {
            "analysis_date": forms.DateInput(
                attrs={"type": "text", "class": "form-control datepicker", "autocomplete": "off"}
            ),
            "analysis_notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _bootstrap(self.fields)
        self.helper = FormHelper()
        self.helper.form_tag = False


class NuclideActivityForm(forms.ModelForm):

    class Meta:
        model = NuclideActivity
        fields = ["radionuclide", "radiation_type", "activity_bq", "uncertainty_bq", "mda_bq"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["radionuclide"].queryset = Nuclides.objects.order_by("name")
        _bootstrap(self.fields)
        self.helper = FormHelper()
        self.helper.form_tag = False


NuclideActivityFormSet = inlineformset_factory(
    Analysis,
    NuclideActivity,
    form=NuclideActivityForm,
    extra=3,
    can_delete=True,
)
