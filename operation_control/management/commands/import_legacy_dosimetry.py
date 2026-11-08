from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from operation_control import import_services, legacy_sql


class Command(BaseCommand):
    help = ("Read dosimetry data straight from the OLD SQL Server database (read-only SELECTs) and import it. "
            "Run with --dry-run first: it shows what would happen and saves nothing.")

    def add_arguments(self, parser):
        parser.add_argument("--connection", help="pyodbc connection string. Default: settings.OPERATION_CONTROL_LEGACY_SQL")
        parser.add_argument("--server", help="SQL Server name, e.g. localhost or .\\SQLEXPRESS (alternative to --connection)")
        parser.add_argument("--database", default="HealthPhysics")
        parser.add_argument("--user", help="SQL login (omit to use the Windows account)")
        parser.add_argument("--password")
        parser.add_argument("--driver", help="ODBC driver name (default: the best installed one is found automatically)")
        parser.add_argument("--tld", action="store_true", help="import TLD readings (TLD + DateD + Personnels tables)")
        parser.add_argument("--online", action="store_true",
                            help="import online doses (OnlineDose + PlaceofActivity + Center + Personnels tables)")
        parser.add_argument("--online-unit", choices=["usv", "msv"], default="usv",
                            help="unit of the old OnlineDose.Dose values (the table does not say). Default: usv")
        parser.add_argument("--unmatched", choices=["env", "skip"], default="env",
                            help="personnel that match no worker: 'env' = create environmental points (default), 'skip'")
        parser.add_argument("--dry-run", action="store_true", help="check everything, save nothing")
        parser.add_argument("--print-sql", action="store_true", help="only print the queries that would be run")

    def handle(self, *args, **opts):
        kinds = [k for k in ("tld", "online") if opts[k]]
        if not kinds:
            raise CommandError("Say what to import: --tld and/or --online")
        if opts["print_sql"]:
            for k in kinds:
                self.stdout.write(legacy_sql.QUERIES[k])
            return
        connection = opts["connection"] or getattr(settings, "OPERATION_CONTROL_LEGACY_SQL", None)
        if not connection and not opts["server"]:
            raise CommandError(
                "No connection. Pass --server NAME (the easy way), or --connection, or set OPERATION_CONTROL_LEGACY_SQL in settings, e.g.\n"
                "  DRIVER={ODBC Driver 17 for SQL Server};SERVER=localhost;DATABASE=HealthPhysics;Trusted_Connection=yes;\n"
                "  DRIVER={ODBC Driver 17 for SQL Server};SERVER=host;DATABASE=HealthPhysics;UID=user;PWD=secret;")
        for kind in kinds:
            self.stdout.write(self.style.MIGRATE_HEADING(f"\n{kind}: reading the old database ..."))
            try:
                if opts["server"]:
                    rows = legacy_sql.fetch_auto(opts["server"], legacy_sql.QUERIES[kind], opts["database"],
                                                 opts["user"], opts["password"], opts["driver"])
                else:
                    rows = legacy_sql.fetch(connection, legacy_sql.QUERIES[kind])
            except Exception as e:                                     # driver / login / network problems
                raise CommandError(f"Could not read the old database: {e}")
            self.stdout.write(f"  {len(rows)} rows read")
            result = import_services.run(
                "legacy_" + kind, {"items": rows, "errors": [], "warnings": []}, user=None,
                dry_run=opts["dry_run"], strict=False, create_missing=opts["unmatched"] == "env" or kind == "online",
                legacy_unit=opts["online_unit"].upper())
            for stat, n in result["stats"]:
                self.stdout.write(f"  {stat}: {n}")
            for line in result["info"]:
                self.stdout.write(f"  · {line}")
            for row, msg in result["errors"]:
                self.stdout.write(self.style.ERROR(f"  ✗ row {row}: {msg}"))
            for row, msg in result["warnings"]:
                self.stdout.write(self.style.WARNING(f"  ! row {row}: {msg}"))
            self.stdout.write(self.style.WARNING("  (dry run - nothing saved)") if opts["dry_run"] else self.style.SUCCESS("  saved"))
