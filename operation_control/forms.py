from crispy_forms.helper import FormHelper
from crispy_forms.layout import Column, Field, Layout, Row
from django import forms
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.forms import inlineformset_factory
from django.utils.translation import gettext_lazy as _

from . import jalali_utils as ju
from .models import (
    CalibrationRecord, Equipment, InspectionItem, InspectionPlanYear, InspectionRecord,
    OnlineDoseRecord, OperationDoseSession, OperationType, RadiationWorker, TLDReading, TLDReport,
)


def _bootstrap(fields):
    for field in fields.values():
        existing = field.widget.attrs.get("class", "")
        if isinstance(field.widget, forms.CheckboxInput):
            if "form-check-input" not in existing:
                field.widget.attrs["class"] = f"{existing} form-check-input".strip()
        elif "form-control" not in existing and "form-select" not in existing:
            field.widget.attrs["class"] = f"{existing} form-control".strip()


def date_widget():
    """Same widget the waste forms use: the Jalali datepicker attaches to .datepicker."""
    return forms.DateInput(attrs={"type": "text", "class": "form-control datepicker", "autocomplete": "off"})


class BaseModelForm(forms.ModelForm):
    """Bootstrap classes + a crispy helper without its own <form> tag (templates add it)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _bootstrap(self.fields)
        self.helper = FormHelper()
        self.helper.form_tag = False


# ============================================================ calibration
class EquipmentForm(BaseModelForm):
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
        self.fields["application"].queryset = self.fields["application"].queryset.filter(is_active=True)
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


class CalibrationRecordForm(BaseModelForm):
    class Meta:
        model = CalibrationRecord
        fields = ["calibration_date", "certificate_number", "laboratory", "calibration_type",
                  "result_label", "attachment", "notes"]
        widgets = {"calibration_date": date_widget(), "notes": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["result_label"].empty_label = _("— keep current label —")
        self.helper.layout = Layout(
            Row(Column(Field("calibration_date"), css_class="col-md-4"),
                Column(Field("certificate_number"), css_class="col-md-4"),
                Column(Field("laboratory"), css_class="col-md-4")),
            Row(Column(Field("calibration_type"), css_class="col-md-6"),
                Column(Field("result_label"), css_class="col-md-6")),
            Field("attachment"),
            Field("notes"),
        )


# ============================================================ dosimetry
class RadiationWorkerForm(BaseModelForm):
    class Meta:
        model = RadiationWorker
        fields = ["personnel_code", "full_name", "unit", "position", "status", "exit_date", "notes"]
        widgets = {"exit_date": date_widget(), "notes": forms.Textarea(attrs={"rows": 2})}


class OperationTypeForm(BaseModelForm):
    class Meta:
        model = OperationType
        fields = ["name"]


class TLDReportForm(BaseModelForm):
    class Meta:
        model = TLDReport
        fields = ["year", "season", "report_number", "received_date", "attachment", "notes"]
        widgets = {"received_date": date_widget(), "notes": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            self.fields["year"].initial = ju.jalali_today()[0]


class TLDReadingForm(BaseModelForm):
    class Meta:
        model = TLDReading
        fields = ["tld_code", "position", "worker", "env_point", "gamma_msv", "neutron_msv", "remarks"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["worker"].queryset = RadiationWorker.objects.order_by("full_name")


TLDReadingFormSet = inlineformset_factory(
    TLDReport, TLDReading, form=TLDReadingForm, extra=5, can_delete=True)


class OperationDoseSessionForm(BaseModelForm):
    class Meta:
        model = OperationDoseSession
        fields = ["operation_type", "performed_date", "location", "duration_minutes", "description"]
        widgets = {"performed_date": date_widget(), "description": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        qs = OperationType.objects.filter(is_active=True)
        if self.instance.pk:
            qs = OperationType.objects.filter(Q(is_active=True) | Q(pk=self.instance.operation_type_id))
        self.fields["operation_type"].queryset = qs


class DeviceChoiceField(forms.ModelChoiceField):
    """Shows a warning next to devices whose calibration is expired / about to expire."""

    def label_from_instance(self, obj):
        label = f"{obj.equipment_id} — {obj.name}"
        status = obj.calibration_status
        if status in (Equipment.CalStatus.EXPIRED, Equipment.CalStatus.DUE_SOON):
            label += f"  ⚠ {status.label}"
        return label


class OnlineDoseRecordForm(BaseModelForm):
    device = DeviceChoiceField(queryset=Equipment.objects.none(), label=_("Device"))

    class Meta:
        model = OnlineDoseRecord
        fields = ["worker", "device", "dose_type", "dose_value", "dose_unit", "exposure_minutes"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        workers = Q(status=RadiationWorker.Status.ACTIVE)
        devices = Q(application__is_personal_dosimetry=True) & ~Q(status=Equipment.Status.INACTIVE)
        if self.instance.pk:
            workers |= Q(pk=self.instance.worker_id)
            devices |= Q(pk=self.instance.device_id)
        self.fields["worker"].queryset = RadiationWorker.objects.filter(workers).order_by("full_name")
        self.fields["device"].queryset = Equipment.objects.filter(devices).order_by("equipment_id")
        self.fields["dose_value"].widget.attrs.update({"step": "any", "min": "0"})

    def clean_dose_value(self):
        value = self.cleaned_data["dose_value"]
        if value is not None and value < 0:
            raise forms.ValidationError(_("Dose cannot be negative."))
        return value


OnlineDoseFormSet = inlineformset_factory(
    OperationDoseSession, OnlineDoseRecord, form=OnlineDoseRecordForm,
    extra=3, can_delete=True, min_num=1, validate_min=True)


class TLDPasteForm(forms.Form):
    pasted = forms.CharField(
        label=_("Pasted rows"), widget=forms.Textarea(attrs={"rows": 14, "dir": "ltr", "class": "form-control"}))


# ============================================================ inspection plan
class InspectionYearForm(BaseModelForm):
    class Meta:
        model = InspectionPlanYear
        fields = ["year", "first_month"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["first_month"].widget = forms.Select(
            choices=[(m, f"{m}") for m in range(1, 13)], attrs={"class": "form-control"})
        if not self.instance.pk:
            self.fields["year"].initial = ju.jalali_today()[0]


class InspectionItemForm(BaseModelForm):
    class Meta:
        model = InspectionItem
        fields = ["title", "form_title", "form_code", "area", "responsible", "period_weeks", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["responsible"].queryset = get_user_model().objects.filter(is_active=True)


class InspectionRecordForm(BaseModelForm):
    class Meta:
        model = InspectionRecord
        fields = ["is_done", "done_date", "done_by", "note", "attachment"]
        widgets = {"done_date": date_widget(), "note": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["done_by"].queryset = get_user_model().objects.filter(is_active=True)
