from django import template

from sell_source.models import SellRequest, SellRequestStatus

register = template.Library()


@register.simple_tag
def sell_ceo_count():
    return SellRequest.objects.filter(
        status=SellRequestStatus.WAITING_CEO
    ).count()