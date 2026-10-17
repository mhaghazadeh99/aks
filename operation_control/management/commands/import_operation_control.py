from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from operation_control import importers
from operation_control import jalali_utils as ju
from operation_control.models import (
    CalibrationRecord, Equipment, EquipmentApplication, InspectionItem,
    InspectionPlanYear, InspectionRecord,
)


class Command(BaseCommand):
    help = "Import the legacy Excel files (equipment calibration list, inspection plan)."

    def add_arguments(self, parser):
        parser.add_argument("--equipment", help="Path to the calibration-management .xlsx")
        parser.add_argument("--plan", help="Path to the inspection-plan .xlsx")
        parser.add_argument("--plan-year", type=int, default=1405)
        parser.add_argument("--dry-run", action="store_true", help="Parse and write, then roll back")

    @transaction.atomic
    def handle(self, *args, **opts):
        if not opts["equipment"] and not opts["plan"]:
            raise CommandError("Pass --equipment and/or --plan.")
        if opts["equipment"]:
            self._equipment(opts["equipment"])
        if opts["plan"]:
            self._plan(opts["plan"], opts["plan_year"])
        if opts["dry_run"]:
            transaction.set_rollback(True)
            self.stdout.write(self.style.WARNING("Dry run - nothing was saved."))

    def _warn(self, warnings):
        for w in warnings:
            self.stdout.write(self.style.WARNING("  ! " + w))

    def _equipment(self, path):
        rows, warnings = importers.read_equipment(path)
        created = updated = records = 0
        for r in rows:
            app = None
            if r["application"]:
                app, _ = EquipmentApplication.objects.get_or_create(
                    name=r["application"],
                    defaults={"is_personal_dosimetry": "دوزیمتری" in r["application"] and "پرسنلی" in r["application"]},
                )
            eq, was_created = Equipment.objects.update_or_create(
                equipment_id=r["equipment_id"],
                defaults=dict(
                    name=r["name"], model_name=r["model_name"], serial_number=r["serial_number"],
                    manufacturer=r["manufacturer"], application=app, status=r["status"],
                    loan_to=r["loan_to"], center=r["center"], current_location=r["current_location"],
                    calibration_period_months=r["period_months"], current_label=r["label"], notes=r["notes"],
                ),
            )
            created, updated = created + was_created, updated + (not was_created)
            if r["last_calibration"]:
                _, rec_created = CalibrationRecord.objects.get_or_create(
                    equipment=eq, calibration_date=ju.from_jalali(*r["last_calibration"]),
                    defaults={"certificate_number": r["certificate_number"], "laboratory": r["laboratory"]},
                )
                records += rec_created
        self.stdout.write(self.style.SUCCESS(
            f"Equipment: {created} created, {updated} updated, {records} calibration records."))
        self._warn(warnings)

    def _plan(self, path, year):
        items, warnings = importers.read_plan(path)
        plan_year, _ = InspectionPlanYear.objects.get_or_create(year=year, defaults={"first_month": 2})
        n_items = n_records = 0
        for i in items:
            item, was_created = InspectionItem.objects.update_or_create(
                title=i["title"], area=i["area"],
                defaults=dict(form_title=i["form_title"], form_code=i["form_code"], period_weeks=i["period_weeks"]),
            )
            n_items += was_created
            for week in i["done_weeks"]:
                _, rec_created = InspectionRecord.objects.get_or_create(
                    item=item, plan_year=plan_year, week_index=week)
                n_records += rec_created
        self.stdout.write(self.style.SUCCESS(
            f"Inspection plan {year}: {n_items} new items, {n_records} done-marks imported."))
        self._warn(warnings)

