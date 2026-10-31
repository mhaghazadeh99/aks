"""
Turns rows of the OLD SQL Server database (HealthPhysics: TLD + DateD + Personnels + TypeofDose) into data for
the new app. Pure Python (no Django, no database) so it can be tested anywhere; the SQL command and the CSV
import both feed it the same flat rows (see legacy_sql.TLD_QUERY).

Rules (from the old schema and your instructions)
* Dates in DateD are JALALI dates stored inside a date column (1396-09-14). A report's season comes from the
  MIDDLE of Date1..Date2 (the periods do not line up with seasons), the year is that Jalali year.
* TLD.DoseID: 3 = total effective dose, 4 = photon (gamma), 5 = hand equivalent, 10 = neutron.
  One person and one DateID usually have several rows (one per DoseID); they become ONE body reading
  (gamma + neutron) and, if present, ONE hand reading. If only the total exists it is imported as gamma
  (and remarked), so the total stays right.
* Personnel are matched to the new workers by first + last name (spacing / Arabic letters ignored), then by
  PNumber = personnel code. Personnel that match nobody are the old "case studies": environmental points.
* MeasureD is taken as mSv.
"""
import datetime
import re
from collections import defaultdict
from decimal import Decimal, InvalidOperation

from . import jalali_utils as ju

DOSE_TOTAL, DOSE_PHOTON, DOSE_HAND, DOSE_NEUTRON = 3, 4, 5, 10
KNOWN_DOSES = {DOSE_TOTAL, DOSE_PHOTON, DOSE_HAND, DOSE_NEUTRON}

_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_LETTERS = str.maketrans({"ي": "ی", "ك": "ک", "ى": "ی", "ة": "ه", "ۀ": "ه"})
_NOISE = re.compile(r"[\s\u200c\u200e\u200f\u0640\u064b-\u065f\u0670]+")      # spaces, ZWNJ, tatweel, diacritics


# ------------------------------------------------------------------ small converters
def norm_name(text):
    return _NOISE.sub("", str(text or "").translate(_LETTERS)).casefold()


def to_decimal(value):
    if value is None or str(value).strip() == "":
        return None
    try:
        return Decimal(str(value).translate(_DIGITS).strip().replace(",", "."))
    except InvalidOperation:
        raise ValueError(value)


def to_int(value):
    try:
        return int(str(value).translate(_DIGITS).strip().split(".")[0])
    except (ValueError, TypeError):
        raise ValueError(value)


def to_jalali_ymd(value):
    """
    A date as the old database stores it -> (jy, jm, jd). The value is a Jalali date written into a date column,
    so a datetime(1396, 9, 14) IS 14 Azar 1396. Real Gregorian dates (year >= 1700) are converted.
    """
    if value is None or str(value).strip() == "":
        raise ValueError("empty date")
    if isinstance(value, (datetime.datetime, datetime.date)):
        y, m, d = value.year, value.month, value.day
    else:
        found = re.match(r"^\s*(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", str(value).translate(_DIGITS))
        if not found:
            raise ValueError(value)
        y, m, d = (int(x) for x in found.groups())
    if y >= 1700:
        return ju.to_jalali(datetime.date(y, m, d))
    if not ju.parse_jalali_str(f"{y}/{m}/{d}"):
        raise ValueError(f"{y}-{m}-{d} is not a valid Jalali date")
    return y, m, d


