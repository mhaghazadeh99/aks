"""
Annual release-limit tracking.

A "release" (liquid discharge, gaseous discharge) is recorded against a
WasteBatch. At the moment of release we snapshot the batch's activity,
broken down the same way laboratory.services.activity.total_activity_breakdown
does: one line per gamma-identified nuclide, plus (if present) one line
for "pure" gross beta and one for "pure" gross alpha — activity gross
counting saw that gamma spectrometry couldn't identify. Snapshotting
matters because the batch keeps decaying / keeps being edited after
release; the release record must not change retroactively.

Two-step flow, deliberately NOT one step:
  1. `preview_release` — read-only. Computes the breakdown and checks it
     against the applicable ReleaseLimit rows, without saving anything.
     Use this to show the operator what they're about to record.
  2. `register_release` — actually records the WasteMovement,
     ReleaseRecord and ReleaseActivityLine rows, re-running the same
     checks (state may have moved between preview and confirm).

Going over an annual limit does NOT raise/block — this is a compliance
record, not a safety interlock, and the person recording it is the one
who needs to decide what happens next. `over_limit` is set on the
record so it's flagged for review; the view is expected to warn loudly
and ask for confirmation before calling register_release when a preview
already shows an excess.
"""

from django.db import transaction
from django.db.models import DecimalField, Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from laboratory.services.activity import total_activity_breakdown

from ..models import (
    BatchStatus, ReleaseActivityLine, ReleaseLimit, ReleaseLimitCategory,
    ChemicalPollutant, ReleaseRecord, WasteMovementType,
)


def _applicable_limit(category, route, facility, radionuclide=None, on_date=None):
    """A facility-specific limit wins over a site-wide one (facility=None)."""
    on_date = on_date or timezone.now().date()
    qs = ReleaseLimit.objects.filter(
        category=category, route=route, effective_from__lte=on_date,
    ).filter(Q(effective_to__isnull=True) | Q(effective_to__gte=on_date))
    if category == ReleaseLimitCategory.NUCLIDE:
        qs = qs.filter(radionuclide=radionuclide)
    return qs.filter(facility=facility).first() or qs.filter(facility__isnull=True).first()


def year_released_bq(category, route, facility, radionuclide=None, year=None):
    """Activity released in `year` for one nuclide / gross category on one route.

    `facility` is the SCOPE of the limit being checked: a facility-specific limit counts only
    that facility's releases; `None` (a site-wide limit) counts every facility's. (Before this
    was fixed, None became "facility IS NULL", which matches nothing, so every site-wide
    limit showed 0 released.)"""
    year = year or timezone.now().year
    qs = ReleaseActivityLine.objects.filter(
        category=category, release__route=route, release__release_date__year=year,
    )
    if facility is not None:
        qs = qs.filter(release__batch__facility=facility)
    if category == ReleaseLimitCategory.NUCLIDE:
        qs = qs.filter(radionuclide=radionuclide)
    return float(qs.aggregate(total=Sum("activity_bq"))["total"] or 0)


def _release_lines(breakdown):
    """Turns an activity breakdown into the (category, radionuclide, activity_bq)
    lines a release is made of — shared by preview and register so they can't drift apart.

    Uses each gamma line's `batch_activity_bq` (the whole-batch figure, already
    scaled from the sample by laboratory.services.activity) — NEVER the raw
    `sample_activity_bq`, which is just whatever the lab sample happened to
    weigh/measure and says nothing on its own about the batch being released.
    A line with no `batch_activity_bq` (couldn't be scaled — see the
    breakdown's warnings) is left out of the release rather than included at
    the wrong scale."""
    lines = []
    for gline in breakdown["gamma_lines"]:
        if gline["batch_activity_bq"]:
            lines.append({
                "category": ReleaseLimitCategory.NUCLIDE,
                "radionuclide": gline["nuclide"],
                "activity_bq": gline["batch_activity_bq"],
            })
    if breakdown["pure_beta_bq"]:
        lines.append({"category": ReleaseLimitCategory.GROSS_BETA, "radionuclide": None, "activity_bq": breakdown["pure_beta_bq"]})
    if breakdown["pure_alpha_bq"]:
        lines.append({"category": ReleaseLimitCategory.GROSS_ALPHA, "radionuclide": None, "activity_bq": breakdown["pure_alpha_bq"]})
    return lines


