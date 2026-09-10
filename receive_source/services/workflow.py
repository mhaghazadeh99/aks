from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.core.files.base import ContentFile

from dashboard.models import DSRS, SOURCE_TYPE, SOURCE_STATUS, MovementType

from ..models import ReceiveApproval, ReceiveStatus, ReceiveAttachmentType


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
    all FIVE approval rows, including CEO — the discount decision is now
    made by the creator up front (see ReceiveDiscountForm), so unlike
    before, whether CEO is actually needed doesn't depend on anything
    that happens later. The CEO row simply stays PENDING/unused if
    discount_requested never gets checked — routing (see receive_sign in
    views.py) is still driven by receive_request.discount_requested at
    the moment Deputy signs.
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
        ReceiveApproval(
            receive_request=receive_request,
            step=ReceiveApproval.ApprovalStep.CEO,
            order=5,
        ),
    ])


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
       We do NOT create a new record for it — we reuse it directly. It
       moves to IRWA now via a TRANSFER movement (Status -> IN_USE, the
       still fully characterized, so its DSRS record doesn't change at
       all until it's explicitly marked stored on the characterization
       page — same single-movement path as brand-new items below.

    2. No match — a genuinely new item. Create one DSRS per unit
       (Status starts IN_USE, still logically "out" at the delivering
       facility) and it goes through the same characterization ->
       mark-stored flow.

    Per current policy there is exactly ONE SourceMovement per DSRS for
    this whole process — created at mark_source_stored time, not here.
    """

    facility = receive_request.facility
    today = timezone.now().date()

    for source in receive_request.sources.select_related("nuclide", "matched_license_dsrs").prefetch_related("result_dsrs").all():

        if source.result_dsrs.exists():
            continue  # already handled (e.g. re-running after a partial failure)

        if source.matched_license_dsrs_id:
            # Nothing to create or move yet — it's linked as-is and stays
            # wherever it currently sits until "Mark Stored" is clicked.
            source.result_dsrs.add(source.matched_license_dsrs)
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
                # A shared serial number can't apply to more than one
                # physical unit — left blank per-unit when quantity > 1,
                # to be filled in individually during characterization.
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

            # EVERY unit gets linked — not just the first — so each one
            # shows up as its own row in characterization and can be
            # edited/marked-stored independently.
            source.result_dsrs.add(dsrs)

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
    container, photos/docs) is complete. This is the ONE AND ONLY
    SourceMovement created for this DSRS in the whole receive process —
    from wherever it currently sits (dsrs.Facility, captured BEFORE the
    move — register_movement overwrites it internally) to IRWA, Status
    -> Stored, via the RECEIVE movement type.

    Also copies every staged صورتجلسه file (ReceiveAttachment,
    attachment_type=CHARACTERIZATION, uploaded once for the whole batch
    on the characterization list page) onto this movement as
    MovementAttachment rows — reusing your existing model rather than a
    new one. If صورتجلسه is uploaded before this DSRS is marked stored,
    it lands on this movement automatically; if uploaded after, it
    won't retroactively attach to already-stored units.
    """

    irwa = get_irwa_facility()
    from_facility = dsrs.Facility  # capture BEFORE register_movement reassigns it

    movement = dsrs.register_movement(
        movement_type=MovementType.RECEIVE,
        to_facility=irwa,
        from_facility=from_facility,
        performed_by=performed_by,
        quantity=1,
        remarks=remarks or _("Received via %(req)s") % {"req": str(receive_request)},
    )

    from dashboard.models import MovementAttachment
    for staged in receive_request.attachments.filter(attachment_type=ReceiveAttachmentType.CHARACTERIZATION):
        staged.file.open("rb")
        file_bytes = staged.file.read()
        staged.file.close()
        MovementAttachment.objects.create(
            movement=movement,
            file=ContentFile(file_bytes, name=staged.file.name.rsplit("/", 1)[-1]),
        )

    check_and_complete_receive_request(receive_request)


def check_and_complete_receive_request(receive_request):
    """If every DSRS linked to every ReceiveSource (there can be several
    per source now, one per unit) is Stored, complete the request."""

    sources = receive_request.sources.prefetch_related("result_dsrs")

    all_stored = all(
        source.result_dsrs.exists()
        and all(d.Status == SOURCE_STATUS.STORED for d in source.result_dsrs.all())
        for source in sources
    )

    if all_stored and sources.exists():
        receive_request.status = ReceiveStatus.COMPLETED
        receive_request.status_date = timezone.now()
        receive_request.save(update_fields=["status", "status_date"])