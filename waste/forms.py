from django import forms
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Fieldset

from .models import (
    WasteBatch,
    LiquidWasteDetails,
    WasteConditioning,
    WasteType,
)


class WasteBatchForm(forms.ModelForm):

    class Meta:
        model = WasteBatch
        exclude = (
            "created_by",
            "created_at",
            "updated_at",
            "is_active",
        )

        widgets = {
            "date_received": forms.DateInput(attrs={"type": "date"}),
            "latest_analysis_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_tag = False


        readonly_fields = [
            "current_alpha_bq",
            "current_beta_bq",
            "current_gamma_bq",
            "current_total_activity_bq",
            "latest_analysis_date",
        ]


        for name, field in self.fields.items():

            field.widget.attrs.update({

                "class": "form-control"

            })


            if name in readonly_fields:

                field.widget.attrs.update({

                    "readonly": True,
                    "style": "background:#f2f2f2;"

                })

                field.help_text = (
                    "Calculated from approved laboratory analysis"
                )


        self.helper.layout = Layout(

            Fieldset(
                "General Information",
                "waste_id",
                "waste_type",
                "waste_class",
                "waste_state",
                "status",
            ),


            Fieldset(
                "Origin Information",
                "facility",
                "origin_of_waste",
                "date_received",
                "origin_facility",
            ),


            Fieldset(
                "Physical Information",
                "material",
                "container_type",
                "mass_kg",
                "volume_m3",
                "description",
            ),


            Fieldset(
                "Radiological Information",
                "current_alpha_bq",
                "current_beta_bq",
                "current_gamma_bq",
                "current_total_activity_bq",
                "latest_analysis_date",
            ),


            Fieldset(
                "Dose Rate",
                "dose_rate_surface",
                "dose_rate_1m",
                "alpha_contamination",
                "beta_gamma_contamination",
            ),


            Fieldset(
                "Storage",
                "location",
                "attachment",
            ),

        )


class LiquidWasteForm(forms.ModelForm):

    class Meta:
        model = LiquidWasteDetails
        exclude = ("batch",)

    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_tag = False


class WasteConditioningForm(forms.ModelForm):

    class Meta:
        model = WasteConditioning
        exclude = ("batch",)

    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_tag = False