def _check_lines(lines, route, facility, release_date):
    """For each line: the applicable limit (if any), what's already been released
    this year (NOT including this release), what the total would be if this release
    goes ahead, and whether that total exceeds the limit."""
    checks = []
    for ln in lines:
        limit = _applicable_limit(ln["category"], route, facility, radionuclide=ln["radionuclide"], on_date=release_date)
        # count releases over the same scope the limit applies to (site-wide limit -> all facilities)
        scope = limit.facility if limit else facility
        prior = year_released_bq(ln["category"], route, scope, radionuclide=ln["radionuclide"], year=release_date.year)
        projected = prior + ln["activity_bq"]
        percent = (projected / float(limit.annual_limit_bq) * 100) if limit else None
        checks.append({
            **ln,
            "limit": limit,
            "year_total_before_bq": prior,
            "year_total_after_bq": projected,
            "percent_of_limit": percent,
            "over_limit": bool(limit and projected > float(limit.annual_limit_bq)),
        })
    return checks


def preview_release(batch, route, release_date=None):
    """Read-only: what WOULD be recorded, and how it stacks up against limits."""
    release_date = release_date or timezone.now().date()
    breakdown = batch.activity_breakdown(as_of=release_date)
    lines = _release_lines(breakdown)
    checks = _check_lines(lines, route, batch.facility, release_date)
    return breakdown, checks


@transaction.atomic
def register_release(batch, route, performed_by, remarks="", release_date=None, pollutants=None):
    """Records the release and CLOSES the batch (status RELEASED -- from then on it accepts no
    split / merge / condition / movement / edit / second release; see WasteBatch.ensure_open).

    `pollutants`: optional list of {"name", "concentration", "unit"} measured AT RELEASE; they are
    saved against this release record (and so also show on the batch)."""
    batch.ensure_open()

    release_date = release_date or timezone.now().date()
    breakdown = batch.activity_breakdown(as_of=release_date)
    lines = _release_lines(breakdown)

    movement = batch.register_movement(
        movement_type=WasteMovementType.RELEASE, to_facility=batch.facility,
        performed_by=performed_by, remarks=remarks, movement_date=release_date,
        mass_kg=batch.mass_kg, volume_m3=batch.volume_m3,
    )

    record = ReleaseRecord.objects.create(
        batch=batch, movement=movement, route=route, release_date=release_date,
        performed_by=performed_by, remarks=remarks,
        # snapshot: what was released is the batch AS IT WAS at this moment
        volume_m3=batch.volume_m3, mass_kg=batch.mass_kg,
    )

    for p in pollutants or []:
        ChemicalPollutant.objects.create(
            batch=batch, release=record, name=p["name"], concentration=p["concentration"],
            unit=p["unit"], measured_on=release_date,
        )

    ReleaseActivityLine.objects.bulk_create([
        ReleaseActivityLine(release=record, category=ln["category"], radionuclide=ln["radionuclide"], activity_bq=ln["activity_bq"])
        for ln in lines
    ])

    # Re-check AFTER the lines are saved, so "released this year" includes this release.
    checks = _check_lines(lines, route, batch.facility, release_date)
    if any(c["over_limit"] for c in checks):
        record.over_limit = True
        record.save(update_fields=["over_limit"])

    return record, breakdown, checks



# =====================================================================
# Annual release REPORT data -- totals and "everything released".
#
# What the three activity totals mean (the same split a batch's own page uses, so the numbers
# agree with it):
#   gamma = activity of nuclides identified by gamma spectrometry (NUCLIDE lines). Each is
#           counted once, including any beta/alpha it also emits.
#   beta  = the UNIDENTIFIED beta left after subtracting those nuclides from the gross beta
#           count (GROSS_BETA lines);  alpha likewise (GROSS_ALPHA lines).
#   total = gamma + beta + alpha  (the batch's total activity).
# Volume and mass are the batch's recorded size at the moment of release (stored on the release's
# movement), so batches with no recorded volume/mass simply add nothing to those two rows.
# =====================================================================

def _scoped(year, route):
    records = ReleaseRecord.objects.all()
    lines = ReleaseActivityLine.objects.all()
    if year:
        records = records.filter(release_date__year=year)
        lines = lines.filter(release__release_date__year=year)
    if route:
        records = records.filter(route=route)
        lines = lines.filter(release__route=route)
    return records, lines


def release_totals(year=None, route=""):
    """Totals over every release (optionally one year and/or one route). Floats; None where unknown."""
    records, lines = _scoped(year, route)

    dec = DecimalField(max_digits=14, decimal_places=3)
    moved = records.aggregate(
        volume_m3=Sum(Coalesce("volume_m3", "movement__volume_m3", output_field=dec)),
        mass_kg=Sum(Coalesce("mass_kg", "movement__mass_kg", output_field=dec)),
    )
    by_category = {
        row["category"]: float(row["total"] or 0)
        for row in lines.values("category").annotate(total=Sum("activity_bq"))
    }
    gamma = by_category.get(ReleaseLimitCategory.NUCLIDE, 0.0)
    beta = by_category.get(ReleaseLimitCategory.GROSS_BETA, 0.0)
    alpha = by_category.get(ReleaseLimitCategory.GROSS_ALPHA, 0.0)

    return {
        "releases": records.count(),
        "batches": records.values("batch").distinct().count(),
        "over_limit_releases": records.filter(over_limit=True).count(),
        "volume_m3": float(moved["volume_m3"]) if moved["volume_m3"] is not None else None,
        "mass_kg": float(moved["mass_kg"]) if moved["mass_kg"] is not None else None,
        "gamma_bq": gamma, "beta_bq": beta, "alpha_bq": alpha,
        "total_bq": gamma + beta + alpha,
    }


