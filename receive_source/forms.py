from django import forms
from django.utils.translation import gettext_lazy as _

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Field, Row, Column

from facilities.models import FacilityModel
from reference.models import Nuclides
from dashboard.models import DSRS, SOURCE_STATUS

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
                .exclude(Status=SOURCE_STATUS.STORED)  # already back at IRWA — not "still out there" anymore
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
# STEP 3/4 — DOCX FILL-IN-HAND (replaces the old per-source /
# manager-input Django forms). Creator fills source characterization
# columns directly in the generated docx and signs; managers then fill
# the logistics section the same way, before their own signatures.
# None of this data is modeled in the DB — the docx is the only record.
# =====================================================================

class SpecificationUploadForm(forms.Form):
    """Used on both the creator's sign page and the manager data-entry
    page to let them replace the current SPECIFICATION attachment with
    their filled-in version."""

    file = forms.FileField(
        label=_("Upload Filled Specification (.docx)"),
        help_text=_("Download the current version below, fill it in Word, then upload it here to replace it."),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _bootstrap(self.fields)
        self.helper = FormHelper()
        self.helper.form_tag = False


# =====================================================================
# STEP 5 — CONTRACT / PAYMENT
# =====================================================================

class ReceiveContractForm(forms.ModelForm):
    """
    Per your clarification: we're NOT creating an actual contract at this
    stage — this is just where the Contract Manager declares the waste
    management cost (and whether a discount applies, which is what
    routes to CEO), along with the invoice for it. contract_number/date/
    accountable/amendment_notes still exist on the model for schema
    compatibility but are deliberately not exposed here.
    """

    class Meta:
        model = ReceiveContract
        fields = [
            "contract_cost",
            "invoice",
            "discount_requested",
            "discount_notes",
        ]
        widgets = {
            "discount_notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _bootstrap(self.fields)
        self.helper = FormHelper()
        self.helper.form_tag = False


class ReceivePaymentForm(forms.ModelForm):

    class Meta:
        model = ReceivePayment
        fields = ["payment_done", "payment_date", "amount_paid", "receipt", "notes"]
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
    """
    Fills in (or completes/corrects) both the identity fields captured
    when the source was originally added, AND the physical
    characterization fields — per requirements, this page should be
    able to add ALL the data for a source, not just dose-rate/container
    details, since some of it may not have been known/confirmed yet at
    add-source time.
    """

    class Meta:
        model = DSRS
        fields = [
            # Identity / "source add" fields — completable/correctable here
            "Nuclide",
            "serial_number",
            "activity_input",
            "activity_unit",
            "Activity_reference_date",
            # Physical characterization
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
            "Activity_reference_date": forms.DateInput(
                attrs={"type": "text", "class": "form-control datepicker", "autocomplete": "off"}
            ),
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
