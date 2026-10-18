from crispy_forms.helper import FormHelper
from crispy_forms.layout import Column, Field, Layout, Row
from django import forms
from django.core.validators import FileExtensionValidator
from django.db.models import Q
from django.forms import inlineformset_factory
from django.utils.translation import gettext_lazy as _

from common.utils.fileValidator import validate_attachment

from . import conf
from . import jalali_utils as ju
from .models import (
    CalibrationAssessment, CalibrationRecord, Equipment, InspectionItem, InspectionPlanYear, InspectionRecord,
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


def personal_dosimeters_defined():
    """True when at least one device belongs to an application ticked as 'personal dosimeter'."""
    return Equipment.objects.filter(application__is_personal_dosimetry=True).exists()


def eligible_devices(include_pk=None):
    """
    Devices offered in operation dose records: active devices whose application is ticked as a personal
    dosimeter. If NO application has been ticked yet, every non-inactive device is offered (the page warns about it)
    instead of showing an empty list.
    """
    usable = Equipment.objects.exclude(status=Equipment.Status.INACTIVE)
    flagged = usable.filter(application__is_personal_dosimetry=True)
    qs = flagged if personal_dosimeters_defined() else usable
    if include_pk:
        qs = Equipment.objects.filter(Q(pk__in=qs.values("pk")) | Q(pk=include_pk))
    return qs.select_related("application").order_by("equipment_id")


class DeviceChoiceField(forms.ModelChoiceField):
    """'PH-0007E21 — SmartRad [Personnel dosimetry]', with a warning if the calibration is expired / expiring."""

    def label_from_instance(self, obj):
        label = f"{obj.equipment_id} — {obj.name}"
        if obj.application_id:
            label += f" [{obj.application}]"
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
        if self.instance.pk:
            workers |= Q(pk=self.instance.worker_id)
        self.fields["worker"].queryset = RadiationWorker.objects.filter(workers).order_by("full_name")
        self.fields["device"].queryset = eligible_devices(self.instance.device_id if self.instance.pk else None)
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
        workers = Q(status=RadiationWorker.Status.ACTIVE)
        if self.instance.pk and self.instance.responsible_id:
            workers |= Q(pk=self.instance.responsible_id)
        self.fields["responsible"].queryset = RadiationWorker.objects.filter(workers).order_by("full_name")


class InspectionRecordForm(BaseModelForm):
    """
    Tick an inspection as done: who did it (workers), when, a note, and - checked in clean() - at least one
    evidence file. The files themselves are uploaded as <input name="attachments" multiple> and handled by the view,
    which passes them in as `new_files` (and how many existing files are kept as `kept_attachments`).
    """

    class Meta:
        model = InspectionRecord
        fields = ["is_done", "done_date", "performed_by", "note"]
        widgets = {"done_date": date_widget(), "note": forms.Textarea(attrs={"rows": 3}),
                   "performed_by": forms.SelectMultiple(attrs={"size": 7})}

    def __init__(self, *args, new_files=(), kept_attachments=0, **kwargs):
        super().__init__(*args, **kwargs)
        self._new_files, self._kept = list(new_files), kept_attachments
        workers = Q(status=RadiationWorker.Status.ACTIVE)
        if self.instance.pk:
            workers |= Q(inspections_done=self.instance)
        self.fields["performed_by"].queryset = RadiationWorker.objects.filter(workers).distinct().order_by("full_name")
        self.fields["done_date"].help_text = _("Leave empty to use today's date.")

    def clean(self):
        data = super().clean()
        for f in self._new_files:
            try:
                validate_attachment(f)
            except forms.ValidationError as e:
                raise forms.ValidationError([f"{f.name}: {m}" for m in e.messages])
        if data.get("is_done"):
            if not data.get("performed_by"):
                self.add_error("performed_by", _("Select who did the inspection."))
            if conf.INSPECTION_REQUIRE_ATTACHMENT and not (self._new_files or self._kept):
                raise forms.ValidationError(
                    _("Attach at least one evidence file (photo, filled form ...) to show the inspection was done."))
        return data


# ============================================================ calibration assessment (scoring)
class CalibrationAssessmentForm(BaseModelForm):
    apply_now = forms.BooleanField(
        required=False, label=_("Apply the recommended interval to the equipment now"),
        help_text=_("Changes the equipment's calibration period and recalculates its due date."))

    class Meta:
        model = CalibrationAssessment
        fields = ["assessment_date", "assessed_by", "device_type", "has_maker_recommendation", "maker_recommendation",
                  "accuracy", "environment", "importance", "wear", "cost", "notes"]
        widgets = {"assessment_date": date_widget(), "notes": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        workers = Q(status=RadiationWorker.Status.ACTIVE)
        if self.instance.pk and self.instance.assessed_by_id:
            workers |= Q(pk=self.instance.assessed_by_id)
        self.fields["assessed_by"].queryset = RadiationWorker.objects.filter(workers).order_by("full_name")
        self.fields["maker_recommendation"].required = False

    def clean(self):
        data = super().clean()
        if data.get("has_maker_recommendation") and not data.get("maker_recommendation"):
            self.add_error("maker_recommendation", _("Select the manufacturer's recommendation."))
        if not data.get("has_maker_recommendation"):
            data["maker_recommendation"] = ""
        return data


# ============================================================ CSV / Excel import
class ImportForm(forms.Form):
    file = forms.FileField(
        label=_("File (.xlsx or .csv)"),
        validators=[FileExtensionValidator(["xlsx", "xlsm", "csv", "txt"])])
    dry_run = forms.BooleanField(
        required=False, initial=True, label=_("Preview only — check the file without saving anything"))
    strict = forms.BooleanField(
        required=False, label=_("All or nothing — save nothing if any row has an error"))
    create_missing = forms.BooleanField(
        required=False, initial=True, label=_("Create missing workers / environmental points / operation types"))
    apply_all = forms.BooleanField(
        required=False, label=_("If a device name/code matches several devices, apply the assessment to all of them"))
    plan_year = forms.IntegerField(
        required=False, label=_("Plan year (Jalali) for the done-marks"),
        help_text=_("Leave empty to use the year found in the file."))

    def __init__(self, *args, kind="equipment", **kwargs):
        super().__init__(*args, **kwargs)
        if kind not in ("tld", "online_doses"):
            del self.fields["create_missing"]
        if kind != "assessments":
            del self.fields["apply_all"]
        if kind != "inspection":
            del self.fields["plan_year"]
        elif not self.is_bound:
            self.fields["plan_year"].initial = ju.jalali_today()[0]
        self.fields["file"].widget.attrs["accept"] = ".xlsx,.xlsm,.csv,.txt"
        for name in ("dry_run", "strict", "create_missing", "apply_all"):
            if name in self.fields:
                self.fields[name].widget.attrs["class"] = "form-check-input"
        for name in ("file", "plan_year"):
            if name in self.fields:
                self.fields[name].widget.attrs["class"] = "form-control"
