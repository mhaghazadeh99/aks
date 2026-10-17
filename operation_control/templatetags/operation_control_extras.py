from django import template

from operation_control import conf
from operation_control import jalali_utils as ju
from operation_control.models import Equipment

register = template.Library()


@register.simple_tag
def calibration_counts():
    """Counts for the hub card, among ACTIVE equipment only."""
    today = ju.today()
    soon = ju.add_days(today, conf.CALIBRATION_WARNING_DAYS)
    active = Equipment.objects.filter(status=Equipment.Status.ACTIVE)
    return {
        "expired": active.filter(due_date__lt=today).count(),
        "due_soon": active.filter(due_date__gte=today, due_date__lte=soon).count(),
    }
