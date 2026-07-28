from django.db import transaction
from django.utils import timezone

from dashboard.models import DSRS, MovementType, SOURCE_STATUS

from ..models import LicenseSourceType


def fulfill_license_sources(license_request, performed_by):
    """
    Call this once a license is fully issued and payment is confirmed —
    NOT at specification time. This is the point where requested sources
    actually become real inventory:

      NEW      -> a brand new DSRS record is created.
      REUSED   -> 1 unit is consumed from the linked DSRS (available_count
                  drops by 1) and a REUSE movement is recorded, which moves
                  its Status from Quality Control -> Reused.
      RECYCLED -> quantity_used is consumed from each component DSRS (a
                  RECYCLE movement per component), then ONE new DSRS is
                  created representing the combined result.

    Raises ValueError if any referenced DSRS no longer has enough
    available_count — nothing is partially applied in that case, since
    everything runs inside one transaction.
    """

    with transaction.atomic():

        sources = (
            license_request.sources
            .select_related("nuclide", "source_dsrs")
            .prefetch_related("components__dsrs")
        )

        dsrs_ids = set()
        for src in sources:
            if src.source_type == LicenseSourceType.REUSED and src.source_dsrs_id:
                dsrs_ids.add(src.source_dsrs_id)
            elif src.source_type == LicenseSourceType.RECYCLED:
                for comp in src.components.all():
                    dsrs_ids.add(comp.dsrs_id)

        locked = {
            d.pk: d
            for d in DSRS.objects.select_for_update().filter(pk__in=dsrs_ids)
        }

        for src in sources:

            if src.source_type == LicenseSourceType.NEW:

                new_dsrs = DSRS.objects.create(
                    Source_Type="DSRS",
                    Facility=license_request.facility,
                    Nuclide=src.nuclide,
                    activity_input=src.activity,
                    activity_unit=src.activity_unit,
                    Activity_reference_date=src.activity_date,
                    serial_number=src.serial_number,
                    Status=SOURCE_STATUS.IN_USE,
                    Status_Date=timezone.now().date(),
                    created_by=performed_by,
                )
                src.result_dsrs = new_dsrs
                src.save(update_fields=["result_dsrs"])

            elif src.source_type == LicenseSourceType.REUSED:

                dsrs_obj = locked.get(src.source_dsrs_id)
                if dsrs_obj is None:
                    raise ValueError(f"Reused source: DSRS {src.source_dsrs_id} not found.")
                if dsrs_obj.available_count < 1:
                    raise ValueError(
                        f"DSRS {dsrs_obj.serial_number or dsrs_obj.pk}: no availability left."
                    )

                dsrs_obj.register_movement(
                    movement_type=MovementType.REUSE,
                    to_facility=license_request.facility,
                    performed_by=performed_by,
                    quantity=1,
                    remarks=f"Reused for license {license_request.pk}",
                )
                dsrs_obj.available_count -= 1
                dsrs_obj.save(update_fields=["available_count"])

                src.result_dsrs = dsrs_obj
                src.save(update_fields=["result_dsrs"])

            elif src.source_type == LicenseSourceType.RECYCLED:

                for comp in src.components.all():

                    dsrs_obj = locked.get(comp.dsrs_id)
                    if dsrs_obj is None:
                        raise ValueError(f"Recycled component: DSRS {comp.dsrs_id} not found.")
                    if comp.quantity_used > dsrs_obj.available_count:
                        raise ValueError(
                            f"DSRS {dsrs_obj.serial_number or dsrs_obj.pk}: insufficient availability."
                        )

                    dsrs_obj.register_movement(
                        movement_type=MovementType.RECYCLE,
                        to_facility=license_request.facility,
                        performed_by=performed_by,
                        quantity=comp.quantity_used,
                        remarks=f"Recycled into new source for license {license_request.pk}",
                    )
                    dsrs_obj.available_count -= comp.quantity_used
                    dsrs_obj.save(update_fields=["available_count"])

                new_dsrs = DSRS.objects.create(
                    Source_Type="DSRS",
                    Facility=license_request.facility,
                    Nuclide=src.nuclide,
                    activity_input=src.activity,
                    activity_unit=src.activity_unit,
                    Activity_reference_date=src.activity_date,
                    serial_number=src.serial_number,
                    Status=SOURCE_STATUS.IN_USE,
                    Status_Date=timezone.now().date(),
                    created_by=performed_by,
                )
                src.result_dsrs = new_dsrs
                src.save(update_fields=["result_dsrs"])