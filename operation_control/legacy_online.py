"""
Turns rows of the OLD database's OnlineDose (+ Personnels, PlaceofActivity, Center) into operations for the new app.
Pure Python (no Django / database); fed by legacy_sql.ONLINE_QUERY or by a CSV export of the same query.

Mapping (from your instructions)
  PlaceofActivity.PlaceName   -> the operation (operation type)
  Center.Name + Center.Address -> the operation's location
  OnlineDose.DateTime          -> operation date (a JALALI date kept in a date column)
  OnlineDose.DureofTime        -> operation duration (also the time in which each person received the dose)
  OnlineDose.Dose              -> the dose; the old table has no dose type and no unit, so both are parameters
                                  (default: gamma, µSv). It has no device either: imported doses have no device.
One operation = the same date + place + duration. Personnel are matched to workers like the TLD import
(first + last name, then PNumber); people who match nobody are skipped and listed (online doses belong to workers).
"""
import datetime
from collections import defaultdict

from . import jalali_utils as ju
from .legacy_tld import match_person, to_decimal, to_int, to_jalali_ymd


def parse_duration(value):
    """'01:04:00.0000000' / time / timedelta -> whole minutes. None for empty or zero."""
    if value is None or str(value).strip() == "" or str(value).strip().upper() == "NULL":
        return None
    if isinstance(value, datetime.timedelta):
        seconds = value.total_seconds()
    elif isinstance(value, (datetime.time, datetime.datetime)):
        seconds = value.hour * 3600 + value.minute * 60 + value.second
    else:
        parts = str(value).strip().split(".")[0].split(":")
        try:
            nums = [int(p) for p in parts]
        except ValueError:
            raise ValueError(value)
        if len(nums) == 2:
            nums.append(0)
        if len(nums) != 3:
            raise ValueError(value)
        seconds = nums[0] * 3600 + nums[1] * 60 + nums[2]
    minutes = int(round(seconds / 60))
    return minutes or None


def _clean(text):
    text = "" if text is None else str(text).strip()
    return "" if text.upper() == "NULL" else text


def transform(rows, index, *, unit="USV", dose_type="GAMMA"):
    errors, warnings, info = [], [], []
    persons, skipped, groups = {}, defaultdict(list), {}
    for row in rows:
        label = row.get("row") or row.get("ondoseid") or 0
        try:
            ondose_id, person_id = to_int(row.get("ondoseid")), to_int(row.get("personnelid"))
            date = ju.from_jalali(*to_jalali_ymd(row.get("datetime")))
            duration = parse_duration(row.get("dureoftime"))
            dose = to_decimal(row.get("dose"))
        except (ValueError, TypeError) as e:
            errors.append((label, f"unreadable OnDoseID / PersonnelID / DateTime / DureofTime / Dose ({e})"))
            continue
        if dose is None:
            warnings.append((label, f"OnDoseID {ondose_id}: empty Dose - skipped"))
            continue
        if dose < 0:
            errors.append((label, f"OnDoseID {ondose_id}: negative dose {dose}"))
            continue
        place_name, place_id = _clean(row.get("placename")), _clean(row.get("placeid"))
        if not place_name:
            errors.append((label, f"OnDoseID {ondose_id}: place {place_id or '?'} has no name - skipped"))
            continue

        if person_id not in persons:
            first, last = _clean(row.get("firstname")), _clean(row.get("lastname"))
            kind, key = match_person(index, first, last, row.get("pnumber"))
            name = f"{first} {last}".strip() or f"PersonnelID {person_id}"
            persons[person_id] = ({"kind": "worker", "code": key} if kind == "worker"
                                  else {"kind": "ambiguous" if kind == "ambiguous" else "none", "name": name,
                                        "codes": key if kind == "ambiguous" else []})
        person = persons[person_id]
        if person["kind"] != "worker":
            skipped[person_id].append(label)
            continue

        center, address = _clean(row.get("centername")), _clean(row.get("centeraddress"))
        location = " — ".join(x for x in (center, address) if x)[:200]
        g = groups.setdefault((date, place_id or place_name, duration), {
            "place_id": place_id, "place_name": place_name, "location": location, "date": date,
            "duration": duration, "lines": []})
        g["lines"].append({"row": label, "legacy_ref": f"OnDoseID:{ondose_id}", "worker_code": person["code"],
                           "dose": dose, "exposure": duration, "unit": unit, "dose_type": dose_type})

    for person_id, labels in skipped.items():
        p = persons[person_id]
        if p["kind"] == "ambiguous":
            errors.append((labels[0], f"'{p['name']}' matches several workers ({', '.join(p['codes'])}) - {len(labels)} dose(s) skipped"))
        else:
            errors.append((labels[0], f"'{p['name']}' matches no worker - {len(labels)} dose(s) skipped "
                                      f"(online doses belong to workers; add the worker or fix the name)"))

    sessions = sorted(groups.values(), key=lambda s: (s["date"], s["place_name"]))
    if sessions:
        lines = sum(len(s["lines"]) for s in sessions)
        info.append(f"{len(sessions)} operations with {lines} dose lines, "
                    f"{ju.fmt(sessions[0]['date'])} … {ju.fmt(sessions[-1]['date'])}")
        for name in sorted({s["place_name"] for s in sessions}):
            n = sum(1 for s in sessions if s["place_name"] == name)
            info.append(f"operation “{name}”: {n} time(s)")
    return {"sessions": sessions, "errors": errors, "warnings": warnings, "info": info,
            "workers_matched": len({p["code"] for p in persons.values() if p["kind"] == "worker"})}
