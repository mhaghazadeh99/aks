import gzip
import json
from datetime import date, timedelta
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from accounts.models import ActivityArchive, ActivityLog


class Command(BaseCommand):
    help = "Move activity logs older than ACTIVITY_ARCHIVE_AFTER_DAYS into monthly .jsonl.gz files."

    def handle(self, *args, **opts):
        days = getattr(settings, "ACTIVITY_ARCHIVE_AFTER_DAYS", 30)
        cutoff = timezone.now() - timedelta(days=days)
        folder = Path(settings.ACTIVITY_ARCHIVE_DIR)
        folder.mkdir(parents=True, exist_ok=True)

        qs = (ActivityLog.objects.filter(timestamp__lt=cutoff)
              .select_related("content_type").order_by("timestamp"))
        total = 0
        while True:
            batch = list(qs[:2000])
            if not batch:
                break
            by_month = {}
            for log in batch:
                local = timezone.localtime(log.timestamp)
                by_month.setdefault((local.year, local.month), []).append(log)

            for (year, month), logs in by_month.items():
                path = folder / f"activity_{year}-{month:02d}.jsonl.gz"
                # 1) write to the file first
                with gzip.open(path, "at", encoding="utf-8") as fh:
                    for l in logs:
                        ct = l.content_type
                        fh.write(json.dumps({
                            "id": l.pk, "timestamp": l.timestamp.isoformat(),
                            "user_id": l.user_id, "username": l.username, "action": l.action,
                            "model": f"{ct.app_label}.{ct.model}" if ct else None,
                            "object_id": l.object_id, "object_repr": l.object_repr,
                            "changes": l.changes, "data_before": l.data_before,
                            "path": l.path, "method": l.method, "ip_address": l.ip_address,
                        }, ensure_ascii=False) + "\n")
                # 2) only then remove the rows from the database
                with transaction.atomic():
                    ActivityLog.objects.filter(pk__in=[l.pk for l in logs]).delete()
                    arch, _ = ActivityArchive.objects.get_or_create(
                        month=date(year, month, 1), defaults={"file_path": str(path)})
                    ActivityArchive.objects.filter(pk=arch.pk).update(
                        row_count=F("row_count") + len(logs), size_bytes=path.stat().st_size)
                total += len(logs)

        self.stdout.write(f"Archived {total} log rows.")
