from decimal import ROUND_HALF_UP, Decimal

from django.db.models import DecimalField, ExpressionWrapper, F, Sum, Value
from django.db.models.functions import Coalesce, Round


def money(value):
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def subtotal_expression(prefix=""):
    return Round(
        ExpressionWrapper(
            F(prefix + "estimated_hours") * F(prefix + "hourly_rate_cop")
            + F(prefix + "infrastructure_cost_cop"),
            output_field=DecimalField(max_digits=24, decimal_places=4),
        ),
        2,
    )


def total(items):
    return items.aggregate(
        value=Coalesce(
            Sum(subtotal_expression()),
            Value(Decimal("0.00")),
            output_field=DecimalField(max_digits=24, decimal_places=2),
        )
    )["value"]
