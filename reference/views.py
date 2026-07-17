import csv
from django.shortcuts import render, redirect, get_object_or_404
from .models import Nuclides
from .forms import NuclideForm, CSVImportForm
from django.contrib import messages

from .utils import parse_float, parse_int, parse_bool

from django.core.paginator import Paginator

def radionuclide_list(request):
    qs = Nuclides.objects.all().order_by("name")

    paginator = Paginator(qs, 25)  # 25 per page
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "reference/radionuclide_list.html", {
        "nuclides": page_obj
    })


from django.shortcuts import render, get_object_or_404, redirect
from .forms import NuclideForm

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





REQUIRED_FIELDS = ["name", "half_life", "d_value_bq"]


def radionuclide_import_csv(request):
    report = {
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "errors": []
    }

    if request.method == "POST":
        form = CSVImportForm(request.POST, request.FILES)

        if form.is_valid():
            file = request.FILES["file"]

            try:
                decoded = file.read().decode("utf-8").splitlines()
                reader = csv.DictReader(decoded)
            except Exception:
                report["errors"].append("File is not a valid UTF-8 CSV.")
                return render(request, "reference/radionuclide_import.html", {
                    "form": form,
                    "report": report
                })

            # Validate header
            missing_headers = [f for f in REQUIRED_FIELDS if f not in reader.fieldnames]
            if missing_headers:
                report["errors"].append(f"Missing required columns: {missing_headers}")
                return render(request, "reference/radionuclide_import.html", {
                    "form": form,
                    "report": report
                })

            for row_num, row in enumerate(reader, start=2):

                row_errors = []

                name = row.get("name")
                if not name:
                    report["errors"].append(f"Row {row_num}: Missing 'name'")
                    report["skipped"] += 1
                    continue

                half_life = parse_float(row.get("half_life"), "half_life", row_errors, row_num)
                d_value_bq = parse_float(row.get("d_value_bq"), "d_value_bq", row_errors, row_num)

                if half_life is None or d_value_bq is None:
                    report["errors"].extend(row_errors)
                    report["skipped"] += 1
                    continue

                data = {
                    "half_life": half_life,
                    "d_value_bq": d_value_bq,

                    "atomic_number": parse_int(row.get("atomic_number"), "atomic_number", row_errors, row_num),
                    "mass_number": parse_int(row.get("mass_number"), "mass_number", row_errors, row_num),

                    "decay_mode": row.get("decay_mode"),
                    "decay_constant": parse_float(row.get("decay_constant"), "decay_constant", row_errors, row_num),

                    "specific_activity_bq_per_g": parse_float(row.get("specific_activity_bq_per_g"), "specific_activity_bq_per_g", row_errors, row_num),

                    "alpha_energy_mev": parse_float(row.get("alpha_energy_mev"), "alpha_energy_mev", row_errors, row_num),
                    "beta_max_energy_mev": parse_float(row.get("beta_max_energy_mev"), "beta_max_energy_mev", row_errors, row_num),
                    "gamma_energy_mev": parse_float(row.get("gamma_energy_mev"), "gamma_energy_mev", row_errors, row_num),
                    "gamma_yield": parse_float(row.get("gamma_yield"), "gamma_yield", row_errors, row_num),

                    "neutron_emitter": parse_bool(row.get("neutron_emitter")),
                    "neutron_yield_n_per_s": parse_float(row.get("neutron_yield_n_per_s"), "neutron_yield_n_per_s", row_errors, row_num),

                    "dose_rate_constant_usv_m2_per_h_gbq": parse_float(row.get("dose_rate_constant_usv_m2_per_h_gbq"), "dose_rate_constant_usv_m2_per_h_gbq", row_errors, row_num),
                    "half_value_layer_lead_mm": parse_float(row.get("half_value_layer_lead_mm"), "half_value_layer_lead_mm", row_errors, row_num),
                    "half_value_layer_concrete_mm": parse_float(row.get("half_value_layer_concrete_mm"), "half_value_layer_concrete_mm", row_errors, row_num),

                    "iaea_category": parse_int(row.get("iaea_category"), "iaea_category", row_errors, row_num),

                    "parent_nuclide": row.get("parent_nuclide"),
                    "daughter_nuclide": row.get("daughter_nuclide"),

                    "is_sealed_source_common": parse_bool(row.get("is_sealed_source_common")),
                }

                if row_errors:
                    report["errors"].extend(row_errors)
                    report["skipped"] += 1
                    continue

                obj, created = Nuclides.objects.update_or_create(
                    name=name,
                    defaults=data
                )

                if created:
                    report["created"] += 1
                else:
                    report["updated"] += 1

            messages.success(
                request,
                f"Import complete: {report['created']} created, {report['updated']} updated, {report['skipped']} skipped"
            )

    else:
        form = CSVImportForm()

    return render(request, "reference/radionuclide_import.html", {
        "form": form,
        "report": report
    })