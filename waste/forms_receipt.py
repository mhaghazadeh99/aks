from django import forms
from django.contrib.auth import get_user_model
from django.forms import BaseInlineFormSet, inlineformset_factory
from django.utils.translation import gettext_lazy as _

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Column, Field, Layout, Row

from .models import MaterialType, WasteType
from .models_receipt import WasteReceipt, WasteReceiptLine


# =====================================================================
# Same helpers/pattern as receive_source.forms
# =====================================================================

def _bootstrap(fields):
    for field in fields.values():
        existing = field.widget.attrs.get("class", "")
        if "form-control" not in existing and "form-select" not in existing:
            css = "form-select" if isinstance(field.widget, forms.Select) else "form-control"
            field.widget.attrs["class"] = f"{existing} {css}".strip()


def _datepicker():
    """Your Jalali datepicker: a text input with the .datepicker class."""
    return forms.DateInput(attrs={"type": "text", "class": "form-control datepicker", "autocomplete": "off"})


def _star_required(fields):
    for field in fields.values():
        if field.required:
            field.label = f"{field.label} *"


class BootstrapRowMixin:
    """Compact Bootstrap look for fields rendered one-per-cell in the lines table."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            cls = f.widget.attrs.get("class", "")
            size = "form-select form-select-sm" if isinstance(f.widget, forms.Select) else "form-control form-control-sm"
            f.widget.attrs["class"] = f"{cls} {size}".strip()


# =====================================================================
# STEP 1 (user 1) - letter + facilities + responsible person
# =====================================================================

class ReceiptForm(forms.ModelForm):

    class Meta:
        model = WasteReceipt
        fields = ["waste_type", "letter_number", "letter_date", "letter_file", "origin_facility",
                  "facility", "laboratory", "received_by", "description"]
        widgets = {
            "letter_date": _datepicker(),
            "description": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _star_required(self.fields)

        # responsible person: pick by the full name / position from their profile
        users = get_user_model().objects.filter(is_active=True).select_related("profile")
        self.fields["received_by"].queryset = users.order_by("profile__full_name", "username")
        self.fields["received_by"].label_from_instance = self._user_label
        _bootstrap(self.fields)

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Row(
                Column(Field("waste_type"), css_class="col-md-3"),
                Column(Field("letter_number"), css_class="col-md-3"),
                Column(Field("letter_date"), css_class="col-md-3"),
                Column(Field("letter_file"), css_class="col-md-3"),
                css_class="g-3",
            ),
            Row(
                Column(Field("origin_facility"), css_class="col-md-4"),
                Column(Field("facility"), css_class="col-md-4"),
                Column(Field("received_by"), css_class="col-md-4"),
                css_class="g-3",
            ),
            Row(
                Column(Field("laboratory"), css_class="col-md-4"),
                Column(Field("description"), css_class="col-md-8"),
                css_class="g-3",
            ),
        )


    @staticmethod
    def _user_label(u):
        profile = getattr(u, "profile", None)
        name = (profile.full_name if profile and profile.full_name else None) or u.get_username()
        return f"{name} - {profile.position}" if profile and profile.position else name


class StartLineForm(BootstrapRowMixin, forms.ModelForm):
    class Meta:
        model = WasteReceiptLine
        fields = ["material", "package_type", "package_count"]


class BaseStartLineFormSet(BaseInlineFormSet):
    def add_fields(self, form, index):
        super().add_fields(form, index)
        if "DELETE" in form.fields:
            form.fields["DELETE"].widget.attrs["class"] = "form-check-input"

    def clean(self):
        super().clean()
        seen = set()
        for f in self.forms:
            if not f.cleaned_data or f.cleaned_data.get("DELETE"):
                continue
            key = (f.cleaned_data["material"], f.cleaned_data["package_type"])
            if key in seen:
                raise forms.ValidationError(_("The same material + package type is listed twice - increase the package count instead."))
            seen.add(key)
            liquid = self.instance.waste_type == WasteType.LIQUID
            if liquid != (key[0] == MaterialType.LIQUID):
                raise forms.ValidationError(_("Liquid receipts take liquid material only; solid receipts take solid materials only."))
        if not seen:
            raise forms.ValidationError(_("Add at least one material/package line."))


StartLineFormSet = inlineformset_factory(
    WasteReceipt, WasteReceiptLine, form=StartLineForm, formset=BaseStartLineFormSet,
    extra=3, can_delete=True)


# =====================================================================
# STEP 2 (user 2) - minutes data
# =====================================================================

class MinutesForm(forms.ModelForm):

    class Meta:
        model = WasteReceipt
        fields = ["minutes_number", "minutes_date", "delivery_date", "laboratory", "nuclides",
                  "waste_origin_place", "cabin_dose_uSv", "container_dose_uSv",
                  "deliverer_name", "deliverer_position", "description"]
        widgets = {
            "minutes_date": _datepicker(),
            "delivery_date": _datepicker(),
            # many nuclides: hold Ctrl/Cmd to pick several (add your select2 class here if you use it)
            "nuclides": forms.SelectMultiple(attrs={"class": "form-select", "size": 6}),
            "description": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("delivery_date", "deliverer_name", "waste_origin_place"):
            self.fields[name].required = False      # enforced in clean() with a clearer message
        # nuclides come from the reference app, sorted by name
        self.fields["nuclides"].queryset = self.fields["nuclides"].queryset.order_by("name")
        self.fields["nuclides"].help_text = _("Hold Ctrl (Cmd on Mac) to select more than one.")
        _bootstrap(self.fields)

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Row(
                Column(Field("minutes_number"), css_class="col-md-3"),
                Column(Field("minutes_date"), css_class="col-md-3"),
                Column(Field("delivery_date"), css_class="col-md-3"),
                Column(Field("laboratory"), css_class="col-md-3"),
                css_class="g-3",
            ),
            Row(
                Column(Field("nuclides"), css_class="col-md-6"),
                Column(Field("waste_origin_place"), css_class="col-md-6"),
                css_class="g-3",
            ),
            Row(
                Column(Field("cabin_dose_uSv"), css_class="col-md-3"),
                Column(Field("container_dose_uSv"), css_class="col-md-3"),
                Column(Field("deliverer_name"), css_class="col-md-3"),
                Column(Field("deliverer_position"), css_class="col-md-3"),
                css_class="g-3",
            ),
            Row(
                Column(Field("description"), css_class="col-12"),
                css_class="g-3",
            ),
        )

    def clean(self):
        c = super().clean()
        for k in ("delivery_date", "deliverer_name", "waste_origin_place", "nuclides"):
            if not c.get(k):
                self.add_error(k, _("Required to print the minutes."))
        return c


class SolidMinutesLineForm(BootstrapRowMixin, forms.ModelForm):
    class Meta:
        model = WasteReceiptLine
        fields = ["package_count", "mass_kg", "volume_m3", "surface_dose_uSv", "half_life"]

    def clean(self):
        c = super().clean()
        # catch it now: finalize runs AFTER the signed copy exists, too late to fix a missing number
        if c.get("mass_kg") is None and c.get("volume_m3") is None:
            raise forms.ValidationError(_("Enter the mass or the volume for every line."))
        return c


class LiquidMinutesLineForm(BootstrapRowMixin, forms.ModelForm):
    class Meta:
        model = WasteReceiptLine
        fields = ["volume_m3", "alpha_bq_l", "beta_bq_l", "gamma_bq_l", "ph", "density",
                  "hardness", "half_life_class", "surface_dose_uSv"]

    def clean(self):
        c = super().clean()
        if not c.get("volume_m3"):
            self.add_error("volume_m3", _("Required."))
        if not c.get("half_life_class"):
            self.add_error("half_life_class", _("Required (it picks the row on the form)."))
        return c


def minutes_line_formset(waste_type):
    form = LiquidMinutesLineForm if waste_type == WasteType.LIQUID else SolidMinutesLineForm
    return inlineformset_factory(WasteReceipt, WasteReceiptLine, form=form, extra=0, can_delete=False)


# =====================================================================
# STEP 3 - signed copy
# =====================================================================

class SignedMinutesForm(forms.ModelForm):
    class Meta:
        model = WasteReceipt
        fields = ["signed_minutes_file"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["signed_minutes_file"].required = True
        _bootstrap(self.fields)
        self.helper = FormHelper()
        self.helper.form_tag = False

    def clean_signed_minutes_file(self):
        f = self.cleaned_data.get("signed_minutes_file")
        if not f:
            raise forms.ValidationError(_("Choose the scanned, signed minutes."))
        return f