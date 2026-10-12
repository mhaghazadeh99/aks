"""
laboratory/services/csv_io.py -- CSV export and import for lab records.

Three datasets, each exportable and importable (an export can be edited in Excel and imported back):

  samples    one row per sample
  gamma      one row per NUCLIDE of a gamma (HPGe) analysis; the analysis-level columns
             (analysis_date, counting_duration_seconds, result_unit) repeat on every row of a sample
  alphabeta  one row per sample: total alpha/beta with their +-2s uncertainties, optional run_id

Rules
  * UTF-8 with BOM on export (Excel shows Persian correctly). Import accepts UTF-8, UTF-8 with BOM
    or Windows-1256, and a comma, semicolon or tab delimiter.
  * Dates are exported as Jalali (1405/07/18) with a Gregorian column next to them; import accepts
    either calendar, Latin or Persian digits.
  * Values are imported exactly as typed -- no unit conversion, no rounding. A number with more
    decimals than the field stores is an error, not silently rounded.
  * A blank cell means "not given": on create it is simply empty, on update the stored value is kept.
  * Import never touches an analysis that is already in the signature chain.
  * Cells that would be read as formulas by Excel (start with = + - @) are exported with a leading
    apostrophe, and the import removes it again.

Model imports are inside the functions so the pure helpers (parsing, header handling) can be tested
without Django.
"""

import csv
import datetime
import io
import re
from decimal import Decimal, InvalidOperation

from .jalali import as_date, format_jalali, latin_digits, parse_date

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_ROWS = 20000

# ---------------------------------------------------------------------
# Column definitions
# ---------------------------------------------------------------------

DATASETS = {
    "samples": {
        "label": "Samples",
        "columns": [
            "sample_id", "barcode", "waste_batch", "analysis_type", "applicant_name", "sample_type",
            "description", "sample_stage", "sampling_date", "sampling_location",
            "sample_mass_kg", "sample_volume_ml", "urgent", "remarks",
        ],
        "export_only": ["sampling_date_gregorian", "status", "collected_by", "sent_to_lab_date", "lab_received_date"],
        "required": ["sample_id", "analysis_type", "sample_stage", "sampling_date"],
        "example": {
            "sample_id": "S-1405-001", "barcode": "S-1405-001", "waste_batch": "", "analysis_type": "HPGE",
            "applicant_name": "Example Co", "sample_type": "Soil",
            "description": "Soil near building 3", "sample_stage": "RECEIPT",
            "sampling_date": "1405/07/18", "sampling_location": "Site A",
            "sample_mass_kg": "1.5", "sample_volume_ml": "", "urgent": "no", "remarks": "",
        },
    },
    "gamma": {
        "label": "Gamma (HPGe) results",
        "columns": [
            "sample_id", "analysis_date", "counting_duration_seconds", "result_unit",
            "nuclide", "radiation_type", "activity", "uncertainty", "mda",
        ],
        "export_only": ["analysis_date_gregorian", "approved"],
        "required": ["sample_id", "nuclide", "activity"],
        "example": {
            "sample_id": "S-1405-001", "analysis_date": "1405/07/20", "counting_duration_seconds": "36000",
            "result_unit": "KG", "nuclide": "Cs-137", "radiation_type": "GAMMA",
            "activity": "12.4", "uncertainty": "1.1", "mda": "0.8",
        },
    },
    "alphabeta": {
        "label": "Alpha/Beta results",
        "columns": [
            "sample_id", "run_id", "analysis_date", "result_unit",
            "total_alpha", "alpha_uncertainty", "total_beta", "beta_uncertainty",
        ],
        "export_only": ["analysis_date_gregorian", "approved"],
        "required": ["sample_id"],
        "example": {
            "sample_id": "S-1405-002", "run_id": "", "analysis_date": "1405/07/20", "result_unit": "KG",
            "total_alpha": "100", "alpha_uncertainty": "5", "total_beta": "500", "beta_uncertainty": "5.5",
        },
    },
}

