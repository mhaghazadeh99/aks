from django import template

from ..models import ReceiveRequest

register = template.Library()


@register.simple_tag
def receiving_queue_count(status):
    """
    Usage from ANY template, anywhere in the project:

        {% load receiving_extras %}
        {% receiving_queue_count "WAITING_CEO" as ceo_count %}
        <p># {{ ceo_count }} Requests</p>

    Valid status values (ReceiveStatus choices): DRAFT, SPECIFICATION,
    WAITING_CREATOR, WAITING_MANAGER_INPUT, WAITING_MANAGER,
    WAITING_CONTROL, WAITING_DEPUTY, CONTRACTS, WAITING_CEO, FINANCE,
    RECEIVING, COMPLETED, REJECTED.
    """
    return ReceiveRequest.objects.filter(status=status).count()