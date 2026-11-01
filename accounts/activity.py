from contextvars import ContextVar
from .models import ActivityLog

_request = ContextVar("current_request", default=None)


class ActivityMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = _request.set(request)
        try:
            return self.get_response(request)
        finally:
            _request.reset(token)


def _ip(request):
    fwd = request.META.get("HTTP_X_FORWARDED_FOR")
    return fwd.split(",")[0].strip() if fwd else request.META.get("REMOTE_ADDR")


def log_activity(action, obj=None, message="", changes=None, user=None):
    request = _request.get()
    user = user or (getattr(request, "user", None) if request else None)
    if user is not None and not user.is_authenticated:
        user = None
    ActivityLog.objects.create(
        user=user,
        username=getattr(user, "get_username", lambda: "")() if user else "",
        action=action,
        content_type=None if obj is None else __import__("django.contrib.contenttypes.models", fromlist=["ContentType"]).ContentType.objects.get_for_model(obj),
        object_id=str(obj.pk) if obj is not None else "",
        object_repr=str(obj)[:255] if obj is not None else "",
        changes=changes or {},
        message=message[:500],
        path=request.path[:500] if request else "",
        method=request.method if request else "",
        ip_address=_ip(request) if request else None,
    )