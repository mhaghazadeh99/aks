"""Saves parsed import rows. Every import runs in ONE transaction; preview mode rolls it back."""
import re
from collections import OrderedDict, defaultdict

from django.db import transaction
from django.utils.translation import gettext as _

from . import jalali_utils as ju
from .models import (
    CalibrationAssessment, CalibrationRecord, Equipment, EquipmentApplication, EnvironmentalPoint, InspectionItem,
    InspectionPlanYear, InspectionRecord, OnlineDoseRecord, OperationDoseSession, OperationType,
    RadiationWorker, TLDReading, TLDReport,
)


def _is_personal_dosimetry(name):
    return "دوزیمتری" in name and "پرسنلی" in name


# ------------------------------------------------------------------ equipment
def save_equipment(items, *, user, **_kw):
    created = updated = records = 0
    errors, warnings = [], []
    apps = {a.name.casefold(): a for a in EquipmentApplication.objects.all()}
    for it in items:
        fields, eid = it["fields"], it["equipment_id"]
        eq = Equipment.objects.filter(equipment_id=eid).first()
        if eq is None:
            if not fields.get("name"):
                errors.append((it["row"], _("%(id)s is new and needs a device name") % {"id": eid}))
                continue
            eq = Equipment(equipment_id=eid, created_by=user)
            created += 1
        else:
            updated += 1
        for k, v in fields.items():
            setattr(eq, k, v)
        if it["application"]:
            key = it["application"].casefold()
            if key not in apps:
                apps[key] = EquipmentApplication.objects.create(
                    name=it["application"], is_personal_dosimetry=_is_personal_dosimetry(it["application"]))
            eq.application = apps[key]
        eq.save()
        cal = it.get("calibration")
        if cal:
            extra = {k: v for k, v in cal.items() if k != "date"}
            rec, was_created = CalibrationRecord.objects.get_or_create(
                equipment=eq, calibration_date=cal["date"], defaults={**extra, "created_by": user})
            if was_created:
                records += 1
            else:
                changed = False
                for k, v in extra.items():
                    if v and getattr(rec, k) != v:
                        setattr(rec, k, v)
                        changed = True
                if changed:
                    rec.save()
    return [(_("Equipment created"), created), (_("Equipment updated"), updated),
            (_("Calibration records added"), records)], errors, warnings


# ------------------------------------------------------------------ workers
def save_workers(items, *, user, **_kw):
    created = updated = 0
    for it in items:
        w = RadiationWorker.objects.filter(personnel_code=it["personnel_code"]).first()
        if w is None:
            w = RadiationWorker(personnel_code=it["personnel_code"], created_by=user)
            created += 1
        else:
            updated += 1
        for k, v in it["fields"].items():
            setattr(w, k, v)
        w.save()
    return [(_("Workers created"), created), (_("Workers updated"), updated)], [], []


# ------------------------------------------------------------------ shared lookups
class _Workers:
    def __init__(self):
        self.by_code = {w.personnel_code: w for w in RadiationWorker.objects.all()}
        self.by_name = {w.full_name.casefold(): w for w in self.by_code.values()}
        self.created = 0

    def resolve(self, code, name, *, create, user):
        w = self.by_code.get(code) if code else None
        w = w or (self.by_name.get(name.casefold()) if name else None)
        if w is None and create and code and name:
            w = RadiationWorker.objects.create(personnel_code=code, full_name=name, created_by=user)
            self.by_code[code], self.by_name[name.casefold()] = w, w
            self.created += 1
        return w


