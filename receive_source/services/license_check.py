"""
Checks the DSRS inventory for an existing license contract belonging to
the SAME facility, for the SAME nuclide, when a coordinator adds a
ReceiveSource row.

Matching rule (per business requirement):
  1. facility + nuclide + serial_number, exact (case-insensitive) match
     -> auto-confirmed, no user interaction needed.
  2. facility + nuclide match but no exact serial hit (serial numbers are
     hand-typed and error-prone) -> surface candidate DSRS records with
     SIMILAR serial numbers and let the creator pick one, or "None of
     these".
  3. No facility+nuclide match at all -> nothing to show; this item has
     no known prior license contract.

This is purely informational (per the current answer): it only affects
ReceiveSource.description / matched_license_dsrs. It never sets
DSRS.contract on the new record created after payment.
"""

import difflib

from django.utils.translation import gettext_lazy as _

from dashboard.models import DSRS


def find_license_contract_match(facility, nuclide, serial_number=None, similarity_cutoff=0.4, max_candidates=5):
    """
    Returns:
        {
            "exact": DSRS | None,
            "candidates": [DSRS, ...],   # only populated when exact is None
        }
    """

    base_qs = (
        DSRS.objects.filter(
            contract__isnull=False,
            contract__license__facility=facility,
            Nuclide=nuclide,
        )
        .exclude(serial_number__isnull=True)
        .exclude(serial_number="")
        .select_related("contract", "contract__license")
    )

    exact = None
    if serial_number:
        exact = base_qs.filter(serial_number__iexact=serial_number.strip()).first()

    candidates = []

    if not exact:
        all_matches = list(base_qs)

        if serial_number:
            close_serials = difflib.get_close_matches(
                serial_number.strip(),
                [d.serial_number for d in all_matches],
                n=max_candidates,
                cutoff=similarity_cutoff,
            )
            candidates = [d for d in all_matches if d.serial_number in close_serials]
        else:
            # No serial typed at all — every facility+nuclide contract hit
            # is a candidate, capped for sanity.
            candidates = all_matches[:max_candidates]

    return {"exact": exact, "candidates": candidates}


def build_contract_note(matched_dsrs):
    """Text appended to ReceiveSource.description for a confirmed match."""
    return _(
        "Existing license contract found: %(num)s (facility & nuclide match, serial: %(serial)s)"
    ) % {
        "num": matched_dsrs.contract.contract_number or "-",
        "serial": matched_dsrs.serial_number,
    }


def annotate_source_with_match(receive_source, facility, save=True):
    """
    Runs the check for a single ReceiveSource and, on an EXACT match only,
    auto-fills matched_license_dsrs / serial_matched_exactly / description.
    Fuzzy candidates are NOT auto-applied here — the view must show them
    to the creator and call `confirm_match()` (or nothing) based on the
    creator's choice.

    Returns the same dict as find_license_contract_match(), so the view
    can decide whether a picker needs to be shown.
    """

    result = find_license_contract_match(
        facility=facility,
        nuclide=receive_source.nuclide,
        serial_number=receive_source.serial_number,
    )

    if result["exact"]:
        receive_source.matched_license_dsrs = result["exact"]
        receive_source.serial_matched_exactly = True
        note = build_contract_note(result["exact"])
        receive_source.description = (
            f"{receive_source.description}\n{note}".strip()
            if receive_source.description else note
        )
        if save:
            receive_source.save(update_fields=[
                "matched_license_dsrs", "serial_matched_exactly", "description",
            ])

    return result


def confirm_match(receive_source, chosen_dsrs, save=True):
    """Called when the creator picks one of the fuzzy candidates."""

    receive_source.matched_license_dsrs = chosen_dsrs
    receive_source.serial_matched_exactly = False
    note = build_contract_note(chosen_dsrs)
    receive_source.description = (
        f"{receive_source.description}\n{note}".strip()
        if receive_source.description else note
    )
    if save:
        receive_source.save(update_fields=[
            "matched_license_dsrs", "serial_matched_exactly", "description",
        ])