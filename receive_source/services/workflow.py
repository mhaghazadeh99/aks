from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from dashboard.models import DSRS, SOURCE_TYPE, SOURCE_STATUS, MovementType

from receive_source.models import ReceiveApproval, ReceiveStatus


# =====================================================================
# CREATION
# =====================================================================

def create_receive_workflow(receive_request):
    """
    Called once, right after a ReceiveRequest is first saved (mirrors
    operations.services.workflow.create_license_workflow). Pre-creates
    the four ALWAYS-required approval rows. The CEO row is deliberately
    NOT created here — see maybe_add_ceo_step() below — since whether
    it's required depends on the contract's discount_requested flag,
    which doesn't exist yet at this point.
    """

    ReceiveApproval.objects.bulk_create([
        ReceiveApproval(
            receive_request=receive_request,
            step=ReceiveApproval.ApprovalStep.CREATOR,
            order=1,
        ),
        ReceiveApproval(
            receive_request=receive_request,
            step=ReceiveApproval.ApprovalStep.MANAGER,
            order=2,
        ),
        ReceiveApproval(
            receive_request=receive_request,
            step=ReceiveApproval.ApprovalStep.CONTROL,
            order=3,
        ),
        ReceiveApproval(
            receive_request=receive_request,
            step=ReceiveApproval.ApprovalStep.DEPUTY,
            order=4,
        ),
    ])


def maybe_add_ceo_step(receive_request):
    """
    Call this when the ReceiveContract is saved. If discount_requested
    is True and a CEO approval row doesn't exist yet, create it and move
    status to WAITING_CEO. Otherwise (no discount), skip straight to
    FINANCE — same pattern as license_contract_create/update's
    send_to_financial check.
    """

    contract = receive_request.contract

    if contract.discount_requested:

        ReceiveApproval.objects.get_or_create(
            receive_request=receive_request,
            step=ReceiveApproval.ApprovalStep.CEO,
            defaults={"order": 5},
        )

        receive_request.status = ReceiveStatus.WAITING_CEO
        receive_request.status_date = timezone.now()
        receive_request.save(update_fields=["status", "status_date"])

    elif contract.send_to_financial:

        receive_request.status = ReceiveStatus.FINANCE
        receive_request.status_date = timezone.now()
        receive_request.save(update_fields=["status", "status_date"])


# =====================================================================
# HALF-LIFE SNAPSHOT
# =====================================================================

def format_half_life(seconds):
    """
    nuclide.half_life is stored in seconds (per reference.models.Nuclides).
    Renders a compact human string in the largest sensible unit, matching
    what you'd hand-write on the paper form (e.g. "5.27 years", "8.02 days").
    """

    if seconds is None:
        return ""

    year = 365.25 * 86400
    day = 86400
    hour = 3600
    minute = 60

    if seconds >= year:
        return _("%(v).2f years") % {"v": seconds / year}
    if seconds >= day:
        return _("%(v).2f days") % {"v": seconds / day}
    if seconds >= hour:
        return _("%(v).2f hours") % {"v": seconds / hour}
    if seconds >= minute:
        return _("%(v).2f minutes") % {"v": seconds / minute}
    return _("%(v).2f seconds") % {"v": seconds}


def snapshot_half_life(receive_source, save=True):
    if receive_source.nuclide:
        receive_source.half_life_display = format_half_life(receive_source.nuclide.half_life)
        if save:
            receive_source.save(update_fields=["half_life_display"])


# =====================================================================
# POST-PAYMENT: CREATE THE PHYSICAL DSRS RECORDS
# =====================================================================

def create_dsrs_for_receive_request(receive_request, performed_by):
    """
    Called once ReceivePayment.payment_done flips True (mirrors
    operations.services.fulfillment.fulfill_license_sources). Creates one
    DSRS per ReceiveSource row (quantity expanded into that many rows).

    Status is intentionally SOURCE_STATUS.IN_USE, not blank — per current
    policy the source is still considered "in use"/in transit until the
    physical receiving + characterization is finished and it's explicitly
    marked stored (see mark_source_stored below), at which point
    register_movement(RECEIVE) flips it to STORED.

    DSRS.contract is left null regardless of any license-contract match
    found earlier (see services.license_check) — that match is purely
    informational for this workflow.
    """

    facility = receive_request.facility
    today = timezone.now().date()

    for source in receive_request.sources.select_related("nuclide").all():

        if source.result_dsrs_id:
            continue  # already created (e.g. re-running after a partial failure)

        for _i in range(source.quantity or 1):

            dsrs = DSRS.objects.create(
                Source_Type=(
                    SOURCE_TYPE.DSRS if source.item_type == "SOURCE" else SOURCE_TYPE.DSRS
                ),
                Facility=facility,
                Origin_Type="Received",
                Date_received=today,
                Nuclide=source.nuclide,
                activity_input=float(source.average_activity_mci) if source.average_activity_mci else None,
                activity_unit="mCi",
                Activity_reference_date=today,
                serial_number=source.serial_number if (source.quantity or 1) == 1 else "",
                source_count=1,
                available_count=1,
                Status=SOURCE_STATUS.IN_USE,
                Status_Date=today,
                Responsible_Person=getattr(facility, "responsible_person", None),
                Comment=source.description[:255] if source.description else "",
                contract=None,
                created_by=performed_by,
            )

            # Only the FIRST created DSRS is linked back for a multi-quantity
            # row — matches the "one row can expand to N DSRS" pattern used
            # in operations' CSV import; if you need all N linked, this is
            # the spot to change to a M2M or a separate join table instead.
            if not source.result_dsrs_id:
                source.result_dsrs = dsrs
                source.save(update_fields=["result_dsrs"])

    receive_request.status = ReceiveStatus.RECEIVING
    receive_request.status_date = timezone.now()
    receive_request.save(update_fields=["status", "status_date"])


# =====================================================================
# FINALIZE: MARK A SOURCE (AND EVENTUALLY THE WHOLE REQUEST) STORED
# =====================================================================

def mark_source_stored(dsrs, receive_request, performed_by, remarks=""):
    """
    Called per-DSRS once its characterization (dose rate, physical form,
    container, photos/docs) is complete. Reuses the existing movement
    machinery — MOVEMENT_TO_STATUS[RECEIVE] == STORED — instead of
    setting Status directly, so SourceMovement history stays consistent
    with every other status change in the system.
    """

    dsrs.register_movement(
        movement_type=MovementType.RECEIVE,
        to_facility=receive_request.facility,
        performed_by=performed_by,
        quantity=1,
        remarks=remarks or _("Received via %(req)s") % {"req": str(receive_request)},
    )

    check_and_complete_receive_request(receive_request)


def check_and_complete_receive_request(receive_request):
    """If every ReceiveSource's result_dsrs is now STORED, complete the request."""

    sources = receive_request.sources.select_related("result_dsrs")

    all_stored = all(
        s.result_dsrs and s.result_dsrs.Status == SOURCE_STATUS.STORED
        for s in sources
    )

    if all_stored and sources.exists():
        receive_request.status = ReceiveStatus.COMPLETED
        receive_request.status_date = timezone.now()
        receive_request.save(update_fields=["status", "status_date"])
