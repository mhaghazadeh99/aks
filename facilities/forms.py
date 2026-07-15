from django import forms
from django.utils.translation import gettext_lazy as _

from crispy_forms.helper import FormHelper
from crispy_forms.layout import (
    Layout,
    Row,
    Column,
    Field,
    Submit,
    HTML,
)

from .models import Facility



class FacilityForm(forms.ModelForm):

    class Meta:

        model = Facility

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



class FacilityImportForm(forms.Form):

    csv_file = forms.FileField(
        label=_("CSV File")
    )