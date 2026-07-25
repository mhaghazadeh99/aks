from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Field, Submit, Div
from django import forms

from .models import DSRS


class DSRSForm(forms.ModelForm):

    class Meta:
        model = DSRS
        exclude = [
            'created_by',
            'created_at',
            'initial_activity_bq'
        ]

        widgets = {

            'Date_received': forms.DateInput(
                attrs={
                     'type':'text',
                    'class': 'datepicker'
                }
            ),

            'Activity_reference_date': forms.DateInput(
                attrs={
                    'type':'text',
                    'class': 'datepicker'
                }
            ),

            'Status_Date': forms.DateInput(
                attrs={
                     'type':'text',
                    'class': 'datepicker'
                }
            ),

            'Dose_rate_measurement_date': forms.DateInput(
                attrs={
                     'type':'text',
                    'class': 'datepicker'
                }
            ),
        }


        labels = {
        "activity_input":
        "Initial Activity",
        }



    def __init__(self, *args, **kwargs):

        user = kwargs.pop("user", None)

        super().__init__(*args, **kwargs)


        # Required fields

        for name, field in self.fields.items():

            if field.required:
                field.label = f"{field.label} *"



        # Crispy

        self.helper = FormHelper()

        self.helper.form_method = "post"

        self.helper.layout = Layout(

            Div(
                Field("Source_Type"),
                Field("serial_number"),
                Field("Nuclide"),
                css_class="row"
            ),

            Field("activity_input"),
            Field("activity_unit"),

            Field("Date_received"),

            Field("Activity_reference_date"),

            Field("Recycled"),

            Field("Status_Date"),

            Field("Dose_rate_measurement_date"),

            Field("Responsible_Person"),

            Field("Facility"),

            Submit(
                "submit",
                "Save Source",
                css_class="btn btn-primary"
            )

        )


        # Group logic

        if user:

            srs = user.groups.filter(
                name="SRS Users"
            ).exists()

            dsrs = user.groups.filter(
                name="DSRS Users"
            ).exists()


            if srs != dsrs:

                self.fields[
                    "Source_Type"
                ].disabled = True


                if srs:

                    self.initial[
                        "Source_Type"
                    ] = "SRS"

                else:

                    self.initial[
                        "Source_Type"
                    ] = "DSRS"



    def clean_activity_input_mci(self):

        val = self.cleaned_data.get(
            "activity_input_mci"
        )


        if val is not None and val <= 0:

            raise forms.ValidationError(
                "Activity must be positive."
            )


        return val



    def clean(self):

        cleaned = super().clean()


        activity = cleaned.get(
            "activity_input_mci"
        )

        nuclide = cleaned.get(
            "Nuclide"
        )


        if activity and not nuclide:

            raise forms.ValidationError(
                "Nuclide is required when activity is set."
            )


        return cleaned