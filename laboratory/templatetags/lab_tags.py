"""
Template tags for the laboratory app  ->  laboratory/templatetags/lab_tags.py
(also create an empty laboratory/templatetags/__init__.py)

Usage in ANY template (dashboard, navbar, other apps' pages):

    {% load lab_tags %}
    {% lab_count "sent" %}                 -> just the number
    {% lab_badge "sig_lab_manager" %}      -> <span class="badge">3</span> (renders nothing if 0)
    {% lab_card "sig_lab_manager" %}       -> a whole link card (icon, title, count, link)
    {% lab_rejected_alert %}               -> banner listing the current user's newly rejected samples

To move a link/number somewhere else you only move that one tag. To
change where a card points, edit its entry in CARDS below — nothing else.
"""
from django import template
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from ..models import (
    AlphaBetaCountingRun, Analysis, LabApprovalRole, Sample, SampleStatus,
)
from ..services.workflow import pending_steps_for_role

register = template.Library()


def _by_status(status):
    return lambda user: Sample.objects.filter(status=status).count()


COUNTERS = {
    "collected": _by_status(SampleStatus.COLLECTED),
    "sent": _by_status(SampleStatus.SENT_TO_LAB),
    "received": _by_status(SampleStatus.RECEIVED_BY_LAB),
    "in_analysis": _by_status(SampleStatus.IN_ANALYSIS),
    "completed": _by_status(SampleStatus.COMPLETED),
    "rejected": _by_status(SampleStatus.REJECTED),
    "urgent": lambda user: Sample.objects.filter(urgent=True)
        .exclude(status__in=[SampleStatus.COMPLETED, SampleStatus.REJECTED]).count(),
    "pending_review": lambda user: Analysis.objects.filter(approved=False).count(),
    "my_rejected": lambda user: (
        Sample.objects.filter(collected_by=user, status=SampleStatus.REJECTED, rejection_seen=False).count()
        if user is not None and user.is_authenticated else 0
    ),
    "open_runs": lambda user: AlphaBetaCountingRun.objects.filter(approvals__isnull=True).distinct().count(),
    "sig_analyst": lambda user: len(pending_steps_for_role(LabApprovalRole.ANALYST)),
    "sig_lab_manager": lambda user: len(pending_steps_for_role(LabApprovalRole.LAB_MANAGER)),
    "sig_ops_manager": lambda user: len(pending_steps_for_role(LabApprovalRole.OPS_MANAGER)),
    "finalized": lambda user: (
        Analysis.objects.filter(approved=True, approvals__isnull=False).distinct().count()
        + AlphaBetaCountingRun.objects.filter(approved=True).count()
    ),
}

# key -> card. "url" is a URL *name*; "query" is appended as-is; "counter" is a COUNTERS key.
CARDS = {
    "all_samples": dict(icon="🧪", title=_("All Samples"), text=_("Browse every sample"), url="sample_list"),
    "new_sample": dict(icon="➕", title=_("New Sample"), text=_("Gamma or Alpha/Beta, with or without a waste batch"), url="sample_create"),
    "collected": dict(icon="📥", title=_("Collected"), text=_("Taken, not yet sent to the lab"), url="sample_list", query="?status=COLLECTED", counter="collected", unit=_("Samples")),
    "sent": dict(icon="🚚", title=_("Sent To Lab"), text=_("In transit — awaiting lab receipt"), url="sample_list", query="?status=SENT_TO_LAB", counter="sent", unit=_("Samples")),
    "received": dict(icon="📦", title=_("Received By Lab"), text=_("Ready to start analysis"), url="sample_list", query="?status=RECEIVED_BY_LAB", counter="received", unit=_("Samples")),
    "in_analysis": dict(icon="🔬", title=_("In Analysis"), text=_("Being counted"), url="sample_list", query="?status=IN_ANALYSIS", counter="in_analysis", unit=_("Samples")),
    "completed": dict(icon="🏁", title=_("Completed"), text=_("Analysis entered"), url="sample_list", query="?status=COMPLETED", counter="completed", unit=_("Samples")),
    "rejected": dict(icon="⛔", title=_("Rejected"), text=_("Rejected by the lab"), url="sample_list", query="?status=REJECTED", counter="rejected", unit=_("Samples"), css="urgent"),
    "my_rejected": dict(icon="🔔", title=_("My Rejected Samples"), text=_("Samples I collected that were rejected"), url="sample_list", query="?status=REJECTED&mine=1", counter="my_rejected", unit=_("New"), css="urgent"),
    "urgent": dict(icon="⚠", title=_("Urgent"), text=_("Open urgent samples"), url="sample_list", counter="urgent", unit=_("Samples"), css="urgent"),
    "pending_review": dict(icon="✅", title=_("Pending Review"), text=_("Analyses awaiting approval"), url="analysis_review_queue", counter="pending_review", unit=_("Analyses")),
    "counting_runs": dict(icon="☢", title=_("Alpha/Beta Counting Runs"), text=_("Group samples into one shared report"), url="counting_run_list", counter="open_runs", unit=_("Open")),
    "new_run": dict(icon="🆕", title=_("New Counting Run"), text=_("Up to 12 samples per run"), url="counting_run_create"),
    "sig_analyst": dict(icon="✍", title=_("Analyst Signatures"), text=_("Waiting for the Analysis Lab Expert"), url="signature_queue_analyst", counter="sig_analyst", unit=_("Reports")),
    "sig_lab_manager": dict(icon="🖋", title=_("Lab Manager Signatures"), text=_("Waiting for the Lab Manager"), url="signature_queue_lab_manager", counter="sig_lab_manager", unit=_("Reports")),
    "sig_ops_manager": dict(icon="🏛", title=_("Operations Manager Signatures"), text=_("Waiting for Operations / Operations Control"), url="signature_queue_ops_manager", counter="sig_ops_manager", unit=_("Reports")),
    "finalized": dict(icon="📑", title=_("Finalized Reports"), text=_("Fully signed reports"), url="finalized_reports", counter="finalized", unit=_("Reports")),
}


def _user(context):
    request = context.get("request")
    return getattr(request, "user", None)


@register.simple_tag(takes_context=True)
def lab_count(context, key):
    fn = COUNTERS.get(key)
    return fn(_user(context)) if fn else ""


@register.simple_tag(takes_context=True)
def lab_badge(context, key, css="bg-danger"):
    n = lab_count(context, key)
    return format_html('<span class="badge {}">{}</span>', css, n) if n else ""


@register.inclusion_tag("laboratory/_lab_card.html", takes_context=True)
def lab_card(context, key):
    card = CARDS[key]
    counter = card.get("counter")
    return {"card": card, "count": COUNTERS[counter](_user(context)) if counter else None}


@register.inclusion_tag("laboratory/_rejected_alert.html", takes_context=True)
def lab_rejected_alert(context):
    user = _user(context)
    samples = []
    if user is not None and user.is_authenticated:
        samples = list(Sample.objects.filter(
            collected_by=user, status=SampleStatus.REJECTED, rejection_seen=False,
        ).order_by("-rejected_at")[:5])
    return {"samples": samples}