from django import forms
from django.forms import modelformset_factory
from django.utils.translation import gettext_lazy as _

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Field, Row, Column

from facilities.models import FacilityModel
from reference.models import Nuclides
from dashboard.models import DSRS

from .models import (
    ReceiveRequest,
    ReceiveSource,
    ReceiveItemType,
    ReceiveContract,
    ReceivePayment,
)


# =====================================================================
# SHARED FILE WIDGETS (same pattern as operations.forms)
# =====================================================================

class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):

    def clean(self, data, initial=None):
        if not data:
            return []
        files = data if isinstance(data, (list, tuple)) else [data]
        return [super(MultipleFileField, self).clean(f, initial) for f in files]


def _bootstrap(fields):
    for field in fields.values():
        existing = field.widget.attrs.get("class", "")
        if "form-control" not in existing and "form-select" not in existing:
            field.widget.attrs["class"] = f"{existing} form-control".strip()


# =====================================================================
# STEP 1 — REQUEST HEADER + FACILITY
# =====================================================================

class ReceiveRequestForm(forms.ModelForm):

    class Meta:
        model = ReceiveRequest
        fields = [
            "inquiry_letter_number",
            "inquiry_letter_date",
            "distance_to_tehran_km",
            "description",
        ]
        widgets = {
            "inquiry_letter_date": forms.DateInput(
                attrs={"type": "text", "class": "form-control datepicker", "autocomplete": "off"}
            ),
            "description": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if field.required:
                field.label = f"{field.label} *"
        _bootstrap(self.fields)

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Row(
                Column(Field("inquiry_letter_number"), css_class="col-md-3"),
                Column(Field("inquiry_letter_date"), css_class="col-md-3"),
                Column(Field("distance_to_tehran_km"), css_class="col-md-3"),
                css_class="g-3",
            ),
            Row(
                Column(Field("description"), css_class="col-md-6"),
                css_class="g-3",
            ),
        )


class ReceiveFacilityForm(forms.Form):

    facility = forms.ModelChoiceField(
        queryset=FacilityModel.objects.order_by("name"),
        label=_("Delivering Facility"),
        empty_label=_("Select Facility"),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["facility"].widget.attrs["class"] = "form-select"
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Row(Column(Field("facility"), css_class="col-md-6"), css_class="g-3"),
        )


