"""
waste/services/release_csv.py -- CSV export / import of RELEASES (the data behind the annual release report).

FORMAT: one row per activity line, so a release with five nuclides is five rows that share
waste_id + release_date + route. The export and the import use the same columns, so an exported
file can be edited and imported back.

    waste_id, release_date, route, category, radionuclide, activity_bq, volume_m3, mass_kg, remarks
    (the export adds facility, over_limit, performed_by, release_id -- ignored on import)

  * release_date  YYYY-MM-DD (Gregorian, like every other CSV in the app)
  * route         LIQUID / GASEOUS
  * category      NUCLIDE / GROSS_BETA / GROSS_ALPHA. Leave blank, with no activity, for a release that
                  had no measured activity: the row then only creates the release (and its volume/mass)
  * radionuclide  nuclide name -- required for NUCLIDE, must be blank for the two gross categories
  * activity_bq   Bq, >= 0
  * volume_m3 / mass_kg   of the whole release (batch size when released); taken from the first row of a
                  release that has them

IMPORT RULES (a release is a compliance record, so these are strict on purpose)
  * ALL-OR-NOTHING PER RELEASE: if any row of a release has a problem, none of that release is imported
    -- importing four of five nuclides would silently understate what was discharged.
  * The batch must already exist (matched by waste_id) and must not be consumed.
  * A batch that already has a release record is skipped, never overwritten or doubled.
  * A successful import closes the batch (status RELEASED, status date = release date), exactly as
    releasing it in the app does.
  * over_limit is NOT worked out for imported releases (it depends on the order things were discharged
    in); the report page's per-limit table still shows the true yearly picture.
"""

import csv
import datetime
import decimal

EXPORT_COLUMNS = [
    "waste_id", "release_date", "route", "category", "radionuclide", "activity_bq",
    "volume_m3", "mass_kg", "remarks", "facility", "over_limit", "performed_by", "release_id",
]


# ---------------------------------------------------------------- pure parsing (no database)

def _dec(value, field, row_num, errors):
    value = (value or "").strip()
    if not value:
        return None
    try:
        d = decimal.Decimal(value)
    except decimal.InvalidOperation:
        errors.append(f"Row {row_num}: invalid number for {field}: '{value}'")
        return None
    if d < 0:
        errors.append(f"Row {row_num}: {field} can't be negative ('{value}')")
        return None
    return d


def parse_release_rows(rows, valid_routes, valid_categories, nuclide_category="NUCLIDE"):
    """rows: iterable of dicts (csv.DictReader). Returns (groups, errors).

    groups: list of dicts, one per (waste_id, release_date, route), in file order:
        {"waste_id", "release_date", "route", "volume_m3", "mass_kg", "remarks",
         "lines": [{"category", "radionuclide", "activity_bq"}], "rows": [row numbers]}
    Any release with a bad row is left OUT of groups, and every problem is reported in errors."""
    errors = []
    order = []
    groups = {}
    bad = set()

    for row_num, row in enumerate(rows, start=2):
        row_errors = []
        waste_id = (row.get("waste_id") or "").strip()
        route = (row.get("route") or "").strip()
        date_text = (row.get("release_date") or "").strip()

        if not waste_id:
            errors.append(f"Row {row_num}: missing waste_id")
            continue
        try:
            release_date = datetime.date.fromisoformat(date_text)
        except ValueError:
            errors.append(f"Row {row_num}: invalid release_date '{date_text}' (use YYYY-MM-DD)")
            bad.add((waste_id, None, route))
            continue
        key = (waste_id, release_date, route)

        if route not in valid_routes:
            row_errors.append(f"Row {row_num}: invalid route '{route}' (expected one of: {sorted(valid_routes)})")

        category = (row.get("category") or "").strip()
        nuclide = (row.get("radionuclide") or "").strip()
        activity = _dec(row.get("activity_bq"), "activity_bq", row_num, row_errors)
        volume = _dec(row.get("volume_m3"), "volume_m3", row_num, row_errors)
        mass = _dec(row.get("mass_kg"), "mass_kg", row_num, row_errors)

        line = None
        if category:
            if category not in valid_categories:
                row_errors.append(f"Row {row_num}: invalid category '{category}' (expected one of: {sorted(valid_categories)})")
            elif category == nuclide_category and not nuclide:
                row_errors.append(f"Row {row_num}: category {category} needs a radionuclide")
            elif category != nuclide_category and nuclide:
                row_errors.append(f"Row {row_num}: category {category} must have a blank radionuclide")
            if activity is None and not row_errors:
                row_errors.append(f"Row {row_num}: category {category} needs an activity_bq")
            line = {"category": category, "radionuclide": nuclide or None, "activity_bq": activity}
        elif activity is not None or nuclide:
            row_errors.append(f"Row {row_num}: activity/radionuclide given without a category")

        group = groups.get(key)
        if group is None:
            group = groups[key] = {
                "waste_id": waste_id, "release_date": release_date, "route": route,
                "volume_m3": None, "mass_kg": None, "remarks": "", "lines": [], "rows": [],
            }
            order.append(key)
        group["rows"].append(row_num)

        if row_errors:
            errors.extend(row_errors)
            bad.add(key)
            continue

        if group["volume_m3"] is None:
            group["volume_m3"] = volume
        if group["mass_kg"] is None:
            group["mass_kg"] = mass
        if not group["remarks"]:
            group["remarks"] = (row.get("remarks") or "").strip()

        if line is not None:
            dup = (line["category"], line["radionuclide"])
            if any((l["category"], l["radionuclide"]) == dup for l in group["lines"]):
                errors.append(
                    f"Row {row_num}: {line['radionuclide'] or line['category']} appears twice in the release of "
                    f"{waste_id} on {release_date} -- it would be counted twice"
                )
                bad.add(key)
            else:
                group["lines"].append(line)

    for key in bad:
        if key in groups:
            errors.append(
                f"Release of {key[0]} on {key[1]} ({key[2] or 'no route'}) NOT imported: "
                f"fix rows {groups[key]['rows']} and import again."
            )
    return [groups[k] for k in order if k not in bad], errors


