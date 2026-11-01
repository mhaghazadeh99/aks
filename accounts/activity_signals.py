import logging

from django.conf import settings
from django.db.models.signals import post_save, pre_delete, pre_save

from .activity import is_tracking, record, snapshot
from .models import ActivityLog

logger = logging.getLogger(__name__)
A = ActivityLog.Action

# Never logged: the log's own tables (would recurse) and framework noise.
ALWAYS_EXCLUDED = {
    "accounts.activitylog",
    "accounts.activityarchive",
    "accounts.trackeduser",
    "sessions.session",
    "admin.logentry",
    "contenttypes.contenttype",
    "migrations.migration",
}
EXCLUDED = ALWAYS_EXCLUDED | {m.lower() for m in getattr(settings, "ACTIVITY_EXCLUDE_MODELS", [])}
# last_login changes on every login, and you don't want login activity in the log
IGNORED_FIELDS = {"last_login"} | set(getattr(settings, "ACTIVITY_IGNORE_FIELDS", []))


def _skip(sender):
    return sender._meta.label_lower in EXCLUDED or not is_tracking()


def _before_save(sender, instance, raw=False, **kw):
    instance._activity_before = None
    if raw or not instance.pk or _skip(sender):
        return
    try:
        old = sender._base_manager.filter(pk=instance.pk).first()
        if old:
            instance._activity_before = snapshot(old)
    except Exception:
        logger.exception("Activity log: could not read old version of %r", instance)


def _after_save(sender, instance, created, raw=False, **kw):
    if raw or _skip(sender):
        return
    try:
        if created:
            record(A.CREATE, instance)
            return
        before = getattr(instance, "_activity_before", None)
        if not before:
            return
        after = snapshot(instance)
        changes = {
            k: [before.get(k), v]
            for k, v in after.items()
            if k not in IGNORED_FIELDS and before.get(k) != v
        }
        if changes:
            record(A.UPDATE, instance, data_before=before, changes=changes)
    except Exception:
        # logging must never break the user's actual save
        logger.exception("Activity log: could not record change to %r", instance)


def _before_delete(sender, instance, **kw):
    if _skip(sender):
        return
    try:
        record(A.DELETE, instance, data_before=snapshot(instance))
    except Exception:
        logger.exception("Activity log: could not record deletion of %r", instance)


# No sender = every model. Only requests from tracked users are recorded.
pre_save.connect(_before_save, weak=False, dispatch_uid="activity-pre-save")
post_save.connect(_after_save, weak=False, dispatch_uid="activity-post-save")
pre_delete.connect(_before_delete, weak=False, dispatch_uid="activity-pre-delete")
