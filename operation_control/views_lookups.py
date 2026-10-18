"""One screen to maintain every admin pick-list: operation types, environmental TLD points, equipment applications."""
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy as _l

from .forms import _bootstrap
from .models import EnvironmentalPoint, EquipmentApplication, OperationType

# kind -> (model, title, help, extra form field, reverse relation used for the usage count, back url name)
LOOKUPS = {
    "operation-types": (OperationType, _l("Operation types"),
                        _l("These are the choices shown when recording operation doses. Deactivate instead of deleting to keep old records."),
                        None, "sessions", "oc_dosimetry_home"),
    "env-points": (EnvironmentalPoint, _l("Environmental TLD points"),
                   _l("The fixed places where environmental TLDs are placed. They are used by TLD report readings."),
                   "location", "tld_readings", "oc_dosimetry_home"),
    "applications": (EquipmentApplication, _l("Equipment applications"),
                     _l("Tick “personal dosimeter” for the application used by online dosimeters: those devices appear in operation dose records."),
                     "is_personal_dosimetry", "equipment", "oc_equipment_list"),
}


@login_required
def lookup_list(request, kind):
    model, title, help_text, extra, usage, back = LOOKUPS[kind]
    fields = ["name"] + ([extra] if extra else [])
    Form = forms.modelform_factory(model, fields=fields)
    form = Form(request.POST or None)
    _bootstrap(form.fields)
    if request.method == "POST":
        if "toggle" in request.POST:
            obj = get_object_or_404(model, pk=request.POST["toggle"])
            obj.is_active = not obj.is_active
            obj.save(update_fields=["is_active"])
            return redirect(request.path)
        if form.is_valid():
            form.save()
            messages.success(request, _("Saved."))
            return redirect(request.path)
    rows = model.objects.annotate(n=Count(usage, distinct=True))
    return render(request, "operation_control/lookup_list.html", {
        "form": form, "rows": rows, "title": title, "help_text": help_text, "extra": extra,
        "extra_label": model._meta.get_field(extra).verbose_name if extra else "", "back": back})