ANALYSIS_TYPE_ALIASES = {
    "gamma": "HPGE", "hpge": "HPGE", "hpg": "HPGE",
    "alpha/beta": "ALPHABETA", "alpha_beta": "ALPHABETA", "alpha-beta": "ALPHABETA",
    "alpha beta": "ALPHABETA", "alpha": "ALPHABETA", "beta": "ALPHABETA", "gross alpha/beta": "ALPHABETA",
}
TRUE_WORDS = {"1", "true", "yes", "y", "t", "urgent", "\u0628\u0644\u0647", "\u0622\u0631\u0647", "\u0627\u0631\u0647"}
FALSE_WORDS = {"", "0", "false", "no", "n", "f", "\u062e\u06cc\u0631"}

FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


# ---------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------

class CsvFormatError(ValueError):
    """The file itself can't be used (encoding, missing columns, too big)."""


class RowErrors(Exception):
    """Raised inside one row's processing; carries every problem found in that row."""
    def __init__(self, errors):
        super().__init__("; ".join(f"{c}: {m}" for c, m in errors))
        self.errors = errors


class ImportResult:
    def __init__(self):
        self.created = 0
        self.updated = 0
        self.skipped = 0
        self.errors = []        # (line, column, message)
        self.warnings = []      # (line, column, message)
        self.notes = []         # free text, e.g. "34 nuclide rows"
        self.committed = False

    def err(self, line, column, message):
        self.errors.append((line, column, message))

    def warn(self, line, column, message):
        self.warnings.append((line, column, message))

    @property
    def error_rows(self):
        return len({e[0] for e in self.errors})


def csv_escape(value):
    """Text for a CSV cell. Strings Excel could read as formulas get a leading apostrophe."""
    if value is None:
        return ""
    s = str(value)
    if s and s[0] in FORMULA_START:
        return "'" + s
    return s


def csv_unescape(value):
    s = (value or "").strip()
    if len(s) > 1 and s[0] == "'" and s[1] in FORMULA_START:
        s = s[1:]
    return s


