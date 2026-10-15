"""
laboratory/csv_views.py -- CSV import / export / template-download views.

Wire up in laboratory/urls.py:

    from . import csv_views
    path("csv/import/", csv_views.lab_csv_import, name="lab_csv_import"),
    path("csv/export/<str:dataset>/", csv_views.lab_csv_export, name="lab_csv_export"),
    path("csv/template/<str:dataset>/", csv_views.lab_csv_template, name="lab_csv_template"),

dataset is one of: samples, gamma, alphabeta.

Access: these views have no decorator, like the rest of laboratory/views.py -- add them to your
accounts ViewPermission the same way you did for the other lab URLs. Import writes data, so grant it
to the lab roles only.
"""

import csv

from crispy_forms.helper import FormHelper
from django import forms
from django.contrib import messages
from django.db import transaction
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .forms import _bootstrap
from .services import csv_io
from .services.jalali import format_jalali

MAX_ROWS_SHOWN = 200


class CsvImportForm(forms.Form):
    dataset = forms.ChoiceField(
        label=_("What are you importing?"),
        choices=[(key, spec["label"]) for key, spec in csv_io.DATASETS.items()],
    )
    file = forms.FileField(label=_("CSV file"))
    on_duplicate = forms.ChoiceField(
        label=_("Samples that already exist (samples file only)"), required=False, initial="skip",
        choices=[
            ("skip", _("Skip them")),
            ("update", _("Update them (blank cells keep the current value)")),
        ],
    )
    allow_no_duration = forms.BooleanField(
        label=_("Gamma file: allow analyses without a counting duration (old records)"), required=False,
    )
    allow_over_limit = forms.BooleanField(
        label=_("Gamma file: allow more than 14 nuclides per sample (old records; the Gamma report form can't print them)"),
        required=False,
    )
    allow_consumed = forms.BooleanField(
        label=_("Samples file: allow samples on consumed waste batches (old records)"), required=False,
    )
    dry_run = forms.BooleanField(
        label=_("Check only -- don't save anything"), required=False, initial=True,
    )
    only_valid = forms.BooleanField(
        label=_("If some rows have errors, still save the rows that are fine"), required=False,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _bootstrap(self.fields)
        self.helper = FormHelper()
        self.helper.form_tag = False


def _csv_response(dataset_name):
    response = HttpResponse(content_type="text/csv; charset=utf-8-sig")   # BOM -> Excel reads Persian
    stamp = format_jalali(timezone.localdate(), persian_digits=False, sep="-")
    response["Content-Disposition"] = f'attachment; filename="lab_{dataset_name}_{stamp}.csv"'
    return response


def lab_csv_export(request, dataset):
    if dataset not in csv_io.DATASETS:
        raise Http404
    response = _csv_response(dataset)
    writer = csv.writer(response)
    for row in csv_io.export_rows(dataset, request.GET):
        writer.writerow(row)
    return response


def lab_csv_template(request, dataset):
    if dataset not in csv_io.DATASETS:
        raise Http404
    response = _csv_response(f"{dataset}_template")
    response.write(csv_io.make_template_csv(dataset))
    return response


def lab_csv_import(request):
    result = None
    file_warnings = []
    form = CsvImportForm(request.POST or None, request.FILES or None)

    if request.method == "POST" and form.is_valid():
        dataset = form.cleaned_data["dataset"]
        upload = form.cleaned_data["file"]
        try:
            rows, file_warnings = csv_io.read_csv(upload.read(csv_io.MAX_UPLOAD_BYTES + 1), dataset)
        except csv_io.CsvFormatError as exc:
            form.add_error("file", str(exc))
        else:
            dry_run = form.cleaned_data["dry_run"]
            only_valid = form.cleaned_data["only_valid"]
            options = {
                "on_duplicate": form.cleaned_data["on_duplicate"] or "skip",
                "allow_no_duration": form.cleaned_data["allow_no_duration"],
                "allow_over_limit": form.cleaned_data["allow_over_limit"],
                "allow_consumed": form.cleaned_data["allow_consumed"],
            }

            with transaction.atomic():
                result = csv_io.IMPORTERS[dataset](rows, request.user, options)
                save = (not dry_run) and (only_valid or not result.errors)
                if not save:
                    transaction.set_rollback(True)
            result.committed = save

            if dry_run:
                messages.info(request, _("Check only: nothing was saved."))
            elif save:
                messages.success(request, _("Import saved."))
            else:
                messages.error(request, _("Nothing was saved because some rows have errors."))

    return render(request, "laboratory/csv_import.html", {
        "form": form,
        "result": result,
        "file_warnings": file_warnings,
        "errors": result.errors[:MAX_ROWS_SHOWN] if result else [],
        "more_errors": max(0, len(result.errors) - MAX_ROWS_SHOWN) if result else 0,
        "warnings": result.warnings[:MAX_ROWS_SHOWN] if result else [],
        "datasets": csv_io.DATASETS,
    })
