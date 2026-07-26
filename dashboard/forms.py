from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Field, Submit, Div
from django import forms
from .models import DSRS,SourceMovement, MovementType


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
        ]

        widgets = {

            "Date_received": forms.DateInput(
                attrs={
                    "type": "text",
                    "class": "datepicker"
                }
            ),

            "Activity_reference_date": forms.DateInput(
                attrs={
                    "type": "text",
                    "class": "datepicker"
                }
            ),

            "Status_Date": forms.DateInput(
                attrs={
                    "type": "text",
                    "class": "datepicker"
                }
            ),

            "Dose_rate_measurement_date": forms.DateInput(
                attrs={
                    "type": "text",
                    "class": "datepicker"
                }
            ),

            "Comment": forms.Textarea(
                attrs={
                    "rows": 3
                }
            ),
        }


        labels = {
            "activity_input": "Activity",
            "Dose_rate_surface_uSv": "Surface Dose Rate (µSv/h)",
            "Dose_rate_1m_uSv": "1m Dose Rate (µSv/h)",
            "contamination_bq_cm2": "Contamination (Bq/cm²)",
        }


    def __init__(self, *args, **kwargs):

        user = kwargs.pop("user", None)

        super().__init__(*args, **kwargs)


        # Add * to required fields
        for name, field in self.fields.items():

            if field.required:
                field.label = f"{field.label} *"


        self.helper = FormHelper()

        self.helper.form_tag = False


        self.helper.layout = Layout(


            # -------------------------
            # Identification
            # -------------------------

            Div(
                Field("Source_Type"),
                Field("Sso_Code"),
                Field("serial_number"),
                Field("Nuclide"),

                css_class="row"
            ),


            # -------------------------
            # Origin
            # -------------------------

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



            # -------------------------
            # Activity
            # -------------------------

            Div(
                Field("activity_input"),
                Field("activity_unit"),
                Field("Activity_reference_date"),

                css_class="row"
            ),



            # -------------------------
            # Status
            # -------------------------

            Div(
                Field("source_state"),
                css_class="row",
            ),



            # -------------------------
            # Dose information
            # -------------------------

            Div(
                Field("Dose_rate_surface_uSv"),
                Field("Dose_rate_1m_uSv"),
                Field("Dose_rate_measurement_date"),

                css_class="row"
            ),


            Field("contamination_bq_cm2"),



            # -------------------------
            # Source details
            # -------------------------

            Div(

                Field("Source_Physical_Form"),
                Field("Source_Manufacturer"),
                Field("Source_Model"),

                css_class="row"

            ),


            Field("Source_Practice"),



            # -------------------------
            # Device details
            # -------------------------

            Div(

                Field("Device_Manufacturer"),
                Field("Device_Model"),
                Field("Device_Serial_Number"),

                css_class="row"

            ),



            # -------------------------
            # Storage/container
            # -------------------------

            Div(

                Field("Container_Type"),
                Field("Dimension"),

                css_class="row"

            ),



            Field("is_divisible"),
            Field("source_count"),
            Field("available_count"),



            Field("Attachments"),

            Field("Comment"),



            

        )



        # -------------------------
        # User restrictions
        # -------------------------

        if user:

            srs = user.groups.filter(
                name="SRS Users"
            ).exists()


            dsrs = user.groups.filter(
                name="DSRS Users"
            ).exists()



            if srs != dsrs:


                self.fields["Source_Type"].widget = (
                    forms.HiddenInput()
                )


                if srs:
                    self.initial["Source_Type"] = "SRS"

                else:
                    self.initial["Source_Type"] = "DSRS"



    def clean_activity_input(self):

        value = self.cleaned_data.get(
            "activity_input"
        )

        if value is not None and value <= 0:

            raise forms.ValidationError(
                "Activity must be positive."
            )

        return value



    def clean(self):

        cleaned = super().clean()


        if (
            cleaned.get("activity_input")
            and not cleaned.get("Nuclide")
        ):

            raise forms.ValidationError(
                "Nuclide is required when activity is entered."
            )


        return cleaned


    



class SourceMovementForm(forms.ModelForm):

    class Meta:
        model = SourceMovement

        fields = [
            "movement_type",
            "from_facility",
            "to_facility",
            "movement_date",
            "contract",
            "source_count",
            "remarks",
        ]

        widgets = {
            "movement_date": forms.DateInput(
                attrs={
                    "type": "text",
                    "class": "datepicker",
                }
            ),
            "remarks": forms.Textarea(
                attrs={"rows": 3}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_tag = False

        self.helper.layout = Layout(

            Div(
                Field("movement_type"),
                Field("movement_date"),
                css_class="row",
            ),

            Div(
                Field("from_facility"),
                Field("to_facility"),
                css_class="row",
            ),

            Div(
                Field("contract"),
                Field("source_count"),
                css_class="row",
            ),

            Field("remarks"),
        )