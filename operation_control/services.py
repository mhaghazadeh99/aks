"""Aggregations for the dosimetry reports and the inspection-plan matrix."""
from collections import defaultdict
from decimal import Decimal

from django.db.models import Q, Sum
from django.utils.translation import gettext_lazy as _

from . import conf, logic
from . import jalali_utils as ju
from .models import (
    Equipment, EnvironmentalPoint, InspectionItem, InspectionRecord, OnlineDoseRecord,
    RadiationWorker, Season, TLDReading,
)

ZERO = Decimal("0")
SEASONS = (1, 2, 3, 4)
_EMPTY_TLD = {"body_gamma": ZERO, "body_neutron": ZERO, "hand_gamma": ZERO, "hand_neutron": ZERO}
_EMPTY_ONLINE = {"gamma": ZERO, "neutron": ZERO}

MONTH_NAMES = [_("Farvardin"), _("Ordibehesht"), _("Khordad"), _("Tir"), _("Mordad"), _("Shahrivar"),
               _("Mehr"), _("Aban"), _("Azar"), _("Dey"), _("Bahman"), _("Esfand")]


def current_year_season():
    jy, jm, _jd = ju.jalali_today()
    return jy, ju.season_of_month(jm)


# ============================================================ calibration alerts
def calibration_alerts(limit=8):
    """
    Devices whose calibration has expired or expires within CALIBRATION_WARNING_DAYS.
    Inactive devices and devices already sent for calibration are not counted.
    """
    today = ju.today()
    soon = ju.add_days(today, conf.CALIBRATION_WARNING_DAYS)
    watched = Equipment.objects.filter(status__in=[Equipment.Status.ACTIVE, Equipment.Status.ON_LOAN])
    expired = watched.filter(due_date__lt=today).order_by("due_date")
    due_soon = watched.filter(due_date__gte=today, due_date__lte=soon).order_by("due_date")
    return {
        "expired_count": expired.count(), "due_soon_count": due_soon.count(),
        "expired": list(expired[:limit]), "due_soon": list(due_soon[:limit]),
        "days": conf.CALIBRATION_WARNING_DAYS,
    }


# ============================================================ dosimetry
def tld_by_worker(year, season=None):
    qs = TLDReading.objects.filter(report__year=year, worker__isnull=False)
    if season:
        qs = qs.filter(report__season=season)
    out = defaultdict(lambda: dict(_EMPTY_TLD))
    for r in qs.values("worker_id", "position").annotate(g=Sum("gamma_msv"), n=Sum("neutron_msv")):
        key = "body" if r["position"] == TLDReading.Position.BODY else "hand"
        out[r["worker_id"]][key + "_gamma"] += r["g"] or ZERO
        out[r["worker_id"]][key + "_neutron"] += r["n"] or ZERO
    return out


def online_by_worker(year, season=None):
    qs = OnlineDoseRecord.objects.filter(session__year=year)
    if season:
        qs = qs.filter(session__season=season)
    out = defaultdict(lambda: dict(_EMPTY_ONLINE))
    for r in qs.values("worker_id", "dose_type").annotate(t=Sum("dose_msv")):
        out[r["worker_id"]][r["dose_type"].lower()] += r["t"] or ZERO
    return out


def season_report(year, season):
    """TLD (official) and online (operational) side by side - never summed together."""
    tld, online = tld_by_worker(year, season), online_by_worker(year, season)
    ids = set(tld) | set(online)
    workers = RadiationWorker.objects.filter(
        Q(pk__in=ids) | Q(status=RadiationWorker.Status.ACTIVE)).order_by("full_name")
    limit, rows = conf.SEASON_DOSE_LIMIT_MSV, []
    for w in workers:
        t, o = tld.get(w.pk, _EMPTY_TLD), online.get(w.pk, _EMPTY_ONLINE)
        body_total, online_total = t["body_gamma"] + t["body_neutron"], o["gamma"] + o["neutron"]
        rows.append({
            "worker": w, "t": t, "o": o,
            "body_total": body_total, "online_total": online_total,
            "tld_over": body_total > limit, "online_over": online_total > limit,
            "has_data": w.pk in ids,
        })
    return rows


def year_report(year):
    body = defaultdict(lambda: {s: ZERO for s in SEASONS})
    qs = TLDReading.objects.filter(report__year=year, position=TLDReading.Position.BODY, worker__isnull=False)
    for r in qs.values("worker_id", "report__season").annotate(g=Sum("gamma_msv"), n=Sum("neutron_msv")):
        body[r["worker_id"]][r["report__season"]] += (r["g"] or ZERO) + (r["n"] or ZERO)
    online = online_by_worker(year)
    ids = set(body) | set(online)
    rows = []
    for w in RadiationWorker.objects.filter(pk__in=ids).order_by("full_name"):
        seasons = body[w.pk]
        total = sum(seasons.values(), ZERO)
        o = online.get(w.pk, _EMPTY_ONLINE)
        rows.append({
            "worker": w,
            "seasons": [{"value": seasons[s], "over": seasons[s] > conf.SEASON_DOSE_LIMIT_MSV} for s in SEASONS],
            "tld_total": total, "over": total > conf.ANNUAL_DOSE_LIMIT_MSV,
            "online_total": o["gamma"] + o["neutron"],
        })
    return rows


