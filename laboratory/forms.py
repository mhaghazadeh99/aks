from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.forms import inlineformset_factory
from django.utils.translation import gettext_lazy as _

from crispy_forms.helper import FormHelper

from reference.models import Nuclides
from waste.models import WasteBatch

from .models import (
    AlphaBetaCountingRun, Analysis, CounterType, MAX_SAMPLES_PER_COUNTING_RUN,
    NuclideActivity, Sample, SampleStatus,
)


def _bootstrap(fields):
    for field in fields.values():
        existing = field.widget.attrs.get("class", "")
        if isinstance(field.widget, forms.CheckboxInput):
            field.widget.attrs["class"] = f"{existing} form-check-input".strip()
        elif "form-control" not in existing and "form-select" not in existing:
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
            "sample_id", "batch", "analysis_type", "applicant_name", "sample_type",
            "description", "sample_stage", "sampling_date", "sampling_location",
            "sample_mass_kg", "sample_volume_ml", "urgent", "sample_code_barcode", "remarks",
        ]
        widgets = {
            "sampling_date": forms.DateInput(attrs={"type": "text", "class": "form-control datepicker", "autocomplete": "off"}),
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
        self.fields["analysis_type"].required = True
        self.fields["analysis_type"].choices = [("", _("— Select analysis type —"))] + list(CounterType.choices)

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
    """Adapts to the sample's analysis type: Gamma (HPGE) or Alpha/Beta."""

    class Meta:
        model = Analysis
        fields = [
            "analysis_date", "counting_duration_seconds",
            "total_alpha", "alpha_uncertainty", "total_beta", "beta_uncertainty",
            "counting_run", "analysis_notes",
        ]
        widgets = {
            "analysis_date": forms.DateInput(
                attrs={"type": "text", "class": "form-control datepicker", "autocomplete": "off"}
            ),
            "analysis_notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, detector_type=None, **kwargs):
        super().__init__(*args, **kwargs)

        if detector_type == CounterType.HPGE:
            for name in ("total_alpha", "alpha_uncertainty", "total_beta", "beta_uncertainty", "counting_run"):
                del self.fields[name]
            self.fields["counting_duration_seconds"].required = True
            self.fields["generate_report"] = forms.BooleanField(
                required=False, label=_("Generate the Gamma report and start signatures"),
                initial=(self.instance.approvals.exists() if self.instance.pk else True),
            )
        else:
            self.fields["analysis_date"].required=False
            del self.fields["counting_duration_seconds"]  # comes from the counting run
            # only runs that haven't been finalized (no signature chain yet)
            open_runs = Q(approvals__isnull=True)
            if self.instance.counting_run_id:
                open_runs |= Q(pk=self.instance.counting_run_id)
            field = self.fields["counting_run"]
            field.queryset = AlphaBetaCountingRun.objects.filter(open_runs).distinct().order_by("-run_date")
            field.required = False
            field.empty_label = _("— Not in a run yet —")

        _bootstrap(self.fields)
        self.helper = FormHelper()
        self.helper.form_tag = False

    def clean_counting_run(self):
        run = self.cleaned_data.get("counting_run")
        if run and run.pk != self.instance.counting_run_id and run.sample_count >= MAX_SAMPLES_PER_COUNTING_RUN:
            raise ValidationError(_("That run already has 12 samples."))
        return run

        
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




class AlphaBetaCountingRunForm(forms.ModelForm):

    class Meta:
        model = AlphaBetaCountingRun
        fields = ["run_id", "run_date", "applicant_name", "sampling_location", "sampling_date_from", "sampling_date_to","counting_duration_seconds", "alpha_mda_mbq", "beta_mda_mbq", "notes"]
        widgets = {
            "sampling_date_from": forms.DateInput(attrs={"type": "text", "class": "form-control datepicker", "autocomplete": "off"}),
            "sampling_date_to": forms.DateInput(attrs={"type": "text", "class": "form-control datepicker", "autocomplete": "off"}),
            "run_date": forms.DateInput(attrs={"type": "text", "class": "form-control datepicker", "autocomplete": "off"}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _bootstrap(self.fields)
        self.helper = FormHelper()
        self.helper.form_tag = False


class LabReportUploadForm(forms.Form):
    """Same replace-with-hand-filled-version pattern as the license/
    receive apps' SpecificationUploadForm."""

    file = forms.FileField(label=_("Upload Filled Report (.docx)"))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _bootstrap(self.fields)
        self.helper = FormHelper()
        self.helper.form_tag = False



class CollectorRunForm(forms.ModelForm):
    """Run creation, collector-facing: no run_id (auto-generated), no counting
    data (duration/MDAs/calibration — the lab adds those later via CountingRunEditForm)."""

    class Meta:
        model = AlphaBetaCountingRun
        fields = ["applicant_name", "sampling_location", "sampling_date_from", "sampling_date_to", "sample_stage", "notes"]
        widgets = {
            "sampling_date_from": forms.DateInput(attrs={"type": "text", "class": "form-control datepicker", "autocomplete": "off"}),
            "sampling_date_to": forms.DateInput(attrs={"type": "text", "class": "form-control datepicker", "autocomplete": "off"}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("sampling_location", "sampling_date_to", "notes"):
            self.fields[name].required = False
        _bootstrap(self.fields)
        self.helper = FormHelper()
        self.helper.form_tag = False