def period_season(date1, date2):
    """-> (jalali_year, season 1-4, start, end, swapped); start/end are real dates. Season = the middle of the period."""
    g1, g2 = ju.from_jalali(*to_jalali_ymd(date1)), ju.from_jalali(*to_jalali_ymd(date2))
    swapped = g2 < g1
    if swapped:
        g1, g2 = g2, g1
    middle = g1 + datetime.timedelta(days=(g2 - g1).days // 2)
    jy, jm, _jd = ju.to_jalali(middle)
    return jy, ju.season_of_month(jm), g1, g2, swapped


# ------------------------------------------------------------------ matching personnel to workers
def build_worker_index(workers):
    """workers: iterable of (personnel_code, full_name)."""
    by_name, codes = defaultdict(list), set()
    for code, name in workers:
        by_name[norm_name(name)].append(str(code))
        codes.add(str(code))
    return {"by_name": by_name, "codes": codes}


def match_person(index, first, last, pnumber=""):
    """-> ('worker', code) | ('ambiguous', [codes]) | ('none', None)"""
    found = []
    for key in (norm_name(f"{first} {last}"), norm_name(f"{last} {first}")):
        if key:
            found += [c for c in index["by_name"].get(key, []) if c not in found]
    if len(found) == 1:
        return "worker", found[0]
    if len(found) > 1:
        return "ambiguous", found
    code = str(pnumber or "").strip()
    if code and code in index["codes"]:
        return "worker", code
    return "none", None


# ------------------------------------------------------------------ the transformation
def transform(rows, index, *, unmatched="env", tolerance=Decimal("0.0015")):
    """
    rows: dicts with the keys of legacy_sql.TLD_QUERY (lower-case) and an optional "row" number.
    Returns {"reports": {DateID: {...}}, "readings": [...], "errors", "warnings", "info", "env_names", "unmatched_people"}
    unmatched: "env" = personnel matching no worker become environmental points, "skip" = they are left out.
    """
    errors, warnings, info = [], [], []
    reports, bad_dates, persons, groups = {}, set(), {}, {}
    unknown_doses = set()

    def label(row):
        return row.get("row") or row.get("tldid") or 0

    for row in rows:
        try:
            dose_id, date_id, person_id = to_int(row.get("doseid")), to_int(row.get("dateid")), to_int(row.get("personnelid"))
        except ValueError:
            errors.append((label(row), f"DoseID / DateID / PersonnelID must be numbers (got {row.get('doseid')!r}, "
                                       f"{row.get('dateid')!r}, {row.get('personnelid')!r})"))
            continue
        if dose_id not in KNOWN_DOSES:
            if dose_id not in unknown_doses:
                unknown_doses.add(dose_id)
                warnings.append((label(row), f"DoseID {dose_id} is not one of 3 / 4 / 5 / 10 - those rows are skipped"))
            continue
        if date_id in bad_dates:
            continue
        if date_id not in reports:
            try:
                y, s, start, end, swapped = period_season(row.get("date1"), row.get("date2"))
            except (ValueError, TypeError) as e:
                bad_dates.add(date_id)
                errors.append((label(row), f"DateID {date_id}: unreadable period ({e}) - all its rows are skipped"))
                continue
            number = str(row.get("numberoftest") or "").strip()
            reports[date_id] = {"date_id": date_id, "year": y, "season": s, "report_number": number,
                                "period_start": start, "period_end": end, "lab_id": str(row.get("labid") or "").strip()}
            if swapped:
                warnings.append((label(row), f"DateID {date_id}: Date1 is after Date2 - swapped"))
        try:
            value = to_decimal(row.get("measured"))
        except ValueError:
            errors.append((label(row), f"MeasureD '{row.get('measured')}' is not a number"))
            continue
        if value is None:
            warnings.append((label(row), f"PersonnelID {person_id}, DateID {date_id}: empty MeasureD - skipped"))
            continue
        if value < 0:
            errors.append((label(row), f"Negative dose {value}"))
            continue

        if person_id not in persons:
            first, last = str(row.get("firstname") or "").strip(), str(row.get("lastname") or "").strip()
            kind, key = match_person(index, first, last, row.get("pnumber"))
            name = f"{first} {last}".strip()
            if kind == "worker":
                persons[person_id] = {"kind": "worker", "code": key, "name": name}
            elif kind == "ambiguous":
                persons[person_id] = {"kind": "skip", "name": name}
                errors.append((label(row), f"'{name}' matches several workers ({', '.join(key)}) - skipped; make the names unique"))
            elif not name:
                persons[person_id] = {"kind": "skip", "name": ""}
                errors.append((label(row), f"PersonnelID {person_id} has no name - skipped"))
            elif unmatched == "env":
                persons[person_id] = {"kind": "env", "name": name}
            else:
                persons[person_id] = {"kind": "skip", "name": name}
                warnings.append((label(row), f"'{name}' matches no worker - skipped"))
        if persons[person_id]["kind"] == "skip":
            continue

        g = groups.setdefault((date_id, person_id), {"doses": {}, "tld_ids": [], "uncertainty": [], "descriptions": [], "job": []})
        if dose_id in g["doses"]:
            warnings.append((label(row), f"PersonnelID {person_id}, DateID {date_id}, DoseID {dose_id} appears twice - the later value is used"))
        g["doses"][dose_id] = value
        for key, field in (("tld_ids", "tldid"), ("uncertainty", "uncertinty"), ("descriptions", "descriptions"), ("job", "jobtype")):
            raw = row.get(field)
            if raw is None and field == "uncertinty":
                raw = row.get("uncertainty")                  # accept the correct spelling too
            text = "" if raw is None else str(raw).strip()
            if text and text.upper() != "NULL" and text not in g[key]:
                g[key].append(text)
        g.setdefault("first_row", label(row))

    readings = []
    for (date_id, person_id), g in groups.items():
        person, d = persons[person_id], g["doses"]
        photon, neutron, total, hand = d.get(DOSE_PHOTON), d.get(DOSE_NEUTRON), d.get(DOSE_TOTAL), d.get(DOSE_HAND)
        notes = []
        gamma, neu = photon, neutron
        if photon is None and neutron is None and total is not None:
            gamma = total
            notes.append("old system: only the total effective dose was recorded (imported as gamma)")
        elif total is not None and abs((photon or 0) + (neutron or 0) - total) > tolerance:
            warnings.append((g["first_row"], f"{person['name']}, DateID {date_id}: photon + neutron = {(photon or 0) + (neutron or 0)} "
                                             f"differs from the recorded total {total}"))
        remarks = " · ".join(filter(None, [
            " / ".join(g["descriptions"]),
            f"JobType: {', '.join(g['job'])}" if g["job"] else "",
            f"uncertainty: {', '.join(g['uncertainty'])}" if g["uncertainty"] else "",
            f"old TLDID: {', '.join(g['tld_ids'])}" if g["tld_ids"] else "", *notes]))
        is_env = person["kind"] == "env"
        base = {"date_id": date_id, "kind": person["kind"], "worker_code": person.get("code"), "env_name": person["name"] if is_env else "",
                "remarks": remarks, "row": g["first_row"]}
        if gamma is not None or neu is not None:
            readings.append({**base, "position": "ENV" if is_env else "BODY", "gamma": gamma, "neutron": neu,
                             "tld_code": f"L{date_id}-{person_id}-{'E' if is_env else 'B'}"})
        if hand is not None:
            if is_env:
                warnings.append((g["first_row"], f"{person['name']} (environmental): the hand dose is ignored"))
            else:
                readings.append({**base, "position": "HAND", "gamma": hand, "neutron": None,
                                 "tld_code": f"L{date_id}-{person_id}-H"})

    seen = defaultdict(list)
    for r in readings:
        if r["kind"] == "worker":
            seen[(r["date_id"], r["worker_code"], r["position"])].append(r["tld_code"])
    for (date_id, code, position), codes in seen.items():
        if len(codes) > 1:
            warnings.append((0, f"Worker {code} has {len(codes)} {position} readings in DateID {date_id} ({', '.join(codes)}): "
                                f"the same person under several PersonnelIDs? Their doses are added together"))

    used = {r["date_id"] for r in readings}
    reports = {k: v for k, v in reports.items() if k in used}
    by_season = defaultdict(list)
    for r in reports.values():
        by_season[(r["year"], r["season"])].append(r)
    for r in sorted(reports.values(), key=lambda r: r["period_start"]):
        info.append(f"DateID {r['date_id']} ({r['report_number'] or '-'}): {ju.fmt(r['period_start'])} → {ju.fmt(r['period_end'])}"
                    f"  ⇒  {r['year']} / season {r['season']}")
    for (y, s), group in sorted(by_season.items()):
        if len(group) > 1:
            warnings.append((0, f"{y} season {s} receives {len(group)} lab reports ({', '.join(g['report_number'] or str(g['date_id']) for g in group)}): "
                                f"kept as separate reports; their doses are added together in the season totals"))
    env_names = sorted({p["name"] for p in persons.values() if p["kind"] == "env" and any(r["env_name"] == p["name"] for r in readings)})
    return {"reports": reports, "readings": readings, "errors": errors, "warnings": warnings, "info": info,
            "env_names": env_names,
            "workers_matched": len({p["code"] for p in persons.values() if p["kind"] == "worker"})}