def fmt_number(value):
    """Decimal as typed, minus the trailing zeros of the fixed 5-place DecimalField."""
    if value is None or value == "":
        return ""
    s = format(Decimal(str(value)), "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s


def fmt_date_jalali(value):
    return format_jalali(value, persian_digits=False)


def fmt_date_gregorian(value):
    d = as_date(value)
    return d.isoformat() if d else ""


def decode_upload(data):
    if len(data) > MAX_UPLOAD_BYTES:
        raise CsvFormatError(f"The file is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")
    for encoding in ("utf-8-sig", "cp1256"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise CsvFormatError("Could not read the file. Save it as 'CSV UTF-8' from Excel and try again.")


def _normalize_header(name):
    return re.sub(r"[\s\-]+", "_", (name or "").replace("\ufeff", "").strip().lower())


def read_csv(data, dataset):
    """bytes -> (rows, warnings). rows = [(line_number, {column: cleaned_text})].
    Raises CsvFormatError for an unusable file."""
    spec = DATASETS[dataset]
    text = decode_upload(data)
    first_line = text.split("\n", 1)[0]
    delimiter = max((",", ";", "\t"), key=first_line.count)
    if first_line.count(delimiter) == 0:
        raise CsvFormatError("The first line has no column separators -- is this a CSV file?")

    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    try:
        header = [_normalize_header(h) for h in next(reader)]
    except StopIteration:
        raise CsvFormatError("The file is empty.")

    known = set(spec["columns"]) | set(spec["export_only"])
    warnings = []
    missing = [c for c in spec["required"] if c not in header]
    if missing:
        raise CsvFormatError("Missing required column(s): " + ", ".join(missing))
    duplicated = sorted({h for h in header if h and header.count(h) > 1})
    if duplicated:
        raise CsvFormatError("Column(s) appear twice: " + ", ".join(duplicated))
    for h in header:
        if h and h not in known:
            warnings.append((1, h, "unknown column, ignored"))

    rows = []
    for line_no, raw in enumerate(reader, start=2):
        if not any((c or "").strip() for c in raw):
            continue
        if len(rows) >= MAX_ROWS:
            raise CsvFormatError(f"More than {MAX_ROWS} rows -- split the file.")
        raw = list(raw) + [""] * (len(header) - len(raw))
        rows.append((line_no, {h: csv_unescape(v) for h, v in zip(header, raw) if h in spec["columns"]}))
    return rows, warnings


def parse_decimal(value, places):
    v = latin_digits(value).strip().replace(" ", "")
    if "," in v:
        raise ValueError("use '.' as the decimal point and no thousands separators")
    try:
        d = Decimal(v)
    except InvalidOperation:
        raise ValueError(f"'{value}' is not a number")
    if not d.is_finite():
        raise ValueError(f"'{value}' is not a number")
    if d.as_tuple().exponent < -places:
        raise ValueError(f"'{value}' has more than {places} decimal places (it would have to be rounded)")
    return d


def parse_int(value):
    v = latin_digits(value).strip()
    if not re.fullmatch(r"\d+", v):
        raise ValueError(f"'{value}' is not a whole number")
    return int(v)


def parse_bool(value):
    v = latin_digits(value or "").strip().lower()
    if v in TRUE_WORDS:
        return True
    if v in FALSE_WORDS:
        return False
    raise ValueError(f"'{value}' is not yes/no")


def match_choice(value, choices, aliases=None):
    """Accept the stored code or the English label, any case. `choices` = TextChoices.choices."""
    v = (value or "").strip().lower()
    for code, label in choices:
        if v in (code.lower(), str(label).lower()):
            return code
    if aliases and v in aliases:
        return aliases[v]
    allowed = ", ".join(code for code, _ in choices)
    raise ValueError(f"'{value}' is not one of: {allowed}")


def make_template_csv(dataset):
    spec = DATASETS[dataset]
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(spec["columns"])
    w.writerow([spec["example"].get(c, "") for c in spec["columns"]])
    return out.getvalue()


# ---------------------------------------------------------------------
# EXPORT
# ---------------------------------------------------------------------

def export_rows(dataset, request_get=None):
    """Yields (header_row, then data rows) for the dataset. `request_get` = request.GET (optional
    filters: samples -> status, search)."""
    spec = DATASETS[dataset]
    get = request_get or {}
    header = spec["columns"] + spec["export_only"]
    yield header

    if dataset == "samples":
        from django.db.models import Q
        from ..models import Sample
        qs = Sample.objects.select_related("batch", "collected_by").order_by("id")
        if get.get("status"):
            qs = qs.filter(status=get["status"])
        if get.get("search"):
            s = get["search"]
            qs = qs.filter(
                Q(sample_id__icontains=s) | Q(sample_code_barcode__icontains=s)
                | Q(description__icontains=s) | Q(batch__waste_id__icontains=s)
            )
        for s in qs.iterator():
            yield [
                csv_escape(s.sample_id), csv_escape(s.sample_code_barcode),
                csv_escape(s.batch.waste_id if s.batch else ""), s.analysis_type,
                csv_escape(s.applicant_name), csv_escape(s.sample_type), csv_escape(s.description),
                s.sample_stage, fmt_date_jalali(s.sampling_date), csv_escape(s.sampling_location),
                fmt_number(s.sample_mass_kg), fmt_number(s.sample_volume_ml),
                "yes" if s.urgent else "no", csv_escape(s.remarks),
                fmt_date_gregorian(s.sampling_date), s.status,
                csv_escape(s.collected_by.get_username() if s.collected_by else ""),
                fmt_date_jalali(s.sent_to_lab_date), fmt_date_jalali(s.lab_received_date),
            ]

    elif dataset == "gamma":
        from ..models import CounterType, NuclideActivity
        qs = (
            NuclideActivity.objects.filter(analysis__detector_type=CounterType.HPGE)
            .select_related("analysis", "analysis__sample", "radionuclide")
            .order_by("analysis__sample__sample_id", "radionuclide__name", "radiation_type")
        )
        for na in qs.iterator():
            a = na.analysis
            yield [
                csv_escape(a.sample.sample_id), fmt_date_jalali(a.analysis_date),
                a.counting_duration_seconds if a.counting_duration_seconds is not None else "",
                a.effective_result_unit, csv_escape(na.radionuclide.name), na.radiation_type,
                fmt_number(na.activity_bq), fmt_number(na.uncertainty_bq), fmt_number(na.mda_bq),
                fmt_date_gregorian(a.analysis_date), "yes" if a.approved else "no",
            ]

    elif dataset == "alphabeta":
        from ..models import Analysis, CounterType
        qs = (
            Analysis.objects.filter(detector_type=CounterType.ALPHABETA)
            .select_related("sample", "counting_run").order_by("sample__sample_id")
        )
        for a in qs.iterator():
            yield [
                csv_escape(a.sample.sample_id), csv_escape(a.counting_run.run_id if a.counting_run else ""),
                fmt_date_jalali(a.analysis_date), a.effective_result_unit,
                fmt_number(a.total_alpha), fmt_number(a.alpha_uncertainty),
                fmt_number(a.total_beta), fmt_number(a.beta_uncertainty),
                fmt_date_gregorian(a.analysis_date), "yes" if a.approved else "no",
            ]


# ---------------------------------------------------------------------
# IMPORT -- shared pieces
# ---------------------------------------------------------------------

def _analysis_locked(analysis):
    """True when the analysis (or its counting run) already has a signature chain: the report was
    generated from the current numbers, so import must not change them."""
    if analysis.approved or analysis.approvals.exists():
        return True
    run = analysis.counting_run
    return bool(run and run.approvals.exists())


class _Collector:
    """Gathers (column, message) problems for one row so every issue is reported, not just the first."""
    def __init__(self):
        self.errors = []

    def add(self, column, message):
        self.errors.append((column, message))

    def run(self, column, fn, *args):
        try:
            return fn(*args)
        except ValueError as exc:
            self.add(column, str(exc))
            return None

    def raise_if_any(self):
        if self.errors:
            raise RowErrors(self.errors)


def _validation_errors(exc, column_map):
    out = []
    for field, messages in exc.message_dict.items():
        for m in messages:
            out.append((column_map.get(field, field), m))
    return out


def _run_rows(items, handler, res):
    """Runs handler(line, row) for each item inside its own savepoint; collects RowErrors."""
    from django.db import transaction
    for line, row in items:
        try:
            with transaction.atomic():
                handler(line, row)
        except RowErrors as exc:
            for column, message in exc.errors:
                res.err(line, column, message)


# ---------------------------------------------------------------------
# IMPORT -- samples
# ---------------------------------------------------------------------

SAMPLE_FIELD_TO_COLUMN = {
    "sample_code_barcode": "barcode", "batch": "waste_batch", "sample_mass_kg": "sample_mass_kg",
}


def import_samples(rows, user, on_duplicate="skip"):
    from django.core.exceptions import ValidationError
    from django.utils import timezone
    from ..models import CounterType, Sample, SampleStage, SampleStatus
    from waste.models import WasteBatch

    res = ImportResult()
    seen = {}

    def handle(line, r):
        c = _Collector()
        sid = r.get("sample_id", "")
        if not sid:
            c.add("sample_id", "required")
            c.raise_if_any()
        if sid in seen:
            c.add("sample_id", f"appears twice in the file (first on line {seen[sid]})")
            c.raise_if_any()
        seen[sid] = line

        existing = Sample.objects.filter(sample_id=sid).first()
        if existing and on_duplicate != "update":
            res.skipped += 1
            res.warn(line, "sample_id", "already exists -- skipped")
            return
        if existing:
            analysis = getattr(existing, "analysis", None)
            if analysis and _analysis_locked(analysis):
                c.add("sample_id", "its analysis is already in the signature chain -- can't be changed by import")
                c.raise_if_any()

        values = {}
        if r.get("barcode"):
            values["sample_code_barcode"] = r["barcode"]
        for col, field in (("applicant_name", "applicant_name"), ("sample_type", "sample_type"),
                           ("description", "description"), ("sampling_location", "sampling_location"),
                           ("remarks", "remarks")):
            if r.get(col):
                values[field] = r[col]

        if r.get("waste_batch"):
            batch = WasteBatch.objects.filter(waste_id=r["waste_batch"]).first()
            if batch is None:
                c.add("waste_batch", f"no waste batch with ID '{r['waste_batch']}'")
            elif batch.status == "CONSUMED":
                c.add("waste_batch", "this batch is consumed and can't be sampled")
            else:
                values["batch"] = batch
        if r.get("analysis_type"):
            v = c.run("analysis_type", match_choice, r["analysis_type"], CounterType.choices, ANALYSIS_TYPE_ALIASES)
            if v: values["analysis_type"] = v
        if r.get("sample_stage"):
            v = c.run("sample_stage", match_choice, r["sample_stage"], SampleStage.choices)
            if v: values["sample_stage"] = v
        if r.get("sampling_date"):
            d = c.run("sampling_date", parse_date, r["sampling_date"])
            if d:
                values["sampling_date"] = timezone.make_aware(datetime.datetime.combine(d, datetime.time.min))
        for col, field, places in (("sample_mass_kg", "sample_mass_kg", 5), ("sample_volume_ml", "sample_volume_ml", 3)):
            if r.get(col):
                v = c.run(col, parse_decimal, r[col], places)
                if v is not None: values[field] = v
        if r.get("urgent"):
            v = c.run("urgent", parse_bool, r["urgent"])
            if v is not None: values["urgent"] = v

        if not existing:
            for col in ("analysis_type", "sample_stage", "sampling_date"):
                if not r.get(col):
                    c.add(col, "required")
        c.raise_if_any()

        obj = existing or Sample(sample_id=sid, status=SampleStatus.COLLECTED, collected_by=user)
        for field, value in values.items():
            setattr(obj, field, value)
        if not obj.batch_id and not obj.description:
            c.add("description", "a standalone sample (no waste batch) needs a description")
            c.raise_if_any()
        try:
            obj.full_clean(exclude=["collected_by"])
        except ValidationError as exc:
            raise RowErrors(_validation_errors(exc, SAMPLE_FIELD_TO_COLUMN))
        obj.save()
        if existing:
            res.updated += 1
        else:
            res.created += 1

    _run_rows(rows, handle, res)
    return res


# ---------------------------------------------------------------------
# IMPORT -- gamma results (one row per nuclide)
# ---------------------------------------------------------------------

def import_gamma(rows, user):
    from django.core.exceptions import ValidationError
    from ..models import (
        Analysis, CounterType, NuclideActivity, RadiationType, ResultUnit, Sample, SampleStatus,
    )
    from reference.models import Nuclides
    from .report_generator import GAMMA_DATA_ROWS

    res = ImportResult()
    groups = {}
    for line, r in rows:
        groups.setdefault(r.get("sample_id", ""), []).append((line, r))

    nuclide_rows = [0]

    def handle_group(sid, items):
        first_line = items[0][0]
        c = _Collector()
        if not sid:
            raise RowErrors([("sample_id", "required")])

        sample = Sample.objects.filter(sample_id=sid).first()
        if sample is None:
            raise RowErrors([("sample_id", f"no sample with ID '{sid}' -- import the samples first")])
        if sample.analysis_type != CounterType.HPGE:
            raise RowErrors([("sample_id", "this sample is not a Gamma (HPGE) sample")])
        analysis = getattr(sample, "analysis", None)
        if analysis and _analysis_locked(analysis):
            raise RowErrors([("sample_id", "its analysis is already in the signature chain -- can't be changed by import")])

        # analysis-level values: must agree on every row that gives them
        level = {}
        for line, r in items:
            for col, parser in (("analysis_date", parse_date), ("counting_duration_seconds", parse_int),
                                ("result_unit", None)):
                if not r.get(col):
                    continue
                if col == "result_unit":
                    v = c.run(col, match_choice, r[col], ResultUnit.choices)
                else:
                    v = c.run(col, parser, r[col])
                if v is None:
                    continue
                if col in level and level[col] != v:
                    c.add(col, f"line {line}: differs from line {first_line} -- one analysis has one {col}")
                level.setdefault(col, v)

        if not analysis and not level.get("counting_duration_seconds"):
            c.add("counting_duration_seconds", "required for a new gamma analysis")
        if len(items) > GAMMA_DATA_ROWS:
            c.add("nuclide", f"{len(items)} nuclide rows, but the Gamma report form only has {GAMMA_DATA_ROWS} rows")

        parsed = []
        seen_keys = {}
        for line, r in items:
            rc = _Collector()
            name = r.get("nuclide", "")
            nuclide = None
            if not name:
                rc.add("nuclide", "required")
            else:
                matches = list(Nuclides.objects.filter(name__iexact=name)[:2])
                if not matches:
                    rc.add("nuclide", f"unknown nuclide '{name}'")
                elif len(matches) > 1:
                    rc.add("nuclide", f"'{name}' matches more than one nuclide")
                else:
                    nuclide = matches[0]
            rtype = RadiationType.GAMMA
            if r.get("radiation_type"):
                rtype = rc.run("radiation_type", match_choice, r["radiation_type"], RadiationType.choices) or rtype
            if not r.get("activity"):
                rc.add("activity", "required")
            vals = {}
            for col, key in (("activity", "activity_bq"), ("uncertainty", "uncertainty_bq"), ("mda", "mda_bq")):
                if r.get(col):
                    v = rc.run(col, parse_decimal, r[col], 5)
                    if v is not None:
                        vals[key] = v
            if nuclide is not None:
                key = (nuclide.pk, rtype)
                if key in seen_keys:
                    rc.add("nuclide", f"'{name}' appears twice for this sample (also line {seen_keys[key]})")
                seen_keys[key] = line
            for col, msg in rc.errors:
                res.err(line, col, msg)
            if not rc.errors:
                parsed.append((line, nuclide, rtype, vals))

        for col, msg in c.errors:
            res.err(first_line, col, msg)
        if c.errors or len(parsed) != len(items):
            raise RowErrors([])          # problems already recorded; roll the sample back

        created = analysis is None
        if created:
            analysis = Analysis(sample=sample, detector_type=CounterType.HPGE, analyst=user)
        if "analysis_date" in level: analysis.analysis_date = level["analysis_date"]
        if "counting_duration_seconds" in level: analysis.counting_duration_seconds = level["counting_duration_seconds"]
        if "result_unit" in level: analysis.result_unit = level["result_unit"]
        try:
            analysis.full_clean(exclude=["sample", "analyst", "counting_run", "reviewed_by"])
        except ValidationError as exc:
            raise RowErrors(_validation_errors(exc, {}))
        analysis.save()

        written = 0
        for line, nuclide, rtype, vals in parsed:
            obj = NuclideActivity.objects.filter(analysis=analysis, radionuclide=nuclide, radiation_type=rtype).first()
            if obj is None:
                obj = NuclideActivity(analysis=analysis, radionuclide=nuclide, radiation_type=rtype)
            for k, v in vals.items():
                setattr(obj, k, v)
            try:
                obj.full_clean(exclude=["analysis"])
            except ValidationError as exc:
                for col, msg in _validation_errors(exc, {"activity_bq": "activity", "uncertainty_bq": "uncertainty", "mda_bq": "mda"}):
                    res.err(line, col, msg)
                raise RowErrors([])
            obj.save()
            written += 1

        if sample.status != SampleStatus.COMPLETED:
            sample.status = SampleStatus.COMPLETED
            sample.save(update_fields=["status"])
        nuclide_rows[0] += written
        if created:
            res.created += 1
        else:
            res.updated += 1

    from django.db import transaction
    for sid, items in groups.items():
        try:
            with transaction.atomic():
                handle_group(sid, items)
        except RowErrors as exc:
            for column, message in exc.errors:
                res.err(items[0][0], column, message)

    res.notes.append(f"{nuclide_rows[0]} nuclide row(s) written")
    return res


# ---------------------------------------------------------------------
# IMPORT -- alpha/beta results (one row per sample)
# ---------------------------------------------------------------------

def import_alphabeta(rows, user):
    from django.core.exceptions import ValidationError
    from ..models import (
        AlphaBetaCountingRun, Analysis, CounterType, MAX_SAMPLES_PER_COUNTING_RUN, ResultUnit,
        Sample, SampleStatus,
    )

    res = ImportResult()
    seen = {}

    def handle(line, r):
        c = _Collector()
        sid = r.get("sample_id", "")
        if not sid:
            raise RowErrors([("sample_id", "required")])
        if sid in seen:
            raise RowErrors([("sample_id", f"appears twice in the file (first on line {seen[sid]})")])
        seen[sid] = line

        sample = Sample.objects.filter(sample_id=sid).first()
        if sample is None:
            raise RowErrors([("sample_id", f"no sample with ID '{sid}' -- import the samples first")])
        if sample.analysis_type != CounterType.ALPHABETA:
            raise RowErrors([("sample_id", "this sample is not an Alpha/Beta sample")])
        analysis = getattr(sample, "analysis", None)
        if analysis and _analysis_locked(analysis):
            raise RowErrors([("sample_id", "its analysis (or its counting run) is already in the signature chain -- can't be changed by import")])

        values = {}
        for col, field in (("total_alpha", "total_alpha"), ("alpha_uncertainty", "alpha_uncertainty"),
                           ("total_beta", "total_beta"), ("beta_uncertainty", "beta_uncertainty")):
            if r.get(col):
                v = c.run(col, parse_decimal, r[col], 5)
                if v is not None: values[field] = v
        if r.get("analysis_date"):
            d = c.run("analysis_date", parse_date, r["analysis_date"])
            if d: values["analysis_date"] = d
        unit = None
        if r.get("result_unit"):
            unit = c.run("result_unit", match_choice, r["result_unit"], ResultUnit.choices)

        run = None
        if r.get("run_id"):
            run = AlphaBetaCountingRun.objects.filter(run_id=r["run_id"]).first()
            if run is None:
                c.add("run_id", f"no counting run '{r['run_id']}'")
            elif run.approvals.exists():
                c.add("run_id", "this run is already in the signature chain")
            elif (not analysis or analysis.counting_run_id != run.pk) and run.sample_count >= MAX_SAMPLES_PER_COUNTING_RUN:
                c.add("run_id", f"this run already has {MAX_SAMPLES_PER_COUNTING_RUN} samples")

        for total, unc in (("total_alpha", "alpha_uncertainty"), ("total_beta", "beta_uncertainty")):
            if total in values and unc not in values and (analysis is None or getattr(analysis, unc) is None):
                res.warn(line, unc, "blank -- the report will print \u00b1 0")
        if not analysis and "total_alpha" not in values and "total_beta" not in values:
            c.add("total_alpha", "give total_alpha and/or total_beta")
        c.raise_if_any()

        created = analysis is None
        if created:
            analysis = Analysis(sample=sample, detector_type=CounterType.ALPHABETA, analyst=user)
        for field, value in values.items():
            setattr(analysis, field, value)
        if run is not None:
            analysis.counting_run = run
        if unit is not None:
            if analysis.counting_run_id:
                res.warn(line, "result_unit", "ignored: analyses in a run use the run's unit")
            else:
                analysis.result_unit = unit
        try:
            analysis.full_clean(exclude=["sample", "analyst", "counting_run", "reviewed_by"])
        except ValidationError as exc:
            raise RowErrors(_validation_errors(exc, {}))
        analysis.save()

        if sample.status != SampleStatus.COMPLETED:
            sample.status = SampleStatus.COMPLETED
            sample.save(update_fields=["status"])
        if created:
            res.created += 1
        else:
            res.updated += 1

    _run_rows(rows, handle, res)
    return res


IMPORTERS = {
    "samples": lambda rows, user, opts: import_samples(rows, user, opts.get("on_duplicate", "skip")),
    "gamma": lambda rows, user, opts: import_gamma(rows, user),
    "alphabeta": lambda rows, user, opts: import_alphabeta(rows, user),
}