# ------------------------------------------------------------------ TLD readings
def save_tld(items, *, user, create_missing, **_kw):
    errors, warnings, reports, noted = [], [], {}, set()
    workers = _Workers()
    points = {p.name.casefold(): p for p in EnvironmentalPoint.objects.all()}
    r_created = created = updated = p_created = 0
    for it in items:
        key = (it["year"], it["season"])
        report = reports.get(key)
        if report is None:
            report, was = TLDReport.objects.get_or_create(
                year=it["year"], season=it["season"],
                defaults={"report_number": it["report_number"], "received_date": it["received_date"], "created_by": user})
            r_created += was
            if not was:
                changed = False
                if it["report_number"] and not report.report_number:
                    report.report_number, changed = it["report_number"], True
                if it["received_date"] and not report.received_date:
                    report.received_date, changed = it["received_date"], True
                if changed:
                    report.save()
            reports[key] = report
        if it["report_number"] and report.report_number and it["report_number"] != report.report_number and key not in noted:
            noted.add(key)
            warnings.append((it["row"], _("%(y)s/%(s)s already has report %(a)s; rows with report %(b)s are added to it")
                             % {"y": key[0], "s": key[1], "a": report.report_number, "b": it["report_number"]}))
        worker = point = None
        if it["position"] == "ENV":
            point = points.get(it["env"].casefold())
            if point is None and create_missing:
                point = points[it["env"].casefold()] = EnvironmentalPoint.objects.create(name=it["env"])
                p_created += 1
            if point is None:
                errors.append((it["row"], _("Unknown environmental point '%(n)s'") % {"n": it["env"]}))
                continue
        else:
            worker = workers.resolve(it["code"], it["name"], create=create_missing, user=user)
            if worker is None:
                errors.append((it["row"], _("Unknown worker '%(n)s' (code and name are needed to create new workers)")
                               % {"n": it["code"] or it["name"]}))
                continue
        _obj, was = TLDReading.objects.update_or_create(
            report=report, tld_code=it["tld_code"],
            defaults={"position": it["position"], "worker": worker, "env_point": point, "gamma_msv": it["gamma"],
                      "neutron_msv": it["neutron"], "remarks": it["remarks"], "created_by": user})
        created += was
        updated += not was
    stats = [(_("TLD reports created"), r_created), (_("Readings added"), created), (_("Readings updated"), updated),
             (_("Workers created"), workers.created), (_("Environmental points created"), p_created)]
    return stats, errors, warnings


# ------------------------------------------------------------------ online doses
def save_online_doses(items, *, user, create_missing, **_kw):
    errors, warnings = [], []
    workers = _Workers()
    ops = {o.name.casefold(): o for o in OperationType.objects.all()}
    devices = {}
    for d in Equipment.objects.all():
        devices.setdefault(d.equipment_id.casefold(), d)
        if d.serial_number:
            devices.setdefault(d.serial_number.casefold(), d)
    groups = OrderedDict()
    for it in items:
        groups.setdefault((it["session"], it["date"], it["operation"].casefold(), it["location"].casefold()), []).append(it)

    s_created = r_created = o_created = skipped = 0
    for rows in groups.values():
        first, resolved, ok = rows[0], [], True
        for it in rows:
            w = workers.resolve(it["code"], it["name"], create=False, user=user)
            d = devices.get(it["device"].casefold())
            if w is None:
                errors.append((it["row"], _("Unknown worker '%(n)s' - add workers first (Workers import)") % {"n": it["code"] or it["name"]}))
                ok = False
            if d is None:
                errors.append((it["row"], _("Unknown device '%(n)s' (use the equipment ID or serial number)") % {"n": it["device"]}))
                ok = False
            elif not (d.application and d.application.is_personal_dosimetry):
                warnings.append((it["row"], _("%(d)s is not marked as a personal dosimeter") % {"d": d.equipment_id}))
            resolved.append((it, w, d))
        if not ok:
            skipped += len(rows)
            continue
        op = ops.get(first["operation"].casefold())
        if op is None:
            if not create_missing:
                errors.append((first["row"], _("Unknown operation type '%(n)s'") % {"n": first["operation"]}))
                skipped += len(rows)
                continue
            op = ops[first["operation"].casefold()] = OperationType.objects.create(name=first["operation"])
            o_created += 1
        if OperationDoseSession.objects.filter(performed_date=first["date"], operation_type=op,
                                               location=first["location"]).exists():
            warnings.append((first["row"], _("%(o)s on %(d)s at '%(l)s' already exists - skipped (not imported twice)")
                             % {"o": op.name, "d": first["date"], "l": first["location"]}))
            skipped += len(rows)
            continue
        session = OperationDoseSession.objects.create(
            operation_type=op, performed_date=first["date"], location=first["location"],
            duration_minutes=first["duration"], description=first["description"], created_by=user)
        s_created += 1
        for it, w, d in resolved:
            OnlineDoseRecord.objects.create(session=session, worker=w, device=d, dose_type=it["dose_type"],
                                            dose_value=it["dose"], dose_unit=it["unit"], exposure_minutes=it["exposure"])
            r_created += 1
    stats = [(_("Operations created"), s_created), (_("Dose lines added"), r_created),
             (_("Operation types created"), o_created), (_("Lines skipped"), skipped)]
    return stats, errors, warnings


