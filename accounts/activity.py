import json
from contextvars import ContextVar

from django.contrib.contenttypes.models import ContentType
from django.core import serializers

from .models import ActivityLog, TrackedUser

_request = ContextVar("current_request", default=None)


class ActivityMiddleware:
    """Keeps the current request available to the signal handlers."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = _request.set(request)
        try:
            return self.get_response(request)
        finally:
            _request.reset(token)


def _tracked_user():
    """Return (user, request) only if the current user is one you chose to track."""
    request = _request.get()
    user = getattr(request, "user", None)
    if request is None or user is None or not user.is_authenticated:
        return None, request
    if not hasattr(request, "_activity_tracked"):
        request._activity_tracked = TrackedUser.objects.filter(user=user).exists()
    return (user if request._activity_tracked else None), request


def is_tracking():
    return _tracked_user()[0] is not None


def snapshot(obj):
    """Full JSON-safe copy of a record's fields."""
    return json.loads(serializers.serialize("json", [obj]))[0]["fields"]


def record(action, obj, data_before=None, changes=None):
    user, request = _tracked_user()
    if user is None:
        return
    fwd = request.META.get("HTTP_X_FORWARDED_FOR")
    ActivityLog.objects.create(
        user=user,
        username=user.get_username(),
        action=action,
        content_type=ContentType.objects.get_for_model(obj),
        object_id=str(obj.pk),
        object_repr=str(obj)[:255],
        changes=changes,
        data_before=data_before,
        path=request.path[:500],
        method=request.method,
        ip_address=(fwd.split(",")[0].strip() if fwd else request.META.get("REMOTE_ADDR")),
    )
