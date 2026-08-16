from django.shortcuts import render
from django.utils.http import url_has_allowed_host_and_scheme
# Create your views here.
import csv

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.models import Group
from django.shortcuts import render, redirect, get_object_or_404
from django.utils.translation import gettext_lazy as _

from .forms import ViewPermissionImportForm
from .models import ViewPermission

from django.contrib.auth.decorators import login_required
from .models import UserProfile
from .forms import UserProfileForm  # add this form below

@staff_member_required
def view_permission_list(request):
    permissions = ViewPermission.objects.prefetch_related("groups").order_by("view_name")
    return render(request, "accounts/view_permission_list.html", {"permissions": permissions})


@staff_member_required
def view_permission_import(request):

    if request.method == "POST":

        form = ViewPermissionImportForm(request.POST, request.FILES)

        if form.is_valid():

            csv_file = form.cleaned_data["csv_file"]
            decoded = csv_file.read().decode("utf-8-sig").splitlines()
            reader = csv.DictReader(decoded)

            created = 0
            errors = []

            for i, row in enumerate(reader, start=1):

                view_name = (row.get("view_name") or "").strip()
                group_names_raw = (row.get("group_name") or "").strip()

                if not view_name or not group_names_raw:
                    errors.append(f"Row {i}: view_name and group_name are both required")
                    continue

                group_names = [g.strip() for g in group_names_raw.split(";") if g.strip()]

                groups = []
                for name in group_names:
                    group, underline = Group.objects.get_or_create(name=name)
                    groups.append(group)

                permission, underlin = ViewPermission.objects.get_or_create(view_name=view_name)
                permission.groups.set(groups)

                created += 1

            messages.success(request, _("%(count)s view permission(s) imported successfully.") % {"count": created})
            for e in errors:
                messages.error(request, e)

            return redirect("view_permission_list")

    else:
        form = ViewPermissionImportForm()

    return render(request, "accounts/view_permission_import.html", {"form": form})


@staff_member_required
def view_permission_delete(request, pk):
    permission = get_object_or_404(ViewPermission, pk=pk)
    if request.method == "POST":
        permission.delete()
        messages.success(request, _("View permission removed."))
        return redirect("view_permission_list")
    return render(request, "accounts/view_permission_delete.html", {"permission": permission})







@login_required
def profile(request):

    user_profile, _created = UserProfile.objects.get_or_create(
        user=request.user,
        defaults={"full_name": request.user.get_full_name() or request.user.username},
    )

    next_url = request.POST.get("next") or request.GET.get("next")

    # Only follow next_url if it's a safe, same-site path — never redirect
    # to an attacker-supplied external URL.
    if next_url and not url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        next_url = None

    if request.method == "POST":
        form = UserProfileForm(request.POST, request.FILES, instance=user_profile)
        if form.is_valid():
            form.save()
            messages.success(request, _("Profile updated successfully."))
            return redirect(next_url or "profile")
    else:
        form = UserProfileForm(instance=user_profile)

    return render(request, "accounts/profile.html", {"form": form, "next": next_url})