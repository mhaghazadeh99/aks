from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit
from django import forms
from .models import DSRS

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Field, Submit




class DSRSForm(forms.ModelForm):
    
    class Meta:
        model = DSRS
        exclude = ['created_by','created_at','initial_activity_bq']
        widgets = {
            'Date_received': forms.DateInput(attrs={'type': 'date'}),
            'Activity_reference_date': forms.DateInput(attrs={'type': 'date'}),
            'Status_Date': forms.DateInput(attrs={'type': 'date'}),
            'Dose_rate_measurement_date': forms.DateInput(attrs={'type': 'date'}),
        }
        labels = {
            "activity_input_mci": "Initial Activity (mCi)",
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        for name, field in self.fields.items():
            if field.required:
                field.label = f"{field.label} *"
        
        if user:
                srs = user.groups.filter(name="SRS Users").exists()
                dsrs = user.groups.filter(name="DSRS Users").exists()

                if srs != dsrs:   # only one group
                    self.fields["Source_Type"].disabled = True

                    if srs:
                        self.initial["Source_Type"] = "SRS"
                    else:
                        self.initial["Source_Type"] = "DSRS"
        # def __init__(self, *args, **kwargs):
    #     super().__init__(*args, **kwargs)
    #     for field in self.fields.values():
    #         field.widget.attrs.update({'class': 'form-control'})
            
    #     self.helper = FormHelper()
    #     self.helper.form_method = 'post'
        # self.helper.layout = Layout(
        #     Field('field1'),
        #     Field('field2'),
        #     Submit('submit', 'Save')
        
        # self.helper.add_input(Submit('submit', 'Save DSRS'))
        

  
    # -------------------------
    # FIELD-LEVEL VALIDATION
    # -------------------------
    def clean_activity_input_mci(self):
        val = self.cleaned_data.get("activity_input_mci")

        if val is not None and val <= 0:
            raise forms.ValidationError("Activity must be positive.")

        return val

    # -------------------------
    # CROSS-FIELD VALIDATION
    # -------------------------
    def clean(self):
        cleaned = super().clean()

        activity = cleaned.get("activity_input_mci")
        nuclide = cleaned.get("Nuclide")

        if activity and not nuclide:
            raise forms.ValidationError("Nuclide is required when activity is set.")

        return cleaned