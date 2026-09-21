"""
Merge / Split / Conditioning for waste batches.

All three are lineage operations (see WasteBatchLineage): parent
batch(es) are consumed, child batch(es) are produced, and the link
between them is recorded so a batch's origin stays traceable.

They deliberately DON'T copy activity figures onto the child, because
activity isn't stored on WasteBatch at all any more — it's read from
the latest laboratory Analysis. A newly created child batch therefore
has NO activity until a sample is taken from it and analysed, which is
the correct answer: physically combining or splitting waste changes the
activity distribution, so the parents' old numbers don't describe the
child. Take a fresh sample after any of these operations.
"""

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from ..models import (
    BatchStatus,
    LineageOperation,
    WasteBatch,
    WasteBatchLineage,
    WasteMovementType,
    WasteState,
    WasteType,
)


def _consume(batch, movement_type, performed_by, remarks):
    """Marks a parent batch as fully consumed by a lineage operation."""
    batch.register_movement(
        movement_type=movement_type,
        to_facility=batch.facility,
        from_facility=batch.facility,
        performed_by=performed_by,
        remarks=remarks,
        mass_kg=batch.mass_kg,
        volume_m3=batch.volume_m3,
    )


@transaction.atomic
def merge_batches(parents, new_waste_id, performed_by, remarks="", **child_overrides):
    """
    Many parents -> one child. Example: two 5 m³ liquid batches poured
    into one tank.

    Mass/volume of the child default to the SUM of the parents; pass
    mass_kg / volume_m3 in child_overrides to record measured values
    instead (they rarely add up exactly in practice).
    """

    parents = list(parents)
    if len(parents) < 2:
        raise ValueError(_("Merging requires at least two batches."))

    types = {p.waste_type for p in parents}
    if len(types) > 1:
        raise ValueError(_("Cannot merge batches of different waste types."))

    states = {p.waste_state for p in parents}
    if len(states) > 1:
        raise ValueError(_("Cannot merge processed and unprocessed batches."))

    facilities = {p.facility_id for p in parents}
    if len(facilities) > 1:
        raise ValueError(_("Cannot merge batches held at different facilities."))

    for p in parents:
        if p.status == BatchStatus.CONSUMED:
            raise ValueError(
                _("Batch %(id)s has already been consumed by another operation.") % {"id": p.waste_id}
            )

    reference = parents[0]

    total_mass = sum((p.mass_kg or 0) for p in parents) or None
    total_volume = sum((p.volume_m3 or 0) for p in parents) or None

    # Worst (highest) waste class among the parents wins.
    class_rank = {"VLLW": 0, "LLW": 1, "ILW": 2, "HLW": 3}
    parent_classes = [p.waste_class for p in parents if p.waste_class]
    merged_class = max(parent_classes, key=lambda c: class_rank.get(c, -1)) if parent_classes else None

    child_data = {
        "waste_id": new_waste_id,
        "waste_type": reference.waste_type,
        "waste_class": merged_class,
        "waste_state": reference.waste_state,
        "facility": reference.facility,
        "origin_facility": reference.facility,
        "origin_of_waste": reference.origin_of_waste,
        "date_received": timezone.now().date(),
        "mass_kg": total_mass,
        "volume_m3": total_volume,
        "container_type": reference.container_type,
        "material": reference.material,
        "status": BatchStatus.STORED,
        "status_date": timezone.now().date(),
        "created_by": performed_by,
    }
    child_data.update(child_overrides)

    child = WasteBatch.objects.create(**child_data)

    for parent in parents:
        WasteBatchLineage.objects.create(
            parent=parent,
            child=child,
            operation=LineageOperation.MERGE,
            mass_kg=parent.mass_kg,
            volume_m3=parent.volume_m3,
            performed_by=performed_by,
            remarks=remarks,
        )
        _consume(
            parent, WasteMovementType.MERGE, performed_by,
            _("Merged into %(id)s") % {"id": child.waste_id},
        )

    return child


