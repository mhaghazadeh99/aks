from django import template
from django.utils.translation import get_language
from persiantools import digits

from common.utils.date_utils import to_jalali

register = template.Library()


@register.filter
def local_date(value):

    if not value:
        return ""

    if get_language() == "fa":

        jalali = to_jalali(value).strftime("%Y/%m/%d")

        return digits.en_to_fa(jalali)

    return value.strftime("%Y-%m-%d")