# ---------------------------------------------------------------- database side

def release_volume_mass(record):
    """A release's volume/mass: its own snapshot, else (older releases) the movement's."""
    volume = record.volume_m3
    mass = record.mass_kg
    if record.movement_id and (volume is None or mass is None):
        volume = volume if volume is not None else record.movement.volume_m3
        mass = mass if mass is not None else record.movement.mass_kg
    return volume, mass


def write_release_lines_csv(response, year=None, route=""):
    """Writes every release line (or a bare release row when it had no lines) to `response`."""
    from ..models import ReleaseRecord

    records = (
        ReleaseRecord.objects.select_related("batch", "batch__facility", "movement", "performed_by")
        .prefetch_related("lines__radionuclide").order_by("release_date", "id")
    )
    if year:
        records = records.filter(release_date__year=year)
    if route:
        records = records.filter(route=route)

    writer = csv.writer(response)
    writer.writerow(EXPORT_COLUMNS)
    for rec in records:
        volume, mass = release_volume_mass(rec)
        base = [rec.batch.waste_id, rec.release_date.isoformat(), rec.route]
        tail = [
            volume if volume is not None else "", mass if mass is not None else "", rec.remarks,
            rec.batch.facility.name if rec.batch.facility_id else "", "yes" if rec.over_limit else "",
            rec.performed_by.username if rec.performed_by_id else "", rec.pk,
        ]
        lines = list(rec.lines.all())
        if not lines:
            writer.writerow(base + ["", "", ""] + tail)
        for ln in lines:
            writer.writerow(base + [ln.category, ln.radionuclide.name if ln.radionuclide_id else "", ln.activity_bq] + tail)


def import_release_groups(groups, user):
    """Creates the releases in `groups` (from parse_release_rows). Returns a report dict."""
    import datetime as _dt

    from django.db import transaction

    from reference.models import Nuclides

    from ..models import BatchStatus, ReleaseActivityLine, ReleaseRecord, WasteBatch

    report = {"created": 0, "skipped": 0, "errors": []}

    for g in groups:
        label = f"Release of {g['waste_id']} on {g['release_date']}"
        batch = WasteBatch.objects.filter(waste_id=g["waste_id"]).first()
        if batch is None:
            report["errors"].append(f"{label}: no batch with waste_id '{g['waste_id']}'")
            report["skipped"] += 1
            continue
        if batch.status == BatchStatus.CONSUMED:
            report["errors"].append(f"{label}: the batch was consumed (merged/split/conditioned) and can't be released")
            report["skipped"] += 1
            continue
        existing = batch.release_records.first()
        if existing:
            report["errors"].append(
                f"{label}: the batch already has a release record ({existing.release_date}, {existing.get_route_display()}) -- left unchanged"
            )
            report["skipped"] += 1
            continue

        nuclides, missing = {}, []
        for ln in g["lines"]:
            if ln["radionuclide"] and ln["radionuclide"] not in nuclides:
                n = Nuclides.objects.filter(name=ln["radionuclide"]).first()
                if n is None:
                    missing.append(ln["radionuclide"])
                nuclides[ln["radionuclide"]] = n
        if missing:
            report["errors"].append(f"{label}: unknown radionuclide(s) {sorted(set(missing))} -- nothing imported for this release")
            report["skipped"] += 1
            continue

        try:
            with transaction.atomic():
                record = ReleaseRecord.objects.create(
                    batch=batch, route=g["route"], release_date=g["release_date"], performed_by=user,
                    remarks=g["remarks"] or "Imported from CSV",
                    volume_m3=g["volume_m3"], mass_kg=g["mass_kg"],
                )
                ReleaseActivityLine.objects.bulk_create([
                    ReleaseActivityLine(
                        release=record, category=ln["category"],
                        radionuclide=nuclides.get(ln["radionuclide"]) if ln["radionuclide"] else None,
                        activity_bq=ln["activity_bq"],
                    ) for ln in g["lines"]
                ])
                if batch.status != BatchStatus.RELEASED:
                    batch.status = BatchStatus.RELEASED
                    batch.status_date = g["release_date"]
                    batch.save(update_fields=["status", "status_date", "updated_at"])
            report["created"] += 1
        except Exception as exc:
            report["errors"].append(f"{label}: {exc}")
            report["skipped"] += 1

    return report