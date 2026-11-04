from decimal import Decimal

from django.db.models import DecimalField, Sum, Value
from django.db.models.functions import Coalesce

from apps.budgets.models import BudgetItem
from apps.common.money import money, total


def proposal_budget(proposal, rate=None):
    items = BudgetItem.objects.filter(sprint__proposal=proposal)
    values = items.aggregate(
        hours=Coalesce(
            Sum("estimated_hours"),
            Value(Decimal(0)),
            output_field=DecimalField(max_digits=24, decimal_places=2),
        ),
        infrastructure=Coalesce(
            Sum("infrastructure_cost_cop"),
            Value(Decimal(0)),
            output_field=DecimalField(max_digits=24, decimal_places=2),
        ),
    )
    values["total"] = total(items)
    values["development"] = values["total"] - values["infrastructure"]
    values["usd"] = money(values["total"] / rate.cop_per_usd) if rate else None
    sprints = list(proposal.sprints.prefetch_related("items"))
    for sprint in sprints:
        sprint.total_cop = Decimal(0)
        sprint.total_hours = Decimal(0)
        for item in sprint.items.all():
            sprint.total_cop += item.subtotal
            sprint.total_hours += item.estimated_hours
            item.subtotal_usd = money(item.subtotal / rate.cop_per_usd) if rate else None
        sprint.total_usd = money(sprint.total_cop / rate.cop_per_usd) if rate else None
    values["sprints"] = sprints
    return values