class ReceiveAttachmentForm(forms.Form):

    inquiry = MultipleFileField(
        required=False, label=_("DSRS Inquiry Letter"),
        widget=MultipleFileInput(attrs={"class": "form-control"}),
    )
    letter = MultipleFileField(
        required=False, label=_("Letter"),
        widget=MultipleFileInput(attrs={"class": "form-control"}),
    )
    other = MultipleFileField(
        required=False, label=_("Other"),
        widget=MultipleFileInput(attrs={"class": "form-control"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Row(
                Column(Field("inquiry"), css_class="col-md-4"),
                Column(Field("letter"), css_class="col-md-4"),
                Column(Field("other"), css_class="col-md-4"),
                css_class="g-3",
            ),
        )


# =====================================================================
# STEP 2 — ADD SOURCE ROW (coordinator)
# =====================================================================

class ReceiveSourceForm(forms.Form):
    """
    The "add source/waste" picker. nuclide is required (per the printed
    form); serial_number is optional and app-only — used only for the
    license-contract inventory check.

    If the facility has ANY existing license-contract DSRS records (for
    any nuclide — not just the one being added), the creator gets a
    choice: pick the item directly from that facility's contracted
    inventory (guarantees an exact match, no fuzzy confirmation needed),
    or add it as a new/uncontracted item. Facilities with no contract
    history at all skip straight to the "new" behavior — full nuclide
    list, freeform serial number.
    """

    SOURCE_ORIGIN_NEW = "NEW"
    SOURCE_ORIGIN_INVENTORY = "INVENTORY"

    source_origin = forms.ChoiceField(
        choices=[(SOURCE_ORIGIN_NEW, _("New / Not in Inventory"))],
        initial=SOURCE_ORIGIN_NEW,
        label=_("Source Origin"),
        widget=forms.RadioSelect,
    )

    inventory_dsrs = forms.ModelChoiceField(
        queryset=DSRS.objects.none(),
        required=False,
        empty_label=_("Select from inventory"),
        label=_("Existing Contracted Source"),
    )

    item_type = forms.ChoiceField(
        choices=ReceiveItemType.choices,
        initial=ReceiveItemType.SOURCE,
        label=_("Item Type"),
    )

    nuclide = forms.ModelChoiceField(
        queryset=Nuclides.objects.order_by("name"),
        required=False,
        empty_label=_("Select Nuclide"),
        label=_("Nuclide"),
    )

    serial_number = forms.CharField(
        required=False,
        label=_("Serial Number"),
        help_text=_("Optional — not printed on the form, used only to check for an existing license contract."),
    )

    average_activity_mci = forms.DecimalField(
        required=False, label=_("Average Activity (mCi)"), min_value=0,
    )

    quantity = forms.IntegerField(
        initial=1, min_value=1, label=_("Quantity"),
    )

    def __init__(self, *args, facility=None, **kwargs):
        super().__init__(*args, **kwargs)

        self.facility = facility
        self.has_contract_inventory = False

        if facility is not None:
            contracted_qs = (
                DSRS.objects.filter(contract__isnull=False, contract__license__facility=facility)
                .select_related("Nuclide", "contract")
                .order_by("Nuclide__name", "serial_number")
            )
            if contracted_qs.exists():
                self.has_contract_inventory = True
                self.fields["inventory_dsrs"].queryset = contracted_qs
                self.fields["inventory_dsrs"].label_from_instance = lambda d: (
                    f"{d.Nuclide} — {d.serial_number or '-'} "
                    f"({d.activity_input or '?'} {d.activity_unit or ''}, contract {d.contract.contract_number or '-'})"
                )
                self.fields["source_origin"].choices = [
                    (self.SOURCE_ORIGIN_INVENTORY, _("Select From Facility's Contracted Inventory")),
                    (self.SOURCE_ORIGIN_NEW, _("New / Not in Inventory")),
                ]
                self.fields["source_origin"].initial = self.SOURCE_ORIGIN_INVENTORY

        # Nuclide is NEVER restricted by contract — a facility can have a
        # contract for some nuclides and still receive uncontracted ones.
        # The inventory picker above is the only contract-aware narrowing.

        _bootstrap(self.fields)
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Field("source_origin"),
            Field("inventory_dsrs"),
            Field("item_type"),
            Field("nuclide"),
            Field("serial_number"),
            Field("average_activity_mci"),
            Field("quantity"),
        )

    def clean(self):
        cleaned = super().clean()
        origin = cleaned.get("source_origin")

        if origin == self.SOURCE_ORIGIN_INVENTORY:

            dsrs = cleaned.get("inventory_dsrs")
            if not dsrs:
                self.add_error("inventory_dsrs", _("Please select an item from the inventory."))
                return cleaned

            # Derive everything from the chosen DSRS — freeform fields are
            # ignored/overwritten for this origin.
            cleaned["nuclide"] = dsrs.Nuclide
            cleaned["serial_number"] = dsrs.serial_number
            cleaned["average_activity_mci"] = dsrs.activity_input
            cleaned["quantity"] = 1
            cleaned.setdefault("item_type", ReceiveItemType.SOURCE)

        else:
            if not cleaned.get("nuclide"):
                self.add_error("nuclide", _("Please select a nuclide."))

        return cleaned


class LicenseMatchChoiceForm(forms.Form):
    """
    Shown when the exact serial didn't match but the facility+nuclide DID
    have license-contract candidates. The creator either picks one
    (confirming it's the same physical source) or "None of these".
    """

    NONE_VALUE = "__none__"

    choice = forms.ChoiceField(
        label=_("Does this match an existing licensed source?"),
        widget=forms.RadioSelect,
    )

    def __init__(self, *args, candidates=None, **kwargs):
        super().__init__(*args, **kwargs)
        candidates = candidates or []

        choices = [
            (str(dsrs.pk), _("%(serial)s — contract %(num)s") % {
                "serial": dsrs.serial_number,
                "num": dsrs.contract.contract_number or "-",
            })
            for dsrs in candidates
        ]
        choices.append((self.NONE_VALUE, _("None of these")))

        self.fields["choice"].choices = choices

        # Without this, {% crispy %} auto-generates a helper with
        # form_tag=True and renders its OWN <form> — nesting it inside the
        # template's <form> produces invalid HTML that breaks submission
        # (the Confirm button ends up outside any real form).
        self.helper = FormHelper()
        self.helper.form_tag = False


# =====================================================================
# STEP 3 — PER-ROW CHARACTERIZATION FIELDS (both managers, full edit)
# =====================================================================

class ReceiveSourceSpecificationForm(forms.ModelForm):

    class Meta:
        model = ReceiveSource
        fields = [
            "item_type",
            "nuclide",
            "average_activity_mci",
            "quantity",
            "half_life_display",
            "needs_shield",
            "needs_burial",
            "storage_duration",
            "sale_probability",
            "description",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False

        # Fixed at creation time by the coordinator — never editable here.
        self.fields["item_type"].disabled = True
        self.fields["nuclide"].disabled = True
        self.fields["quantity"].disabled = True
        self.fields["half_life_display"].disabled = True

        _bootstrap(self.fields)

        self.helper.layout = Layout(
            Field("item_type"),
            Field("nuclide"),
            Field("average_activity_mci"),
            Field("quantity"),
            Field("half_life_display"),
            Field("needs_shield"),
            Field("needs_burial"),
            Field("storage_duration"),
            Field("sale_probability"),
            Field("description"),
        )


ReceiveSourceSpecificationFormSet = modelformset_factory(
    ReceiveSource,
    form=ReceiveSourceSpecificationForm,
    extra=0,
    can_delete=False,  # rows are fixed once added by the coordinator
)


# =====================================================================
# STEP 4 — "REST OF THE FORM" (managers)
# =====================================================================

class ReceiveManagerInputForm(forms.ModelForm):
    """
    Everything the Operation Manager can fill EXCEPT the operation
    personnel counts (Control Manager owns those, add-only — see
    ReceiveControlAddForm below).
    """

    class Meta:
        model = ReceiveRequest
        fields = [
            "pre_operation_visit_needed",
            "visit_expert_count",
            "visit_technician_count",
            "visit_driver_count",
            "visit_mission_days",
            "visit_vehicle_type",
            "operation_mission_days",
            "operation_vehicle_type",
            "route_difficulty",
            "accommodation_days",
            "food_cost_days",
            "peripheral_equipment",
            "other_costs",
            "logistics_notes",
        ]
        widgets = {
            "logistics_notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _bootstrap(self.fields)
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Field("pre_operation_visit_needed"),
            Row(
                Column(Field("visit_expert_count"), css_class="col-md-4"),
                Column(Field("visit_technician_count"), css_class="col-md-4"),
                Column(Field("visit_driver_count"), css_class="col-md-4"),
                css_class="g-3",
            ),
            Row(
                Column(Field("visit_mission_days"), css_class="col-md-6"),
                Column(Field("visit_vehicle_type"), css_class="col-md-6"),
                css_class="g-3",
            ),
            Row(
                Column(Field("operation_mission_days"), css_class="col-md-6"),
                Column(Field("operation_vehicle_type"), css_class="col-md-6"),
                css_class="g-3",
            ),
            Field("route_difficulty"),
            Row(
                Column(Field("accommodation_days"), css_class="col-md-6"),
                Column(Field("food_cost_days"), css_class="col-md-6"),
                css_class="g-3",
            ),
            Field("peripheral_equipment"),
            Field("other_costs"),
            Field("logistics_notes"),
        )


class ReceiveControlAddForm(forms.Form):
    """
    Control Manager's ONLY editable fields on the whole request: how many
    MORE experts/technicians/drivers to add to the operation team. Pure
    increment — the view adds these to the existing counts and this form
    never shows/accepts an absolute value, so there's no way to reduce.
    """

    add_experts = forms.IntegerField(
        required=False, min_value=0, initial=0, label=_("Add Experts"),
    )
    add_technicians = forms.IntegerField(
        required=False, min_value=0, initial=0, label=_("Add Technicians"),
    )
    add_drivers = forms.IntegerField(
        required=False, min_value=0, initial=0, label=_("Add Drivers"),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _bootstrap(self.fields)
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Row(
                Column(Field("add_experts"), css_class="col-md-4"),
                Column(Field("add_technicians"), css_class="col-md-4"),
                Column(Field("add_drivers"), css_class="col-md-4"),
                css_class="g-3",
            ),
        )

    def apply(self, receive_request, save=True):
        data = self.cleaned_data
        receive_request.operation_expert_count += data.get("add_experts") or 0
        receive_request.operation_technician_count += data.get("add_technicians") or 0
        receive_request.operation_driver_count += data.get("add_drivers") or 0
        if save:
            receive_request.save(update_fields=[
                "operation_expert_count",
                "operation_technician_count",
                "operation_driver_count",
            ])
        return receive_request


# =====================================================================
# STEP 5 — CONTRACT / PAYMENT
# =====================================================================

class ReceiveContractForm(forms.ModelForm):

    contract_attachment = forms.FileField(required=False, label=_("Contract Document"))

    class Meta:
        model = ReceiveContract
        fields = [
            "contract_number",
            "contract_date",
            "contract_cost",
            "discount_requested",
            "discount_notes",
            "contract_accountable",
            "amendment_notes",
            "contract_attachment",
            "send_to_financial",
        ]
        widgets = {
            "contract_date": forms.DateInput(
                attrs={"type": "text", "class": "form-control datepicker", "autocomplete": "off"}
            ),
            "discount_notes": forms.Textarea(attrs={"rows": 2}),
            "amendment_notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _bootstrap(self.fields)
        self.helper = FormHelper()
        self.helper.form_tag = False


class ReceivePaymentForm(forms.ModelForm):

    class Meta:
        model = ReceivePayment
        fields = ["payment_done", "payment_date", "amount_paid", "notes"]
        widgets = {
            "payment_date": forms.DateInput(
                attrs={"type": "text", "class": "form-control datepicker", "autocomplete": "off"}
            ),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _bootstrap(self.fields)
        self.helper = FormHelper()
        self.helper.form_tag = False


# =====================================================================
# STEP 6 — CHARACTERIZATION (post-payment, per-DSRS)
# =====================================================================

class DSRSCharacterizationForm(forms.ModelForm):
    """Fills in the physical characterization fields already on DSRS."""

    class Meta:
        model = DSRS
        fields = [
            "Dose_rate_surface_uSv",
            "Dose_rate_1m_uSv",
            "Dose_rate_measurement_date",
            "source_state",
            "contamination_bq_cm2",
            "Source_Physical_Form",
            "Source_Manufacturer",
            "Source_Model",
            "Source_Practice",
            "Device_Manufacturer",
            "Device_Model",
            "Device_Serial_Number",
            "Container_Type",
            "Dimension",
            "Comment",
        ]
        widgets = {
            "Dose_rate_measurement_date": forms.DateInput(
                attrs={"type": "text", "class": "form-control datepicker", "autocomplete": "off"}
            ),
            "Comment": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _bootstrap(self.fields)
        self.helper = FormHelper()
        self.helper.form_tag = False


class CharacterizationDocForm(forms.Form):

    files = MultipleFileField(
        required=False, label=_("Characterization Documents / Photos"),
        widget=MultipleFileInput(attrs={"class": "form-control"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False