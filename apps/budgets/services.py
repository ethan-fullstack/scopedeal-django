from django.core.exceptions import PermissionDenied
from django.db import transaction

from apps.budgets.models import BudgetItem, Sprint
from apps.common.authorization import developer
from apps.proposals.models import Proposal
from apps.proposals.services import draft


@transaction.atomic
def save_component(user, obj, proposal=None):
    developer(user)
    if isinstance(obj, (BudgetItem, Sprint)):
        actual_proposal = obj.sprint.proposal if isinstance(obj, BudgetItem) else obj.proposal
        if proposal and proposal.pk != actual_proposal.pk:
            raise PermissionDenied
        proposal = actual_proposal
    if proposal:
        draft(Proposal.objects.select_for_update().get(pk=proposal.pk))
    if isinstance(obj, BudgetItem):
        if obj.sprint.proposal_id != proposal.pk:
            raise PermissionDenied
        if not obj.tariff_profile.is_active:
            raise PermissionDenied
        obj.hourly_rate_cop = obj.tariff_profile.hourly_rate_cop
        obj.profile_name = obj.tariff_profile.profile
        obj.profile_level = obj.tariff_profile.level
    obj.full_clean()
    obj.save()
    return obj


@transaction.atomic
def delete_component(user, obj, proposal):
    developer(user)
    draft(Proposal.objects.select_for_update().get(pk=proposal.pk))
    obj.delete()
