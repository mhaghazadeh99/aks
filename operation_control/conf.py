"""Tunable limits. Override in settings.py, e.g.
OPERATION_CONTROL_SEASON_DOSE_LIMIT_MSV = 1.5
"""
from decimal import Decimal

from django.conf import settings

# Warning threshold per season (taken from your Excel dashboard setting).
SEASON_DOSE_LIMIT_MSV = Decimal(str(getattr(settings, "OPERATION_CONTROL_SEASON_DOSE_LIMIT_MSV", "1.5")))
# Whole-body limit used for the yearly alert (hand/extremity doses are never added to it).
ANNUAL_DOSE_LIMIT_MSV = Decimal(str(getattr(settings, "OPERATION_CONTROL_ANNUAL_DOSE_LIMIT_MSV", "20")))
# Equipment is flagged "due soon" when this many days (or fewer) remain.
CALIBRATION_WARNING_DAYS = int(getattr(settings, "OPERATION_CONTROL_CALIBRATION_WARNING_DAYS", 30))