def env_report(year):
    data = defaultdict(lambda: {s: {"gamma": ZERO, "neutron": ZERO} for s in SEASONS})
    qs = TLDReading.objects.filter(report__year=year, env_point__isnull=False)
    for r in qs.values("env_point_id", "report__season").annotate(g=Sum("gamma_msv"), n=Sum("neutron_msv")):
        data[r["env_point_id"]][r["report__season"]] = {"gamma": r["g"] or ZERO, "neutron": r["n"] or ZERO}
    rows = []
    for p in EnvironmentalPoint.objects.filter(Q(is_active=True) | Q(pk__in=list(data))):
        seasons = data[p.pk]
        rows.append({"point": p, "seasons": [seasons[s] for s in SEASONS]})
    return rows


def worker_trend(worker, from_year, to_year):
    tld = defaultdict(lambda: {"body": ZERO, "hand": ZERO})
    qs = TLDReading.objects.filter(worker=worker, report__year__gte=from_year, report__year__lte=to_year)
    for r in qs.values("report__year", "report__season", "position").annotate(g=Sum("gamma_msv"), n=Sum("neutron_msv")):
        key = "body" if r["position"] == TLDReading.Position.BODY else "hand"
        tld[(r["report__year"], r["report__season"])][key] += (r["g"] or ZERO) + (r["n"] or ZERO)
    online = defaultdict(lambda: ZERO)
    qs = OnlineDoseRecord.objects.filter(worker=worker, session__year__gte=from_year, session__year__lte=to_year)
    for r in qs.values("session__year", "session__season").annotate(t=Sum("dose_msv")):
        online[(r["session__year"], r["session__season"])] += r["t"] or ZERO
    rows = []
    for y in range(from_year, to_year + 1):
        for s in SEASONS:
            rows.append({"year": y, "season": s, "label": f"{y} {Season(s).label}",
                         "tld_body": tld[(y, s)]["body"], "tld_hand": tld[(y, s)]["hand"],
                         "online": online[(y, s)]})
    return rows


def over_limit_count(year, season):
    return sum(1 for t in tld_by_worker(year, season).values()
               if t["body_gamma"] + t["body_neutron"] > conf.SEASON_DOSE_LIMIT_MSV)


# ============================================================ inspection plan
def plan_matrix(plan):
    ty, tm, td = ju.jalali_today()
    current = logic.current_week(plan.year, plan.first_month, ty, tm, td)
    total = plan.total_weeks

    records, record_info = defaultdict(dict), {}
    for r in InspectionRecord.objects.filter(plan_year=plan).prefetch_related("performed_by", "attachments"):
        records[r.item_id][r.week_index] = r
        record_info[f"{r.item_id}-{r.week_index}"] = {
            "done": r.is_done, "date": ju.display(r.done_date), "note": r.note,
            "workers": [w.full_name for w in r.performed_by.all()],
            "files": [{"name": a.filename, "url": a.file.url} for a in r.attachments.all()],
        }

    rows = []
    summary = {"due": 0, "done": 0, "overdue_items": 0, "pending_now": 0}
    for item in InspectionItem.objects.filter(is_active=True).select_related("responsible"):
        recs = records.get(item.pk, {})
        cells, due, done, overdue, pending_now = [], 0, 0, 0, False
        for w in range(1, total + 1):
            rec = recs.get(w)
            is_done = bool(rec and rec.is_done)
            state = logic.cell_state(item.period_weeks, w, is_done, current)
            scheduled = item.is_due_in_week(w)
            if scheduled and w <= current:
                due += 1
                done += is_done
            overdue += state == "overdue"
            pending_now = pending_now or state == "current"
            month, slot = logic.week_to_month_slot(w, plan.first_month)
            cells.append({"week": w, "state": state, "scheduled": scheduled,
                          "tip": f"{MONTH_NAMES[month - 1]} #{slot}" + (f" — {ju.display(rec.done_date)}" if rec and rec.done_date else ""),
                          "has_note": bool(rec and rec.note),
                          "has_files": bool(rec and is_done and len(rec.attachments.all()))})   # prefetched: no extra queries
        notes = [r.note for _w, r in sorted(recs.items(), reverse=True) if r.note]
        rows.append({"item": item, "cells": cells, "due": due, "done": done, "overdue": overdue,
                     "percent": round(done * 100 / due) if due else None,
                     "pending_now": pending_now, "note": notes[0] if notes else ""})
        summary["due"] += due
        summary["done"] += done
        summary["overdue_items"] += overdue > 0
        summary["pending_now"] += pending_now
    summary["percent"] = round(summary["done"] * 100 / summary["due"]) if summary["due"] else None
    months = [{"name": MONTH_NAMES[m - 1], "span": 4} for m in range(plan.first_month, 13)]
    return {"rows": rows, "months": months, "current": current, "total": total, "summary": summary,
            "records": record_info}
