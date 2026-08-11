from django.http import HttpResponseForbidden
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from .models import ViewPermission

# Never blockable, regardless of what's in the ViewPermission table —
# protects against an admin accidentally locking everyone (including
# staff) out of login, or out of the permission-management pages
# themselves.
ALWAYS_ALLOWED_VIEW_NAMES = {
    "login",
    "logout",
    "password_change",
    "password_change_done",
    "set_language",
    "view_permission_list",
    "view_permission_import",
    "view_permission_delete",
}


class ViewPermissionMiddleware:

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):

        match = request.resolver_match
        if not match:
            return None

        view_name = match.url_name

        if not view_name or view_name in ALWAYS_ALLOWED_VIEW_NAMES:
            return None

        if request.path.startswith("/admin/"):
            return None  # Django admin manages its own permissions

        try:
            permission = ViewPermission.objects.prefetch_related("groups").get(view_name=view_name)
        except ViewPermission.DoesNotExist:
            return None

        user = request.user

        if user.is_authenticated and user.is_superuser:
            return None

        if not user.is_authenticated:
            return redirect(f"{reverse('login')}?next={request.path}")

        allowed_group_ids = permission.groups.values_list("pk", flat=True)

        if not user.groups.filter(pk__in=allowed_group_ids).exists():
            return HttpResponseForbidden(_("You do not have access to this page."))

        return None