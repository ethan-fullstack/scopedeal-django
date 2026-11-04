from decimal import Decimal

from django.db.models import DecimalField, Sum, Value
from django.db.models.functions import Coalesce

from apps.budgets.models import BudgetItem, Sprint
from apps.common.money import subtotal_expression, total


def budget_breakdown(proposals, sprint_number=None):
    sprints = Sprint.objects.filter(proposal__in=proposals)
    if sprint_number:
        sprints = sprints.filter(number=sprint_number)
    items = BudgetItem.objects.filter(sprint__in=sprints)
    zero = Value(Decimal("0.00"))
    decimal_field = DecimalField(max_digits=24, decimal_places=2)
    return {
        "total": total(items),
        "groups": items.values("profile_name", "profile_level").annotate(
            hours=Sum("estimated_hours"), cost=Sum(subtotal_expression())
        ),
        "sprints": sprints.values("proposal_id", "number")
        .annotate(
            hours=Coalesce(Sum("items__estimated_hours"), zero, output_field=decimal_field),
            cost=Coalesce(Sum(subtotal_expression("items__")), zero, output_field=decimal_field),
        )
        .order_by("proposal_id", "number"),
    }
