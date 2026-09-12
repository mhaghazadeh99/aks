from operations.models import LicenseApproval


def create_license_workflow(license_request):

    steps = [
        LicenseApproval.ApprovalStep.CREATOR,
        LicenseApproval.ApprovalStep.MANAGER,
        LicenseApproval.ApprovalStep.DEPUTY,
    ]

    if license_request.discount_requested:
        steps.append(LicenseApproval.ApprovalStep.CEO)

    steps.append(LicenseApproval.ApprovalStep.CONTRACTS)

    for index, step in enumerate(steps, start=1):
        LicenseApproval.objects.create(
            license=license_request,
            step=step,
            order=index,
        )