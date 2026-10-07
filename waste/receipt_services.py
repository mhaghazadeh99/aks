from decimal import ROUND_DOWN, Decimal

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from .models import (MaterialType, OriginOfWaste, PackageType, WasteBatch, WasteMovementAttachment,
                     WasteMovementType, WasteState, WasteType)
from .models_receipt import ReceiptStatus, WasteIdCounter, WasteReceipt, WasteReceiptPackage

MATERIAL_CODE = {
    MaterialType.LIQUID: "LQ", MaterialType.LIGHTWEIGHT: "LW", MaterialType.HEAVY: "HV",
    MaterialType.FILTERS: "FL", MaterialType.RESINS: "RS", MaterialType.BIOLOGICAL: "BI",
    MaterialType.CHARCOAL: "CH", MaterialType.OTHER: "OT", MaterialType.SPECIAL_OTHER: "SO",
    MaterialType.SOIL_SEDIMENTS_SLUDGE: "SS",
}
PACKAGE_CODE = {
    PackageType.BAG: "BG", PackageType.LARGE_BIN: "LB", PackageType.SMALL_BIN: "SB", PackageType.BOX: "BX",
    PackageType.CONTAINER: "CT", PackageType.DRUM: "DR", PackageType.NON_STANDARD: "NS", PackageType.CAN: "CN",
    PackageType.SMALL_PIPE: "SP", PackageType.LIQUID: "LQ",
}


def next_waste_id(material, package_type):
    """LW-BG-0001, LW-BG-0002, ... (counter is per material+package prefix).
    Call inside transaction.atomic(): the counter row is locked, so two users
    finalizing at the same moment can never get the same number.
    For ONE global counter instead, use prefix='GLOBAL' and format f"{m}-{p}-{n:05d}"."""
    prefix = f"{MATERIAL_CODE[material]}-{PACKAGE_CODE[package_type]}"
    counter, created = WasteIdCounter.objects.select_for_update().get_or_create(prefix=prefix)
    counter.last_value += 1
    counter.save(update_fields=["last_value"])
    return f"{prefix}-{counter.last_value:04d}"


def split_evenly(total, n, places="0.001"):
    """Share a line total over n packages. All but the last get total/n rounded down;
    the last takes the remainder, so the parts always add up to the total exactly."""
    if total is None:
        return [None] * n
    total = Decimal(total)
    each = (total / n).quantize(Decimal(places), rounding=ROUND_DOWN)
    return [each] * (n - 1) + [total - each * (n - 1)]


class ReceiptError(Exception):
    pass


