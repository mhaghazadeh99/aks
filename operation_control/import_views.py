from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.utils.translation import gettext as _

from . import csv_import, import_services
from .forms import ImportForm
from .import_specs import SPECS

# TODO: swap login_required for your project's permission decorators.


@login_required
def csv_import_view(request, kind):
    spec = SPECS.get(kind)
    if spec is None:
        raise Http404
    form = ImportForm(request.POST or None, request.FILES or None, kind=kind)
    result = None
    if request.method == "POST" and form.is_valid():
        upload = form.cleaned_data["file"]
        try:
            parsed = csv_import.parse_file(kind, upload.name, upload.read())
        except csv_import.ImportFormatError as e:
            form.add_error("file", str(e))
        except Exception as e:                                    # corrupt xlsx etc.
            form.add_error("file", _("The file could not be read (%(e)s).") % {"e": e.__class__.__name__})
        else:
            year = form.cleaned_data.get("plan_year") or parsed.get("detected_year")
            result = import_services.run(
                kind, parsed, user=request.user, plan_year=year,
                dry_run=form.cleaned_data["dry_run"], strict=form.cleaned_data["strict"],
                create_missing=form.cleaned_data.get("create_missing", False),
                apply_all=form.cleaned_data.get("apply_all", False))
            if result["saved"]:
                messages.success(request, _("Import finished."))
    return render(request, "operation_control/csv_import.html", {
        "kind": kind, "spec": spec, "form": form, "result": result,
        "errors_shown": result["errors"][:300] if result else [],
        "warnings_shown": result["warnings"][:300] if result else []})


@login_required
def csv_template_view(request, kind):
    if kind not in csv_import.TEMPLATES:
        raise Http404
    response = HttpResponse(csv_import.template_csv(kind), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="import_{kind}_template.csv"'
    return response
