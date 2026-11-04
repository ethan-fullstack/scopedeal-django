from django.db.models import OuterRef, Subquery

from apps.budgets.models import BudgetItem
from apps.common.authorization import scoped
from apps.common.money import total
from apps.proposals.models import Proposal


def proposals_for(user):
    return scoped(
        Proposal.objects.select_related("software_request__client"),
        user,
        "software_request__client_id",
    )


def latest(queryset):
    newest = (
        Proposal.objects.filter(software_request_id=OuterRef("software_request_id"))
        .order_by("-version")
        .values("pk")[:1]
    )
    return queryset.filter(pk=Subquery(newest))


def proposal_total(proposal):
    return total(BudgetItem.objects.filter(sprint__proposal=proposal))
