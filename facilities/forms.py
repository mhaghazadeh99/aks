from django import forms
from django.utils.translation import gettext_lazy as _
from django.urls import reverse
from crispy_forms.helper import FormHelper
from crispy_forms.layout import (
    Layout,
    Row,
    Column,
    Field,
    Submit,
    HTML,
)

from .models import FacilityModel



class FacilityForm(forms.ModelForm):

    class Meta:

        model = FacilityModel

        fields = [
            "name",
            "responsible_person",
            "telephone",
            "email",
            "address1",
            "address2",
            "postal_code",
            "national_id",
            "economic_code",
            
        ]


    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)


        self.helper = FormHelper()


        self.helper.form_method = "post"


        self.helper.layout = Layout(


            Row(
                Column(
                    Field("name"),
                    css_class="col-md-6"
                ),

                Column(
                    Field("responsible_person"),
                    css_class="col-md-6"
                ),
            ),



            Row(

                Column(
                    Field("telephone"),
                    css_class="col-md-4"
                ),


                Column(
                    Field("email"),
                    css_class="col-md-4"
                ),


                Column(
                    Field("postal_code"),
                    css_class="col-md-4"
                ),

            ),




            Row(

                Column(
                    Field("address1"),
                    css_class="col-md-6"
                ),


                Column(
                    Field("address2"),
                    css_class="col-md-6"
                ),

            ),





            Row(

                Column(
                    Field("national_id"),
                    css_class="col-md-6"
                ),


                Column(
                    Field("economic_code"),
                    css_class="col-md-6"
                ),

            ),


            HTML(
                """
                <div class="form-actions mt-4">
                    <a 
                    href="/facilities/"
                    class="btn btn-secondary">
                    {cancel}
                    </a>
                </div>
                """.format(
                    cancel=_("Cancel")
                )
            ),

            Submit(
                "submit",
                _("Save"),
                css_class="btn btn-primary mt-4"
            ),)
    def clean(self):
        cleaned_data = super().clean()

        name = cleaned_data.get("name")
        national_id = cleaned_data.get("national_id")
        postal_code = cleaned_data.get("postal_code")

        # Duplicate facility name
        if name:
            qs = FacilityModel.objects.filter(name__iexact=name)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError(
                    _("A facility with this name already exists.")
                )

        # Duplicate national ID
        if national_id:
            qs = FacilityModel.objects.filter(national_id=national_id)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError(
                    _("A facility with this national ID already exists.")
                )

        # Duplicate postal code
        if postal_code:
            qs = FacilityModel.objects.filter(postal_code=postal_code)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError(
                    _("A facility with this postal code already exists.")
                )

        return cleaned_data


class FacilityImportForm(forms.Form):

    csv_file = forms.FileField(
        label=_("CSV File")
    )