@transaction.atomic
def split_batch(parent, portions, performed_by, remarks=""):
    """
    Splits one or more portions OFF a parent batch. Unlike before, this
    is no longer all-or-nothing: the parent's mass/volume is reduced by
    whatever was taken, and the parent stays STORED (fully usable —
    splittable and mergeable again) as long as anything measurable
    remains. It only becomes CONSUMED once its mass AND volume (whichever
    are tracked) are fully exhausted by one or more of these calls over
    time — there's no separate "close" action needed.

    `portions` is a list of dicts, each REQUIRING "waste_id" and
    optionally mass_kg / volume_m3 / any other WasteBatch field to
    override. A single portion is a valid call (take one piece now,
    leave the rest for later).
    """

    if len(portions) < 1:
        raise ValueError(_("Provide at least one portion to split off."))

    if parent.status == BatchStatus.CONSUMED:
        raise ValueError(
            _("Batch %(id)s has already been fully consumed.") % {"id": parent.waste_id}
        )

    requested_mass = sum((p.get("mass_kg") or 0) for p in portions)
    requested_volume = sum((p.get("volume_m3") or 0) for p in portions)

    if parent.mass_kg is not None and requested_mass > parent.mass_kg:
        raise ValueError(
            _("Requested %(req)s kg but only %(have)s kg remains on this batch.")
            % {"req": requested_mass, "have": parent.mass_kg}
        )
    if parent.volume_m3 is not None and requested_volume > parent.volume_m3:
        raise ValueError(
            _("Requested %(req)s m³ but only %(have)s m³ remains on this batch.")
            % {"req": requested_volume, "have": parent.volume_m3}
        )

    children = []

    for portion in portions:

        if not portion.get("waste_id"):
            raise ValueError(_("Every split portion needs a waste ID."))

        child_data = {
            "waste_type": parent.waste_type,
            "waste_class": parent.waste_class,
            "waste_state": parent.waste_state,
            "facility": parent.facility,
            "origin_facility": parent.facility,
            "origin_of_waste": parent.origin_of_waste,
            "date_received": timezone.now().date(),
            "container_type": parent.container_type,
            "material": parent.material,
            "status": BatchStatus.STORED,
            "status_date": timezone.now().date(),
            "created_by": performed_by,
        }
        child_data.update(portion)

        child = WasteBatch.objects.create(**child_data)
        children.append(child)

        WasteBatchLineage.objects.create(
            parent=parent,
            child=child,
            operation=LineageOperation.SPLIT,
            mass_kg=child.mass_kg,
            volume_m3=child.volume_m3,
            performed_by=performed_by,
            remarks=remarks,
        )

    # Deduct what was taken from the parent's remaining mass/volume —
    # this is what makes the split partial rather than all-or-nothing.
    if parent.mass_kg is not None:
        parent.mass_kg = parent.mass_kg - requested_mass
    if parent.volume_m3 is not None:
        parent.volume_m3 = parent.volume_m3 - requested_volume

    # Figure out whether anything measurable is left. If NEITHER
    # mass_kg nor volume_m3 is tracked on this batch, there's no way to
    # know what "remaining" means, so it's treated as fully taken (the
    # old, only-possible, all-or-nothing behavior).
    if parent.mass_kg is None and parent.volume_m3 is None:
        fully_consumed = True
    else:
        mass_remaining = parent.mass_kg if parent.mass_kg is not None else 0
        volume_remaining = parent.volume_m3 if parent.volume_m3 is not None else 0
        fully_consumed = mass_remaining <= 0 and volume_remaining <= 0

    parent_remarks = _("Split off %(ids)s") % {"ids": ", ".join(c.waste_id for c in children)}

    if fully_consumed:
        parent.save(update_fields=["mass_kg", "volume_m3"])
        _consume(parent, WasteMovementType.SPLIT, performed_by, parent_remarks)
    else:
        # Record the movement WITHOUT going through register_movement's
        # automatic status mapping — SPLIT maps to CONSUMED there, which
        # is wrong for a partial split. The batch stays STORED and fully
        # usable (splittable/mergeable again) at its own facility.
        parent.movements.create(
            movement_type=WasteMovementType.SPLIT,
            from_facility=parent.facility,
            to_facility=parent.facility,
            movement_date=timezone.now().date(),
            performed_by=performed_by,
            mass_kg=requested_mass,
            volume_m3=requested_volume,
            remarks=parent_remarks,
        )
        parent.status_date = timezone.now().date()
        parent.save(update_fields=["mass_kg", "volume_m3", "status_date"])

    return children


@transaction.atomic
def condition_batch(parent, new_waste_id, performed_by, remarks="", **child_overrides):
    """
    Conditioning: treat + immobilise + package a batch. Per your
    description this always produces a PROCESSED SOLID record — even
    from a liquid parent, since cementation/solidification is exactly
    what turns liquid waste into a solid package.

    The processed-only fields (pretreatment, treatment, package_type,
    waste_matrix, and for liquid parents waste_to_matrix_ratio /
    waste_mass_kg / package_mass_kg / package_volume_m3) are passed in
    via child_overrides — that's the data the operator fills in on the
    conditioning form.
    """

    if parent.status == BatchStatus.CONSUMED:
        raise ValueError(
            _("Batch %(id)s has already been consumed by another operation.") % {"id": parent.waste_id}
        )

    child_data = {
        "waste_id": new_waste_id,
        "waste_type": WasteType.SOLID,
        "waste_state": WasteState.PROCESSED,
        "waste_class": parent.waste_class,
        "facility": parent.facility,
        "origin_facility": parent.facility,
        # Conditioning output is waste generated BY processing, not
        # received — this is exactly what OriginOfWaste.PROCESSING is for.
        "origin_of_waste": "PROCESSING",
        "date_received": timezone.now().date(),
        "material": parent.material,
        "status": BatchStatus.STORED,
        "status_date": timezone.now().date(),
        "created_by": performed_by,
        # Carry the liquid parent's own mass across as the waste (not
        # package) mass, so the waste-to-matrix picture stays sensible.
        "waste_mass_kg": parent.mass_kg,
    }
    child_data.update(child_overrides)

    child = WasteBatch.objects.create(**child_data)

    WasteBatchLineage.objects.create(
        parent=parent,
        child=child,
        operation=LineageOperation.CONDITIONING,
        mass_kg=parent.mass_kg,
        volume_m3=parent.volume_m3,
        performed_by=performed_by,
        remarks=remarks,
    )

    _consume(
        parent, WasteMovementType.CONDITIONING, performed_by,
        _("Conditioned into %(id)s") % {"id": child.waste_id},
    )

    return child