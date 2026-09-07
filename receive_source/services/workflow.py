from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from dashboard.models import DSRS, SOURCE_TYPE, SOURCE_STATUS, MovementType

from ..models import ReceiveApproval, ReceiveStatus


def get_irwa_facility():
    """The company's own facility record — matched (contracted) sources
    move straight here on payment, and newly-created sources move here
    once characterization is finished and they're marked stored."""
    from facilities.models import FacilityModel
    try:
        return FacilityModel.objects.get(name="IRWA")
    except FacilityModel.DoesNotExist:
        raise FacilityModel.DoesNotExist(
            "No FacilityModel record named 'IRWA' found. This is required as "
            "the destination facility for stored receive sources."
        )


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
    Call this when the ReceiveContract (really just a cost/discount
    declaration, not an actual contract) is saved. discount_requested
    True -> CEO signs before Finance. Otherwise -> straight to Finance,
    unconditionally (no separate "send to financial" flag anymore since
    there's no real contract to hold back on).
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

    else:

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
    operations.services.fulfillment.fulfill_license_sources).

    Two cases per ReceiveSource:

    1. matched_license_dsrs is set — this is already an "In Use" DSRS
       record in our own inventory, under an existing license contract.
       We do NOT create a new record for it. It's already fully
       characterized, so there's nothing left to do except bring it
       home: Status -> Stored, Facility -> IRWA, right now (no trip
       through the RECEIVING/characterization stage at all).

    2. No match — a genuinely new item. Create one DSRS per unit
       (Status starts IN_USE, still logically "out" at the delivering
       facility) and it goes through the normal characterization ->
       mark-stored flow, which is when it actually moves to IRWA.
    """

    facility = receive_request.facility
    irwa = get_irwa_facility()
    today = timezone.now().date()

    for source in receive_request.sources.select_related("nuclide", "matched_license_dsrs").all():

        if source.result_dsrs_id:
            continue  # already handled (e.g. re-running after a partial failure)

        if source.matched_license_dsrs_id:

            existing = source.matched_license_dsrs

            existing.register_movement(
                movement_type=MovementType.RETURN,
                to_facility=irwa,
                performed_by=performed_by,
                quantity=1,
                remarks=_("Returned to IRWA via %(req)s") % {"req": str(receive_request)},
            )

            source.result_dsrs = existing
            source.save(update_fields=["result_dsrs"])
            continue

        for _i in range(source.quantity or 1):

            dsrs = DSRS.objects.create(
                Source_Type=SOURCE_TYPE.DSRS,
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

            if not source.result_dsrs_id:
                source.result_dsrs = dsrs
                source.save(update_fields=["result_dsrs"])

    receive_request.status = ReceiveStatus.RECEIVING
    receive_request.status_date = timezone.now()
    receive_request.save(update_fields=["status", "status_date"])

    # If every source turned out to be a matched/inventory item, there's
    # nothing left to characterize — this request may already be done.
    check_and_complete_receive_request(receive_request)


# =====================================================================
# FINALIZE: MARK A SOURCE (AND EVENTUALLY THE WHOLE REQUEST) STORED
# =====================================================================

def mark_source_stored(dsrs, receive_request, performed_by, remarks=""):
    """
    Called per-DSRS once its characterization (dose rate, physical form,
    container, photos/docs) is complete. Moves it to IRWA (final storage
    location) and STORED via the RECEIVE movement type, reusing the
    existing movement machinery for consistent history.
    """

    irwa = get_irwa_facility()

    dsrs.register_movement(
        movement_type=MovementType.RECEIVE,
        to_facility=irwa,
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