@transaction.atomic
def finalize_receipt(receipt_id, user):
    receipt = (WasteReceipt.objects
               .select_for_update(of=("self",))   # of=self: Postgres can't lock joined rows
               .select_related("facility", "origin_facility").get(pk=receipt_id))

    # ---- guards ----
    if receipt.status != ReceiptStatus.MINUTES_READY:
        raise ReceiptError(_("Only a receipt whose minutes are ready can be finalized."))
    if not receipt.signed_minutes_file:
        raise ReceiptError(_("Upload the signed minutes first."))
    if not receipt.delivery_date:
        raise ReceiptError(_("Delivery date is missing."))
    lines = list(receipt.lines.select_for_update().all())
    if not lines:
        raise ReceiptError(_("The receipt has no material lines."))
    for ln in lines:
        if ln.batch_id or ln.packages.exists():
            raise ReceiptError(_("This receipt already produced waste records."))
        if ln.mass_kg is None and ln.volume_m3 is None:
            raise ReceiptError(_("Line %(material)s / %(package)s: enter mass or volume.") % {
                "material": ln.get_material_display(), "package": ln.get_package_type_display()})

    liquid = receipt.waste_type == WasteType.LIQUID

    # ---- SOLID: one WasteBatch per PACKAGE.  LIQUID: one per line (a stream). ----
    for ln in lines:
        n = 1 if liquid else max(ln.package_count, 1)
        masses = split_evenly(ln.mass_kg, n)
        volumes = split_evenly(ln.volume_m3, n)

        for i in range(n):
            batch = WasteBatch(
                waste_id=next_waste_id(ln.material, ln.package_type),
                waste_type=receipt.waste_type,
                waste_state=WasteState.UNPROCESSED,
                facility=receipt.facility,
                origin_facility=receipt.origin_facility,
                origin_of_waste=OriginOfWaste.RECEIVED,
                date_received=receipt.delivery_date,
                description=receipt.description or None,
                waste_arising_from=(receipt.waste_origin_place or None),
                material=ln.material,
                package_type=ln.package_type,
                mass_kg=masses[i],
                volume_m3=volumes[i],
                dose_rate_surface_uSv=ln.surface_dose_uSv,     # the line's reading applies to each package
                dose_rate_date=receipt.delivery_date,
                ph=ln.ph if liquid else None,
                density=ln.density if liquid else None,
                hardness=ln.hardness if liquid else None,
                created_by=user,
            )
            batch.full_clean(exclude=["created_by"])
            batch.save()

            remark = f"Letter {receipt.letter_number}; minutes {receipt.minutes_number}"
            if not liquid:
                remark += f"; package {i + 1}/{n}"
            movement = batch.register_movement(
                WasteMovementType.RECEIVE,
                to_facility=receipt.facility,
                from_facility=receipt.origin_facility,
                performed_by=user,
                movement_date=receipt.delivery_date,
                mass_kg=masses[i],
                volume_m3=volumes[i],
                remarks=remark,
            )
            WasteMovementAttachment.objects.create(movement=movement, file=receipt.signed_minutes_file.name)

            if liquid:
                ln.batch = batch
                ln.save(update_fields=["batch"])
            else:
                WasteReceiptPackage.objects.create(line=ln, sequence=i + 1, batch=batch)

    receipt.status = ReceiptStatus.FINALIZED
    receipt.finalized_at = timezone.now()
    receipt.finalized_by = user
    receipt.save(update_fields=["status", "finalized_at", "finalized_by", "updated_at"])
    return receipt


def planned_batch_count(receipt):
    """How many waste records finalizing will create (shown on the finalize page)."""
    if receipt.waste_type == WasteType.LIQUID:
        return receipt.lines.count()
    return sum(max(ln.package_count, 1) for ln in receipt.lines.all())


# ------------------------------------------------ context for docx_export
def _jalali(d):
    if not d:
        return ""
    import jdatetime                      # installed with your jalali package
    return jdatetime.date.fromgregorian(date=d).strftime("%Y/%m/%d")


def receipt_to_context(r):
    def f(v):
        return None if v is None else float(v)
    d = _jalali(r.delivery_date)
    dose = lambda v: f"{v} µSv/h" if v is not None else ""
    return {
        "minutes_date": _jalali(r.minutes_date), "minutes_number": r.minutes_number,
        "origin_facility": str(r.origin_facility), "laboratory": r.laboratory,
        "request_date": _jalali(r.letter_date), "request_number": r.letter_number,
        "delivery_date": d, "radionuclides": r.nuclide_names,
        "waste_origin_place": r.waste_origin_place, "description": r.description,
        "cabin_dose": dose(r.cabin_dose_uSv), "container_dose": dose(r.container_dose_uSv),
        "deliverer": {"name": r.deliverer_name, "position": r.deliverer_position, "date": d},
        "receiver": {"name": r.receiver_name, "position": r.receiver_position, "date": d},
        "lines": [{
            "material": l.material, "package_type": l.package_type, "package_count": l.package_count,
            "mass_kg": f(l.mass_kg), "volume_m3": f(l.volume_m3), "surface_dose": f(l.surface_dose_uSv),
            "half_life": l.half_life, "half_life_class": l.half_life_class,
            "alpha": f(l.alpha_bq_l), "beta": f(l.beta_bq_l), "gamma": f(l.gamma_bq_l),
            "ph": f(l.ph), "density": f(l.density), "hardness": f(l.hardness),
        } for l in r.lines.all()],
    }