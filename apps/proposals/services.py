from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.budgets.models import BudgetItem
from apps.clients.models import SoftwareRequest
from apps.common.authorization import developer
from apps.common.money import money
from apps.proposals.models import NegotiationNote, Proposal
from apps.proposals.selectors import proposal_total


class InvalidProposalTransition(ValidationError):
    pass


def draft(proposal):
    if proposal.status != "DRAFT":
        raise InvalidProposalTransition("Solo se puede modificar un borrador.")


@transaction.atomic
def new_version(user, request_id, source_id=None):
    developer(user)
    request = SoftwareRequest.objects.select_for_update().get(pk=request_id)
    if request.status == "CLOSED":
        raise InvalidProposalTransition("La solicitud está cerrada.")
    previous = request.proposals.select_for_update().order_by("-version").first()
    if previous and source_id != previous.pk:
        raise InvalidProposalTransition("Clone la última versión.")
    values = {}
    if previous:
        values = {
            field: getattr(previous, field)
            for field in [
                "technical_scope",
                "technologies",
                "exclusions",
                "service_conditions",
                "sla_response_hours",
                "warranty_days",
            ]
        }
    proposal = Proposal.objects.create(
        software_request=request,
        version=previous.version + 1 if previous else 1,
        created_by=user,
        **values,
    )
    if previous:
        for sprint in previous.sprints.all():
            old_id = sprint.pk
            sprint.pk = None
            sprint.proposal = proposal
            sprint.save()
            for item in BudgetItem.objects.filter(sprint_id=old_id):
                item.pk = None
                item.sprint = sprint
                item.save()
    return proposal


@transaction.atomic
def transition(user, proposal_id, action):
    reference = Proposal.objects.get(pk=proposal_id)
    SoftwareRequest.objects.select_for_update().get(pk=reference.software_request_id)
    proposal = Proposal.objects.select_for_update().get(pk=proposal_id)
    if action == "submit":
        developer(user)
        draft(proposal)
        if not all(
            [
                proposal.technical_scope.strip(),
                proposal.technologies.strip(),
                proposal.service_conditions.strip(),
                proposal.exclusions.strip(),
                proposal.sprints.exists(),
                BudgetItem.objects.filter(sprint__proposal=proposal).exists(),
                proposal_total(proposal) > 0,
            ]
        ):
            raise InvalidProposalTransition(
                "Complete alcance, tecnologías, exclusiones, condiciones, sprints y presupuesto positivo."
            )
        proposal.status = "SUBMITTED"
    elif action in ["accept", "reject"]:
        if user.role != "CLIENT" or user.client_id != proposal.software_request.client_id:
            raise PermissionDenied
        if proposal.status not in ["SUBMITTED", "NEGOTIATING"]:
            raise InvalidProposalTransition("La propuesta no admite esta decisión.")
        if action == "accept":
            if Proposal.objects.filter(
                software_request=proposal.software_request,
                status="ACCEPTED",
                version__gt=proposal.version,
            ).exists():
                raise InvalidProposalTransition("Ya existe un acuerdo de una versión posterior.")
            Proposal.objects.filter(
                software_request=proposal.software_request, status="ACCEPTED"
            ).update(status="SUPERSEDED")
            proposal.status = "ACCEPTED"
            proposal.accepted_by = user
            proposal.accepted_at = timezone.now()
            proposal.accepted_total_cop = proposal_total(proposal)
            from integrations.exchange_rates import current_snapshot

            rate = current_snapshot(24)
            if rate:
                proposal.accepted_exchange_rate = rate.cop_per_usd
                proposal.accepted_exchange_rate_at = rate.effective_at
                proposal.accepted_total_usd = money(proposal.accepted_total_cop / rate.cop_per_usd)
        else:
            proposal.status = "REJECTED"
    else:
        raise InvalidProposalTransition("Acción desconocida.")
    proposal.save()
    return proposal


@transaction.atomic
def add_note(user, proposal_id, values, negotiate=False):
    proposal = Proposal.objects.select_for_update().get(pk=proposal_id)
    if user.role != "DEVELOPER" and user.client_id != proposal.software_request.client_id:
        raise PermissionDenied
    if proposal.status not in ["SUBMITTED", "NEGOTIATING"]:
        raise InvalidProposalTransition("Esta versión es de solo lectura.")
    if negotiate:
        developer(user)
        if proposal.status != "SUBMITTED":
            raise InvalidProposalTransition("La propuesta ya está en negociación.")
    note = NegotiationNote(proposal=proposal, author=user, **values)
    note.full_clean()
    note.save()
    if negotiate:
        proposal.status = "NEGOTIATING"
        proposal.save(update_fields=["status"])
    return note
