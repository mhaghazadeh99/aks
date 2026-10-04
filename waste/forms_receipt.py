from django import forms
from django.utils.translation import gettext_lazy as _
from django.forms import inlineformset_factory, BaseInlineFormSet

from .models import MaterialType, PackageType, WasteType
from .models_receipt import WasteReceipt, WasteReceiptLine

class BootstrapRowMixin:
    """Bootstrap look for fields rendered one-per-cell in the lines table
    (the header forms are rendered with crispy instead)."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            cls = f.widget.attrs.get("class", "")
            f.widget.attrs["class"] = f"{cls} form-control form-control-sm".strip()


SOLID_MATERIALS = [(v, l) for v, l in MaterialType.choices if v != MaterialType.LIQUID]


# ------------------------------------------------------------ step 1 (user 1)
class ReceiptForm(forms.ModelForm):
    class Meta:
        model = WasteReceipt
        fields = ["waste_type", "letter_number", "letter_date", "letter_file", "origin_facility",
                  "facility", "laboratory", "received_by", "description"]
        widgets = {"letter_date": forms.DateInput(attrs={"type": "date"}),
                   "description": forms.Textarea(attrs={"rows": 3})}


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


# ------------------------------------------------------------ step 2 (user 2)
class MinutesForm(forms.ModelForm):
    class Meta:
        model = WasteReceipt
        fields = ["minutes_number", "minutes_date", "delivery_date", "laboratory", "radionuclides",
                  "waste_origin_place", "cabin_dose_uSv", "container_dose_uSv",
                  "deliverer_name", "deliverer_position", "receiver_position", "description"]
        widgets = {"minutes_date": forms.DateInput(attrs={"type": "date"}),
                   "delivery_date": forms.DateInput(attrs={"type": "date"}),
                   "description": forms.Textarea(attrs={"rows": 3})}

    def clean(self):
        c = super().clean()
        for k in ("delivery_date", "deliverer_name", "waste_origin_place"):
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


class SignedMinutesForm(forms.ModelForm):
    class Meta:
        model = WasteReceipt
        fields = ["signed_minutes_file"]

    def clean_signed_minutes_file(self):
        f = self.cleaned_data.get("signed_minutes_file")
        if not f:
            raise forms.ValidationError(_("Choose the scanned, signed minutes."))
        return f