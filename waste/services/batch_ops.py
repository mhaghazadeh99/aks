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
    ConditioningIngredient,
    ConditioningMaterial,
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
    Splits one or more portions OFF a parent batch. The parent's
    mass/volume is reduced by whatever was taken, and the parent stays
    STORED as long as anything measurable remains — it only becomes
    CONSUMED once its tracked mass/volume is fully exhausted.

    `portions` is a list of dicts, each REQUIRING "waste_id" and
    optionally mass_kg / volume_m3 / any other WasteBatch field.
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

    if parent.mass_kg is not None:
        parent.mass_kg = parent.mass_kg - requested_mass
    if parent.volume_m3 is not None:
        parent.volume_m3 = parent.volume_m3 - requested_volume

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


# =====================================================================
# Conditioning ingredients
#
# Each ingredient row carries EITHER a mass, a volume, or both; if only
# one is given together with a density, the other is derived. The waste
# itself is entered as one row with material=WASTE (defaults to the
# parent batch's mass/volume) so "waste-to-matrix ratio" falls out of
# the same totals as everything else, with no special-casing.
# =====================================================================

def compute_conditioning_totals(ingredients):
    """
    ingredients: list of (unsaved) ConditioningIngredient instances.
    Returns {package_mass_kg, package_volume_m3, waste_mass_kg,
             waste_to_matrix_ratio, warnings}.
    """
    total_mass = 0.0
    total_volume_l = 0.0
    waste_mass = 0.0
    matrix_mass = 0.0
    warnings = []

    for ing in ingredients:
        mass = ing.resolved_mass_kg
        volume = ing.resolved_volume_l
        label = ing.material_other or ing.get_material_display()

        if mass is None and volume is None:
            warnings.append(_("%(label)s: no mass or volume given — left out of the totals.") % {"label": label})
            continue

        if mass is not None:
            total_mass += float(mass)
            if ing.material == ConditioningMaterial.WASTE:
                waste_mass += float(mass)
            else:
                matrix_mass += float(mass)
        else:
            warnings.append(
                _("%(label)s: only a volume was given, with no density — its mass isn't counted "
                  "in the package total or the waste-to-matrix ratio.") % {"label": label}
            )

        if volume is not None:
            total_volume_l += float(volume)

    return {
        "package_mass_kg": round(total_mass, 3) if total_mass else None,
        "package_volume_m3": round(total_volume_l / 1000, 5) if total_volume_l else None,
        "waste_mass_kg": round(waste_mass, 3) if waste_mass else None,
        "waste_to_matrix_ratio": round(waste_mass / matrix_mass, 4) if matrix_mass else None,
        "warnings": warnings,
    }


@transaction.atomic
def condition_batch(parent, new_waste_id, performed_by, ingredients=None, remarks="", **child_overrides):
    """
    Conditioning: treat + immobilise + package a batch. Always produces
    a PROCESSED SOLID record — even from a liquid parent, since
    cementation/solidification is exactly what turns liquid waste into
    a solid package.

    `ingredients`: optional list of unsaved ConditioningIngredient
    instances (cement, water, NaOH, microsilica, Penetron, the waste
    itself, …). When given, the package's mass_kg / volume_m3 /
    waste_mass_kg / waste_to_matrix_ratio are CALCULATED from them —
    an explicit value in child_overrides (a measured final weight, say)
    always wins over the calculated one. The ingredient rows themselves
    are saved against the resulting lineage record once the child batch
    is created.
    """

    if parent.status == BatchStatus.CONSUMED:
        raise ValueError(
            _("Batch %(id)s has already been consumed by another operation.") % {"id": parent.waste_id}
        )

    computed = {}
    if ingredients:
        totals = compute_conditioning_totals(ingredients)
        if totals["package_mass_kg"] is not None:
            computed["mass_kg"] = totals["package_mass_kg"]
            computed["package_mass_kg"] = totals["package_mass_kg"]
        if totals["package_volume_m3"] is not None:
            computed["volume_m3"] = totals["package_volume_m3"]
            computed["package_volume_m3"] = totals["package_volume_m3"]
        if totals["waste_mass_kg"] is not None:
            computed["waste_mass_kg"] = totals["waste_mass_kg"]
        if totals["waste_to_matrix_ratio"] is not None:
            computed["waste_to_matrix_ratio"] = totals["waste_to_matrix_ratio"]

    child_data = {
        "waste_id": new_waste_id,
        "waste_type": WasteType.SOLID,
        "waste_state": WasteState.PROCESSED,
        "waste_class": parent.waste_class,
        "facility": parent.facility,
        "origin_facility": parent.facility,
        # Conditioning output is waste generated BY processing, not received.
        "origin_of_waste": "PROCESSING",
        "date_received": timezone.now().date(),
        "material": parent.material,
        "status": BatchStatus.STORED,
        "status_date": timezone.now().date(),
        "created_by": performed_by,
        "waste_mass_kg": parent.mass_kg,  # default, overridden by computed/child_overrides below
    }
    child_data.update(computed)
    child_data.update(child_overrides)

    child = WasteBatch.objects.create(**child_data)

    lineage = WasteBatchLineage.objects.create(
        parent=parent,
        child=child,
        operation=LineageOperation.CONDITIONING,
        mass_kg=parent.mass_kg,
        volume_m3=parent.volume_m3,
        performed_by=performed_by,
        remarks=remarks,
    )

    if ingredients:
        for ing in ingredients:
            ing.lineage = lineage
        ConditioningIngredient.objects.bulk_create(ingredients)

    _consume(
        parent, WasteMovementType.CONDITIONING, performed_by,
        _("Conditioned into %(id)s") % {"id": child.waste_id},
    )

    return child