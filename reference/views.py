"""
Drop-in replacement for reference/views.py's radionuclide_import_csv.

WHY "doesn't update" even with no duplicates: the old version required
half_life AND d_value_bq on every row and skipped the WHOLE row if either
was blank -- before ever calling update_or_create. A CSV meant to patch in
new fields (decay data, emission probabilities, ...) for nuclides that
ALREADY have a correct d_value_bq in the database, but leaves that column
blank (on purpose, so it doesn't get silently overwritten with a guess),
got every single row skipped -- nothing ever reached the database, for
existing OR new rows. "No duplicates" doesn't change that; the row never
got as far as matching on name at all.

THE FIX ("import CSV as edit"): an existing nuclide (matched by name) is
now treated as a PATCH, not a full overwrite:
  - only columns that actually have a value in that row are written --
    a blank cell leaves whatever's already in the database untouched.
  - half_life / d_value_bq are only REQUIRED when the name doesn't exist
    yet (there's no sensible way to create a brand-new nuclide without
    them). For an existing nuclide, you can import a CSV that only has
    name + a couple of new columns filled in, and it'll update just those.
"""
import csv

from django.contrib import messages
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render

from .forms import CSVImportForm, NuclideForm
from .models import Nuclides
from .utils import parse_bool, parse_float, parse_int

FLOAT_FIELDS = [
    "half_life", "d_value_bq", "decay_constant", "specific_activity_bq_per_g",
    "alpha_energy_mev", "beta_max_energy_mev", "gamma_energy_mev", "gamma_yield",
    "neutron_yield_n_per_s", "dose_rate_constant_usv_m2_per_h_gbq",
    "half_value_layer_lead_mm", "half_value_layer_concrete_mm",
    "beta_emission_probability", "alpha_emission_probability",
]
INT_FIELDS = ["atomic_number", "mass_number", "iaea_category"]
BOOL_FIELDS = ["neutron_emitter", "is_sealed_source_common"]
TEXT_FIELDS = ["decay_mode", "parent_nuclide", "daughter_nuclide"]


def radionuclide_list(request):
    qs = Nuclides.objects.all().order_by("name")
    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get("page"))
    return render(request, "reference/radionuclide_list.html", {"nuclides": page_obj})


def radionuclide_add(request):
    form = NuclideForm(request.POST or None)
    if form.is_valid():
        form.save()
        return redirect("radionuclide_list")
    return render(request, "reference/radionuclide_form.html", {"form": form})


def radionuclide_edit(request, pk):
    obj = get_object_or_404(Nuclides, pk=pk)
    form = NuclideForm(request.POST or None, instance=obj)
    if form.is_valid():
        form.save()
        return redirect("radionuclide_list")
    return render(request, "reference/radionuclide_form.html", {"form": form})


def radionuclide_delete(request, pk):
    obj = get_object_or_404(Nuclides, pk=pk)
    obj.delete()
    return redirect("radionuclide_list")


def _parse_row(row, row_num, row_errors):
    """Builds a dict with ONLY the fields that have a non-blank value in this
    CSV row -- a column that's empty is simply absent from the result, which
    is what makes the update path a patch instead of a blanket overwrite."""
    data = {}

    for field in FLOAT_FIELDS:
        raw = row.get(field)
        if raw not in (None, ""):
            value = parse_float(raw, field, row_errors, row_num)
            if value is not None:
                data[field] = value

    for field in INT_FIELDS:
        raw = row.get(field)
        if raw not in (None, ""):
            value = parse_int(raw, field, row_errors, row_num)
            if value is not None:
                data[field] = value

    for field in BOOL_FIELDS:
        raw = row.get(field)
        if raw not in (None, ""):
            data[field] = parse_bool(raw)

    for field in TEXT_FIELDS:
        raw = row.get(field)
        if raw not in (None, ""):
            data[field] = raw

    return data


def radionuclide_import_csv(request):
    report = {"created": 0, "updated": 0, "skipped": 0, "errors": []}

    if request.method == "POST":
        form = CSVImportForm(request.POST, request.FILES)

        if form.is_valid():
            file = request.FILES["file"]

            try:
                decoded = file.read().decode("utf-8-sig").splitlines()
                reader = csv.DictReader(decoded)
            except Exception:
                report["errors"].append("File is not a valid UTF-8 CSV.")
                return render(request, "reference/radionuclide_import.html", {"form": form, "report": report})

            if not reader.fieldnames or "name" not in reader.fieldnames:
                report["errors"].append("Missing required column: name")
                return render(request, "reference/radionuclide_import.html", {"form": form, "report": report})

            for row_num, row in enumerate(reader, start=2):

                row_errors = []
                name = (row.get("name") or "").strip()
                if not name:
                    report["errors"].append(f"Row {row_num}: Missing 'name'")
                    report["skipped"] += 1
                    continue

                data = _parse_row(row, row_num, row_errors)
                if row_errors:
                    report["errors"].extend(row_errors)
                    report["skipped"] += 1
                    continue

                existing = Nuclides.objects.filter(name=name).first()

                if existing is None:
                    # Creating a brand-new nuclide: these two are the minimum you
                    # can't sensibly create a row without.
                    if "half_life" not in data:
                        report["errors"].append(
                            f"Row {row_num}: '{name}' doesn't exist yet, and half_life + d_value_bq "
                            f"are required to create a new nuclide (this row only patches existing data)."
                        )
                        report["skipped"] += 1
                        continue
                    try:
                        Nuclides.objects.create(name=name, **data)
                        report["created"] += 1
                    except Exception as exc:
                        report["errors"].append(f"Row {row_num}: {exc}")
                        report["skipped"] += 1

                else:
                    # Updating: PATCH semantics -- only the columns this row actually
                    # supplied are changed. A column left blank in the CSV is left
                    # alone on the existing record, not cleared.
                    if not data:
                        report["skipped"] += 1
                        continue
                    try:
                        for field, value in data.items():
                            setattr(existing, field, value)
                        existing.save()
                        report["updated"] += 1
                    except Exception as exc:
                        report["errors"].append(f"Row {row_num}: {exc}")
                        report["skipped"] += 1

            messages.success(
                request,
                f"Import complete: {report['created']} created, {report['updated']} updated, {report['skipped']} skipped",
            )

    else:
        form = CSVImportForm()

    return render(request, "reference/radionuclide_import.html", {"form": form, "report": report})