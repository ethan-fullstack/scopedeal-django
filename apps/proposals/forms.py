from apps.common.forms import model_form
from apps.proposals.models import NegotiationNote, Proposal

ProposalForm = model_form(
    Proposal,
    [
        "technical_scope",
        "technologies",
        "exclusions",
        "service_conditions",
        "sla_response_hours",
        "warranty_days",
    ],
)


NoteForm = model_form(NegotiationNote, ["type", "message", "proposed_amount_cop"])
