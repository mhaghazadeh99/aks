from django import forms
from django.forms import inlineformset_factory
from django.utils.translation import gettext_lazy as _

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit

from .models import (
    Operation,
    OperationSource,
    OperationAttachment,
    OperationSignature,
)

from reference.models import Nuclides
from facilities.models import Facility


# ============================================================
# Crispy helper
# ============================================================

def crispy_helper(instance, button_text):

    helper = FormHelper()

    helper.form_method = "post"

    helper.add_input(
        Submit(
            "submit",
            button_text
        )
    )

    return helper



# ============================================================
# Operation Form
# ============================================================

# operations/forms.py

from django import forms

from .models import Operation


class OperationForm(forms.ModelForm):

    class Meta:

        model = Operation

        fields = [
            "operation_type",
            "facility",
            "notes",
        ]

        widgets = {

            "notes": forms.Textarea(
                attrs={
                    "rows":4,
                    "class":"form-control"
                }
            ),

            "operation_type": forms.Select(
                attrs={
                    "class":"form-select"
                }
            ),

            "facility": forms.Select(
                attrs={
                    "class":"form-select"
                }
            ),
        }

    
from .models import OperationAttachment


class OperationAttachmentUploadForm(forms.ModelForm):

    class Meta:

        model = OperationAttachment

        fields = [
            "attachment_type",
            "file",
        ]


    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)


        self.fields["file"].widget.attrs.update(
            {
                "class":"form-control"
            }
        )

        self.fields["attachment_type"].widget.attrs.update(
            {
                "class":"form-select"
            }
        )
# ============================================================
# Operation Source Form
# ============================================================

class OperationSourceForm(forms.ModelForm):


    nuclides = forms.ModelMultipleChoiceField(

        queryset=Nuclides.objects.all(),

        required=True,

        widget=forms.SelectMultiple(
            attrs={
                "class": "form-control",
                "size": 5,
            }
        ),

        label=_("Nuclides"),

    )



    class Meta:

        model = OperationSource


        fields = [

            "nuclides",

            "source_model",

            "serial_number",

            "activity",

            "activity_unit",

            "half_life",

            "remarks",

        ]



    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)


        self.helper = crispy_helper(
            self,
            _("Save Source")
        )


        # Load existing M2M values during edit

        if self.instance.pk:

            self.fields["nuclides"].initial = (
                self.instance.nuclides.all()
            )



# ============================================================
# Source Formset
# ============================================================

OperationSourceFormSet = inlineformset_factory(

    Operation,

    OperationSource,

    form=OperationSourceForm,

    extra=1,

    can_delete=True,

)



# ============================================================
# Attachment Form
# ============================================================

class OperationAttachmentForm(forms.ModelForm):


    class Meta:

        model = OperationAttachment


        fields = [

            "attachment_type",

            "title",

            "file",

        ]



    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)


        self.helper = crispy_helper(
            self,
            _("Upload Attachment")
        )



# ============================================================
# Attachment Formset
# ============================================================

OperationAttachmentFormSet = inlineformset_factory(

    Operation,

    OperationAttachment,

    form=OperationAttachmentForm,

    extra=1,

    can_delete=True,

)



# ============================================================
# Signature Form
# ============================================================

class OperationSignatureForm(forms.ModelForm):


    class Meta:

        model = OperationSignature


        fields = [

            "role",

            "user",

            "remarks",

        ]



    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)


        self.helper = crispy_helper(
            self,
            _("Save Signature")
        )



# ============================================================
# Signature Formset
# ============================================================

OperationSignatureFormSet = inlineformset_factory(

    Operation,

    OperationSignature,

    form=OperationSignatureForm,

    extra=1,

    can_delete=True,)



from .models import OperationOCR


class OperationOCRForm(forms.ModelForm):

    class Meta:

        model = OperationOCR

        fields = [
            "extracted_data",
        ]

        widgets = {

            "extracted_data": forms.HiddenInput()

        }