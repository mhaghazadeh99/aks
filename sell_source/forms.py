from django import forms
from django.utils.translation import gettext_lazy as _

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Field, Row, Column

from dashboard.models import DSRS, SOURCE_STATUS

from .models import SellRequest


def _bootstrap(fields):
    for field in fields.values():
        existing = field.widget.attrs.get("class", "")
        if "form-control" not in existing and "form-select" not in existing:
            field.widget.attrs["class"] = f"{existing} form-control".strip()


class SellRequestForm(forms.ModelForm):

    class Meta:
        model = SellRequest
        fields = ["request_form"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _bootstrap(self.fields)
        self.helper = FormHelper()
        self.helper.form_tag = False


class SellSourceForm(forms.Form):
    """
    The "add source" picker for the specification step — only sources
    already STORED in our own inventory are sellable. Nuclide, serial
    number, manufacture date, and recorded (current, decayed) activity
    are all pulled from the chosen DSRS automatically in the view; this
    form only needs the DSRS itself plus the two free-text fields.
    """

    dsrs = forms.ModelChoiceField(
        queryset=DSRS.objects.none(),
        empty_label=_("Select a source from inventory"),
        label=_("Source (from inventory)"),
    )

    physical_characteristics = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
        label=_("مشخصات فیزیکی / Physical Characteristics"),
    )

    remarks = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
        label=_("ملاحظات / Remarks"),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["dsrs"].queryset = (
            DSRS.objects.filter(Status=SOURCE_STATUS.STORED)
            .select_related("Nuclide")
            .order_by("Nuclide__name", "serial_number")
        )
        self.fields["dsrs"].label_from_instance = lambda d: (
            f"{d.Nuclide} — {d.serial_number or '-'} ({d.current_activity_mci_value or '?'} mCi)"
        )

        _bootstrap(self.fields)
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Field("dsrs"),
            Field("physical_characteristics"),
            Field("remarks"),
        )