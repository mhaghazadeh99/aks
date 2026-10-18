from django import template

from operation_control import conf
from operation_control import jalali_utils as ju
from operation_control import services
from operation_control.models import Equipment, InspectionPlanYear

register = template.Library()


@register.simple_tag
def calibration_counts():
    """Hub-card counts (same rule as the alert: active / loaned devices only)."""
    a = services.calibration_alerts(limit=0)
    return {"expired": a["expired_count"], "due_soon": a["due_soon_count"]}


@register.inclusion_tag("operation_control/_calibration_alert.html")
def calibration_alert():
    """
    Notification banner: devices whose calibration has expired or expires within the warning window.
    Put {% calibration_alert %} at the top of the Operation Control home and the calibration pages.
    """
    return services.calibration_alerts()


@register.simple_tag
def dosimetry_counts():
    """Workers over the season whole-body limit (TLD) in the current Jalali season."""
    year, season = services.current_year_season()
    return {"over_limit": services.over_limit_count(year, season), "limit": conf.SEASON_DOSE_LIMIT_MSV}


@register.simple_tag
def inspection_counts():
    """Items overdue / due this week for the current plan year (zeros if there is none)."""
    plan = InspectionPlanYear.objects.filter(year=ju.jalali_today()[0]).first()
    if not plan:
        return {"overdue": 0, "this_week": 0, "has_plan": False}
    s = services.plan_matrix(plan)["summary"]
    return {"overdue": s["overdue_items"], "this_week": s["pending_now"], "has_plan": True}


@register.filter
def jdate(value):
    """Jalali (1405/07/25) when the UI language is Persian, ISO otherwise. Empty for None."""
    return ju.display(value) if value else ""
