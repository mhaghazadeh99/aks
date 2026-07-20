from operations.models import LicenseApproval


def create_license_workflow(license_request):

    steps = [

        LicenseApproval.ApprovalStep.CREATOR,

        LicenseApproval.ApprovalStep.MANAGER,

        LicenseApproval.ApprovalStep.DEPUTY,

        LicenseApproval.ApprovalStep.CONTRACTS,

    ]

    for index, step in enumerate(steps, start=1):

        LicenseApproval.objects.create(

            license=license_request,

            step=step,

            order=index,

        )