from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from apps.budgets.selectors import proposal_budget
from apps.common.authorization import developer
from apps.common.presentation import exchange_context
from apps.common.views import draft, form_page, proposal_object, request_object
from apps.proposals.forms import (
    NoteForm,
    ProposalForm,
)
from apps.proposals.models import Proposal
from apps.proposals.selectors import proposal_total
from apps.proposals.services import add_note, new_version, transition


@login_required
@require_POST
def proposal_new(request, pk):
    developer(request.user)
    request_object(request.user, pk)
    try:
        obj = new_version(request.user, pk)
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
        return redirect("request-detail", pk=pk)
    return redirect("proposal-edit", pk=obj.pk)


@login_required
def proposal_detail(request, pk, budget_only=False):
    obj = proposal_object(request.user, pk)
    fx = exchange_context()
    budget = proposal_budget(obj, fx["rate"])
    can_clone = (
        request.user.role == "DEVELOPER"
        and obj.software_request.status != "CLOSED"
        and not obj.software_request.proposals.filter(version__gt=obj.version).exists()
    )
    return render(
        request,
        "proposal.html",
        {
            "object": obj,
            "total": budget["total"],
            "budget": budget,
            **fx,
            "can_clone": can_clone,
            "budget_only": budget_only,
            "note_form": NoteForm(),
            "sprints": budget["sprints"],
            "notes": obj.notes.select_related("author").order_by("created_at", "pk"),
            "draft": obj.status == "DRAFT",
            "eligible": obj.status in ["SUBMITTED", "NEGOTIATING"],
        },
    )


@login_required
def proposal_edit(request, pk):
    developer(request.user)
    obj = proposal_object(request.user, pk)
    draft(obj)
    form = ProposalForm(request.POST if request.method == "POST" else None, instance=obj)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            draft(Proposal.objects.select_for_update().get(pk=pk))
            form.save()
        return redirect("proposal-detail", pk=pk)
    return form_page(request, form, "Editar propuesta")


@login_required
@require_POST
def proposal_action(request, pk, action):
    obj = proposal_object(request.user, pk)
    if request.POST.get("review") == "yes" and action in ["submit", "clone"]:
        developer(request.user)
        return render(
            request, "confirm.html", {"object": obj, "total": proposal_total(obj), "action": action}
        )
    if action in ["accept", "reject"] and request.user.role != "CLIENT":
        raise PermissionDenied
    if action in ["accept", "reject"] and request.POST.get("confirm") != "yes":
        return render(
            request, "confirm.html", {"object": obj, "total": proposal_total(obj), "action": action}
        )
    try:
        if action == "clone":
            obj = new_version(request.user, obj.software_request_id, obj.pk)
        else:
            obj = transition(request.user, pk, action)
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        messages.success(request, "Operación completada.")
    return redirect("proposal-detail", pk=obj.pk)


@login_required
@require_POST
def note_new(request, pk, negotiate=False):
    proposal_object(request.user, pk)
    form = NoteForm(request.POST)
    if form.is_valid():
        try:
            add_note(request.user, pk, form.cleaned_data, negotiate)
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            return redirect("proposal-detail", pk=pk)
    return form_page(request, form, "Observación compartida")
