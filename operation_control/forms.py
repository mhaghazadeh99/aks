from crispy_forms.helper import FormHelper
from crispy_forms.layout import Column, Field, Layout, Row
from django import forms
from django.utils.translation import gettext_lazy as _

from .models import CalibrationRecord, Equipment


def _bootstrap(fields):
    for field in fields.values():
        existing = field.widget.attrs.get("class", "")
        if "form-control" not in existing and "form-select" not in existing:
            field.widget.attrs["class"] = f"{existing} form-control".strip()


class EquipmentForm(forms.ModelForm):
    class Meta:
        model = Equipment
        fields = [
            "name", "equipment_id", "model_name", "serial_number", "manufacturer", "application",
            "status", "loan_to", "center", "current_location",
            "calibration_period_months", "current_label", "notes",
        ]
        widgets = {"notes": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _bootstrap(self.fields)
        self.fields["application"].queryset = self.fields["application"].queryset.filter(is_active=True)
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Row(Column(Field("name"), css_class="col-md-6"), Column(Field("equipment_id"), css_class="col-md-3"),
                Column(Field("application"), css_class="col-md-3")),
            Row(Column(Field("model_name"), css_class="col-md-4"), Column(Field("serial_number"), css_class="col-md-4"),
                Column(Field("manufacturer"), css_class="col-md-4")),
            Row(Column(Field("status"), css_class="col-md-3"), Column(Field("loan_to"), css_class="col-md-3"),
                Column(Field("center"), css_class="col-md-3"), Column(Field("current_location"), css_class="col-md-3")),
            Row(Column(Field("calibration_period_months"), css_class="col-md-3"),
                Column(Field("current_label"), css_class="col-md-3")),
            Field("notes"),
        )

    def clean(self):
        data = super().clean()
        if data.get("status") == Equipment.Status.ON_LOAN and not data.get("loan_to"):
            self.add_error("loan_to", _("Say who the device is loaned to."))
        return data


class CalibrationRecordForm(forms.ModelForm):
    class Meta:
        model = CalibrationRecord
        fields = ["calibration_date", "certificate_number", "laboratory", "calibration_type",
                  "result_label", "attachment", "notes"]
        widgets = {"notes": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _bootstrap(self.fields)
        self.fields["result_label"].empty_label = _("— keep current label —")
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Row(Column(Field("calibration_date"), css_class="col-md-4"),
                Column(Field("certificate_number"), css_class="col-md-4"),
                Column(Field("laboratory"), css_class="col-md-4")),
            Row(Column(Field("calibration_type"), css_class="col-md-6"),
                Column(Field("result_label"), css_class="col-md-6")),
            Field("attachment"),
            Field("notes"),
        )