def released_by_line(year, route=""):
    """Everything released, one row per nuclide / gross category / route, with the selected
    year's total, the all-years total, its share of that year's activity, and whether any limit
    is defined for it. Sorted: identified nuclides first, biggest first."""
    _, year_lines = _scoped(year, route)
    _, all_lines = _scoped(None, route)

    keys = ("category", "radionuclide", "radionuclide__name", "release__route")
    year_rows = {
        (r["category"], r["radionuclide"], r["release__route"]): (r["radionuclide__name"], float(r["total"] or 0))
        for r in year_lines.values(*keys).annotate(total=Sum("activity_bq"))
    }
    all_rows = {
        (r["category"], r["radionuclide"], r["release__route"]): (r["radionuclide__name"], float(r["total"] or 0))
        for r in all_lines.values(*keys).annotate(total=Sum("activity_bq"))
    }

    year_total = sum(v[1] for v in year_rows.values())
    rows = []
    for key in set(year_rows) | set(all_rows):
        category, nuclide_id, rt = key
        name = (year_rows.get(key) or all_rows.get(key))[0]
        year_bq = year_rows.get(key, (None, 0.0))[1]
        limit_qs = ReleaseLimit.objects.filter(category=category, route=rt, effective_from__year__lte=year).filter(
            Q(effective_to__isnull=True) | Q(effective_to__year__gte=year)
        )
        if category == ReleaseLimitCategory.NUCLIDE:
            limit_qs = limit_qs.filter(radionuclide_id=nuclide_id)
        rows.append({
            "category": category, "radionuclide": name, "route": rt,
            "year_bq": year_bq, "all_bq": all_rows.get(key, (None, 0.0))[1],
            "share": (year_bq / year_total * 100) if year_total else None,
            "has_limit": limit_qs.exists(),
        })

    order = {ReleaseLimitCategory.NUCLIDE: 0, ReleaseLimitCategory.GROSS_BETA: 1, ReleaseLimitCategory.GROSS_ALPHA: 2}
    rows.sort(key=lambda r: (order.get(r["category"], 9), -r["year_bq"], r["radionuclide"] or ""))
    return rows


def limit_rows(year, route=""):
    """One row per release limit that applies to `year` (a limit that ended before it isn't included):
    {"limit", "released_bq", "percent"}. A facility-specific limit counts that facility's releases;
    a site-wide limit counts every facility's (see year_released_bq)."""
    limits = (
        ReleaseLimit.objects
        .filter(effective_from__year__lte=year)
        .filter(Q(effective_to__isnull=True) | Q(effective_to__year__gte=year))
        .select_related("radionuclide", "facility")
    )
    if route:
        limits = limits.filter(route=route)
    rows = []
    for limit in limits:
        released = year_released_bq(
            limit.category, limit.route, limit.facility, radionuclide=limit.radionuclide, year=year,
        )
        percent = (released / float(limit.annual_limit_bq) * 100) if limit.annual_limit_bq else None
        rows.append({"limit": limit, "released_bq": released, "percent": percent})
    return rows


# ---- display helpers (kept in Python so the template needs no custom filters) ----

def fmt_sci(value, sig=4):
    if value is None:
        return "-"
    if value == 0:
        return "0"
    return f"{value:.{sig}g}"


def fmt_activity(bq):
    """{'gbq': '12.5', 'bq': '1.25e+10'} -- GBq is the readable one, Bq is what the limits are in."""
    if bq is None:
        return {"gbq": "-", "bq": "-"}
    return {"gbq": fmt_sci(bq / 1e9), "bq": fmt_sci(bq)}


def display_totals(t):
    return {
        "releases": t["releases"], "batches": t["batches"], "over_limit_releases": t["over_limit_releases"],
        "volume": fmt_sci(t["volume_m3"]), "mass": fmt_sci(t["mass_kg"]),
        "gamma": fmt_activity(t["gamma_bq"]), "beta": fmt_activity(t["beta_bq"]),
        "alpha": fmt_activity(t["alpha_bq"]), "total": fmt_activity(t["total_bq"]),
    }