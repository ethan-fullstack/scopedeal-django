from decimal import Decimal, InvalidOperation

from django import template

from apps.common.money import money

register = template.Library()


@register.filter
def amount(value):
    if value is None:
        return "—"
    try:
        formatted = f"{money(Decimal(value)):,.2f}"
    except (InvalidOperation, ValueError, TypeError):
        return "—"
    return formatted.translate(str.maketrans({",": ".", ".": ","}))


@register.filter
def startswith(value, prefix):
    return str(value).startswith(str(prefix))
