from datetime import timedelta
from pathlib import Path

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.paginator import Paginator
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

from .models import ActivityArchive, ActivityLog


@staff_member_required
def activity_log(request):
    qs = ActivityLog.objects.select_related("user", "content_type")
    user_ids = request.GET.getlist("user")
    if user_ids:
        qs = qs.filter(user_id__in=user_ids)
    if v := request.GET.get("action"):
        qs = qs.filter(action=v)
    if v := request.GET.get("model"):
        qs = qs.filter(content_type_id=v)
    if v := request.GET.get("from"):
        qs = qs.filter(timestamp__date__gte=v)
    if v := request.GET.get("to"):
        qs = qs.filter(timestamp__date__lte=v)
    if v := request.GET.get("q"):
        qs = qs.filter(object_repr__icontains=v)

    params = request.GET.copy()
    params.pop("page", None)
    return render(request, "accounts/activity_log.html", {
        "page": Paginator(qs, 50).get_page(request.GET.get("page")),
        "users": get_user_model().objects.filter(activity_logs__isnull=False).distinct().order_by("username"),
        "models": ContentType.objects.filter(activitylog__isnull=False).distinct(),
        "actions": ActivityLog.Action.choices,
        "selected_users": user_ids,
        "querystring": params.urlencode(),
    })


def _expiry_limit():
    return (timezone.localdate() - timedelta(days=365)).replace(day=1)


@staff_member_required
def activity_archives(request):
    limit = _expiry_limit()
    archives = list(ActivityArchive.objects.all())
    for a in archives:
        a.expired = a.month < limit
    return render(request, "accounts/activity_archives.html", {"archives": archives})


@staff_member_required
def activity_archive_download(request, pk):
    archive = get_object_or_404(ActivityArchive, pk=pk)
    path = Path(archive.file_path)
    if not path.exists():
        raise Http404(_("Archive file is missing"))
    return FileResponse(open(path, "rb"), as_attachment=True, filename=path.name)


@staff_member_required
@require_POST
def activity_archive_delete(request, pk):
    archive = get_object_or_404(ActivityArchive, pk=pk)
    if archive.month >= _expiry_limit():
        messages.error(request, _("That archive is not older than one year yet."))
        return redirect("activity_archives")
    Path(archive.file_path).unlink(missing_ok=True)
    archive.delete()
    messages.success(request, _("Archive deleted."))
    return redirect("activity_archives")