# ------------------------------------------------------------------ inspection plan
def save_inspection(items, *, user, plan_year=None, **_kw):
    errors, warnings = [], []
    workers = _Workers()                                  # responsible people are radiation workers, not users
    plans = {p.year: p for p in InspectionPlanYear.objects.all()}
    i_created = i_updated = marks = 0
    unmatched = set()
    for it in items:
        item = InspectionItem.objects.filter(title=it["title"], area=it["area"]).first()
        if item is None:
            item = InspectionItem(title=it["title"], area=it["area"], created_by=user)
            i_created += 1
        else:
            i_updated += 1
        for k, v in it["fields"].items():
            setattr(item, k, v)
        ref = it["responsible"]
        if ref:
            resp = workers.resolve(ref, ref, create=False, user=user)      # personnel code or full name
            if resp:
                item.responsible = resp
            elif ref not in unmatched:
                unmatched.add(ref)
                warnings.append((it["row"], _("Responsible '%(r)s' matches no worker (use the personnel code or full name) - left empty") % {"r": ref}))
        item.save()
        if it["done_weeks"]:
            year = it["plan_year"] or plan_year
            if not year:
                warnings.append((it["row"], _("Done weeks ignored: no plan year given")))
                continue
            plan = plans.get(year) or plans.setdefault(year, InspectionPlanYear.objects.create(year=year))
            for w in it["done_weeks"]:
                if not 1 <= w <= plan.total_weeks:
                    errors.append((it["row"], _("Week %(w)s is outside 1-%(t)s") % {"w": w, "t": plan.total_weeks}))
                    continue
                _rec, was = InspectionRecord.objects.get_or_create(
                    item=item, plan_year=plan, week_index=w, defaults={"is_done": True, "created_by": user})
                if not was and not _rec.is_done:
                    _rec.is_done = True
                    _rec.save()
                marks += was
    return [(_("Inspection items created"), i_created), (_("Inspection items updated"), i_updated),
            (_("Done-marks added"), marks)], errors, warnings


# ------------------------------------------------------------------ calibration assessments
def _code(x):
    return re.sub(r"[\s\-_/]+", "", str(x or "")).casefold()


def save_assessments(items, *, user, apply_all=False, **_kw):
    errors, warnings = [], []
    index = defaultdict(list)
    for d in Equipment.objects.all():
        for key in {_code(d.name), _code(d.model_name)} - {""}:
            index[key].append(d)
    by_id = {_code(d.equipment_id): d for d in Equipment.objects.all()}
    workers = _Workers()
    created = skipped = 0
    for it in items:
        key = _code(it["ref"])
        matches = [by_id[key]] if key in by_id else index.get(key, [])
        if not matches:
            errors.append((it["row"], _("No device matches '%(r)s' (use the equipment ID, or the exact device name / model)") % {"r": it["ref"]}))
            continue
        if len(matches) > 1 and not apply_all:
            errors.append((it["row"], _("'%(r)s' matches %(n)s devices (%(ids)s). Use the equipment ID, or tick “apply to all matching devices”.")
                           % {"r": it["ref"], "n": len(matches), "ids": ", ".join(d.equipment_id for d in matches[:4]) + ("…" if len(matches) > 4 else "")}))
            continue
        assessor = workers.resolve(it["assessor"], it["assessor"], create=False, user=user) if it["assessor"] else None
        date = it["date"] or ju.today()
        for eq in matches:
            same = CalibrationAssessment.objects.filter(
                equipment=eq, assessment_date=date, device_type=it["device_type"], has_maker_recommendation=it["has_maker"],
                maker_recommendation=it["maker"] or "", accuracy=it["accuracy"], environment=it["environment"],
                importance=it["importance"], wear=it["wear"], cost=it["cost"])
            if same.exists():
                skipped += 1
                continue
            CalibrationAssessment.objects.create(
                equipment=eq, assessment_date=date, assessed_by=assessor, device_type=it["device_type"],
                has_maker_recommendation=it["has_maker"], maker_recommendation=it["maker"] or "",
                accuracy=it["accuracy"], environment=it["environment"], importance=it["importance"],
                wear=it["wear"], cost=it["cost"], notes=it["notes"], created_by=user)
            created += 1
    return [(_("Assessments created"), created), (_("Already existed (skipped)"), skipped)], errors, warnings


SAVERS = {"equipment": save_equipment, "workers": save_workers, "tld": save_tld,
          "online_doses": save_online_doses, "inspection": save_inspection,
          "assessments": save_assessments}


def run(kind, parsed, *, user, dry_run, strict, create_missing, plan_year=None, apply_all=False):
    errors, warnings = list(parsed["errors"]), list(parsed["warnings"])
    with transaction.atomic():
        stats, row_errors, row_warnings = SAVERS[kind](
            parsed["items"], user=user, create_missing=create_missing, plan_year=plan_year, apply_all=apply_all)
        errors += row_errors
        warnings += row_warnings
        blocked = strict and bool(errors)
        saved = not dry_run and not blocked
        if not saved:
            transaction.set_rollback(True)
    return {"saved": saved, "dry_run": dry_run, "blocked": blocked and not dry_run,
            "stats": stats, "errors": sorted(errors, key=lambda e: e[0]), "warnings": sorted(warnings, key=lambda e: e[0])}
