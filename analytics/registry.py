from dashboard.models import DSRS
from contract.models import Contract, LicenseContract
from facilities.models import FacilityModel
from financial.models import LicensePayment
from operations.models import LicenseRequest
MODEL_REGISTRY = {
    "dsrs": DSRS,
    "LicenseContract":LicenseContract,
    "contracts": Contract,
    "FacilityModel": FacilityModel,
    "LicensePayment":LicensePayment,
    "LicenseRequest": LicenseRequest,
}