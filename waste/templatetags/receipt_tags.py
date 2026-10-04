"""{% load receipt_tags %}  ->  {{ date_or_datetime|jdate }}  /  {{ value|jdate:"%Y/%m/%d %H:%M" }}

Uses jdatetime, which django-jalali / django-jalali-date already depend on.
Put this folder at waste/templatetags/ (keep your existing __init__.py if you have one)."""
import datetime

import jdatetime
from django import template
from django.utils import timezone

register = template.Library()


@register.filter
def jdate(value, fmt="%Y/%m/%d"):
    if not value:
        return "-"
    if isinstance(value, datetime.datetime):
        if timezone.is_aware(value):
            value = timezone.localtime(value)
        return jdatetime.datetime.fromgregorian(datetime=value).strftime(fmt)
    return jdatetime.date.fromgregorian(date=value).strftime(fmt)