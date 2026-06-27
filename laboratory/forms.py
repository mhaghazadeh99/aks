from django import forms
from .models import Sample, Analysis, GammaActivity


class SampleCreateForm(forms.ModelForm):

    class Meta:
        model = Sample

        fields = [
            'sample_id',
            'sample_stage',
            'sampling_date',
            'sample_mass_kg',
            'sample_volume_l',
            'urgent',
            'remarks'
        ]

        widgets = {
            'sampling_date': forms.DateInput(
                attrs={'type': 'date'}
            )
        }

class SampleForm(forms.ModelForm):

    class Meta:
        model = Sample
        fields = [
            'sample_id',
            'sample_stage',
            'sampling_date',
            'sample_mass_kg',
            'sample_volume_l',
            'urgent',
            'remarks'
        ]


class AnalysisForm(forms.ModelForm):

    class Meta:
        model = Analysis
        fields = [
            'analysis_date',
            'total_alpha',
            'total_beta',
            'approved'
        ]


class GammaActivityForm(forms.ModelForm):

    class Meta:
        model = GammaActivity
        fields = [
            'radionuclide',
            'activity_bq'
        ]