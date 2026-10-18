import os

from django.core.management.base import BaseCommand, CommandError

from operation_control import csv_import, import_services

ORDER = [  # workers first: TLD and online-dose rows refer to them
    ("workers", "workers"), ("equipment", "equipment"), ("tld", "tld"),
    ("online_doses", "online_doses"), ("plan", "inspection"),
]


class Command(BaseCommand):
    help = ("Import your Excel / CSV files from the command line - the same code as the Import CSV pages. "
            "Each option takes a .xlsx or .csv path.")

    def add_arguments(self, parser):
        parser.add_argument("--workers", help="'پرسنل' sheet of the dose workbook, or CSV")
        parser.add_argument("--equipment", help="calibration-management workbook, or CSV")
        parser.add_argument("--tld", help="'ثبت دز' sheet of the dose workbook, or CSV")
        parser.add_argument("--online-doses", dest="online_doses", help="online dose CSV")
        parser.add_argument("--plan", help="inspection-plan workbook, or CSV")
        parser.add_argument("--plan-year", type=int, help="Jalali year for the plan's done-marks (default: read from the file)")
        parser.add_argument("--dry-run", action="store_true", help="Check everything, save nothing")

    def handle(self, *args, **opts):
        jobs = [(label, kind, opts[label]) for label, kind in ORDER if opts.get(label)]
        if not jobs:
            raise CommandError("Pass at least one of --workers --equipment --tld --online-doses --plan.")
        for label, kind, path in jobs:
            self.stdout.write(self.style.MIGRATE_HEADING(f"\n{label}: {path}"))
            try:
                with open(path, "rb") as fh:
                    parsed = csv_import.parse_file(kind, os.path.basename(path), fh.read())
            except (OSError, csv_import.ImportFormatError) as e:
                raise CommandError(f"{path}: {e}")
            result = import_services.run(
                kind, parsed, user=None, dry_run=opts["dry_run"], strict=False, create_missing=True,
                plan_year=opts["plan_year"] or parsed.get("detected_year"))
            for stat, n in result["stats"]:
                self.stdout.write(f"  {stat}: {n}")
            for row, msg in result["errors"]:
                self.stdout.write(self.style.ERROR(f"  ✗ row {row}: {msg}"))
            for row, msg in result["warnings"]:
                self.stdout.write(self.style.WARNING(f"  ! row {row}: {msg}"))
            self.stdout.write(self.style.WARNING("  (dry run - nothing saved)") if opts["dry_run"]
                              else self.style.SUCCESS("  saved"))
