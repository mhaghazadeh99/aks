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
from django.db.models import Q, Sum
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from laboratory.services.activity import total_activity_breakdown

from ..models import (
    BatchStatus, ReleaseActivityLine, ReleaseLimit, ReleaseLimitCategory,
    ReleaseRecord, WasteMovementType,
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
    year = year or timezone.now().year
    qs = ReleaseActivityLine.objects.filter(
        category=category, release__route=route, release__batch__facility=facility,
        release__release_date__year=year,
    )
    if category == ReleaseLimitCategory.NUCLIDE:
        qs = qs.filter(radionuclide=radionuclide)
    return float(qs.aggregate(total=Sum("activity_bq"))["total"] or 0)


def _release_lines(breakdown):
    """Turns an activity breakdown into the (category, radionuclide, activity_bq)
    lines a release is made of — shared by preview and register so they can't drift apart."""
    lines = []
    for gline in breakdown["gamma_lines"]:
        if gline["activity_bq"]:
            lines.append({
                "category": ReleaseLimitCategory.NUCLIDE,
                "radionuclide": gline["nuclide"],
                "activity_bq": gline["activity_bq"],
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
        prior = year_released_bq(ln["category"], route, facility, radionuclide=ln["radionuclide"], year=release_date.year)
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
def register_release(batch, route, performed_by, remarks="", release_date=None):
    if batch.status == BatchStatus.CONSUMED:
        raise ValueError(_("This batch has already been consumed and can't be released."))

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