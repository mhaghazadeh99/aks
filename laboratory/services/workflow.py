from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from ..models import AnalysisApproval, LabApprovalRole, LabApprovalStatus

def pending_steps_for_role(role):
    """Steps that are actually 'current' for this role: PENDING, every earlier step approved, nothing rejected."""
    steps = (
        AnalysisApproval.objects.filter(role=role, status=LabApprovalStatus.PENDING)
        .select_related("analysis__sample", "counting_run")
    )
    current = []
    for step in steps:
        target = step.analysis or step.counting_run
        siblings = list(target.approvals.all())
        if any(s.status == LabApprovalStatus.REJECTED for s in siblings):
            continue
        if any(s.order < step.order and s.status != LabApprovalStatus.APPROVED for s in siblings):
            continue
        current.append(step)
    return current


def rejected_steps():
    return (
        AnalysisApproval.objects.filter(status=LabApprovalStatus.REJECTED)
        .select_related("analysis__sample", "counting_run", "user")
    )
def create_analysis_approval_chain(analysis):
    """3-step chain for a single Gamma analysis's report."""
    AnalysisApproval.objects.bulk_create([
        AnalysisApproval(analysis=analysis, role=LabApprovalRole.ANALYST, order=1),
        AnalysisApproval(analysis=analysis, role=LabApprovalRole.LAB_MANAGER, order=2),
        AnalysisApproval(analysis=analysis, role=LabApprovalRole.OPS_MANAGER, order=3),
    ])


def create_counting_run_approval_chain(counting_run):
    """3-step chain for an Alpha/Beta counting run's shared report."""
    AnalysisApproval.objects.bulk_create([
        AnalysisApproval(counting_run=counting_run, role=LabApprovalRole.ANALYST, order=1),
        AnalysisApproval(counting_run=counting_run, role=LabApprovalRole.LAB_MANAGER, order=2),
        AnalysisApproval(counting_run=counting_run, role=LabApprovalRole.OPS_MANAGER, order=3),
    ])


def current_step_for(approvals_qs):
    """Returns the first PENDING approval in order, or None if the chain
    is fully approved (or was rejected, in which case nothing is 'current')."""
    if approvals_qs.filter(status=LabApprovalStatus.REJECTED).exists():
        return None
    return approvals_qs.filter(status=LabApprovalStatus.PENDING).order_by("order").first()


def approve_step(approval, user, comment=""):
    approval.status = LabApprovalStatus.APPROVED
    approval.user = user
    approval.signed_date = timezone.now().date()
    approval.comments = comment
    approval.save()

    target = approval.analysis or approval.counting_run
    remaining = target.approvals.filter(status=LabApprovalStatus.PENDING).exists()
    if not remaining:
        
        target.approved = True
        target.save(update_fields=["approved"])
        if approval.counting_run_id:
            target.analyses.update(approved=True, review_date=timezone.now().date())


def reject_step(approval, user, comment=""):
    approval.status = LabApprovalStatus.REJECTED
    approval.user = user
    approval.signed_date = timezone.now().date()
    approval.comments = comment
    approval.save()