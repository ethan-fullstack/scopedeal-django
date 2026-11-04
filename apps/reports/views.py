from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, Sum
from django.http import Http404
from django.shortcuts import get_object_or_404, render

from apps.budgets.models import BudgetItem
from apps.clients.models import SoftwareRequest
from apps.common.authorization import scoped
from apps.common.money import subtotal_expression, total
from apps.common.presentation import bar_rows, exchange_context, status_chart
from apps.common.views import paginate
from apps.proposals.models import NegotiationNote, Proposal
from apps.proposals.selectors import latest, proposals_for
from apps.reports.forms import (
    ReportForm,
)
from apps.reports.selectors import budget_breakdown


@login_required
def dashboard(request):
    proposals = latest(proposals_for(request.user))
    requests = scoped(SoftwareRequest.objects.all(), request.user)
    items = BudgetItem.objects.filter(sprint__proposal__in=proposals)
    return render(
        request,
        "dashboard.html",
        {
            "title": "Dashboard",
            "proposal_count": proposals.count(),
            "negotiating_count": proposals.filter(status="NEGOTIATING").count(),
            "pending_count": requests.filter(status="NEW").count(),
            "status_chart": status_chart(proposals),
            "sprint_chart": bar_rows(
                items.values("sprint__number")
                .annotate(cost=Sum(subtotal_expression()))
                .order_by("sprint__number"),
                label_key="sprint__number",
            ),
            "recent_notes": NegotiationNote.objects.filter(proposal__in=proposals_for(request.user))
            .select_related("author", "proposal__software_request__client")
            .order_by("-created_at")[:5],
            **exchange_context(),
            "request_counts": [
                dict(
                    row,
                    label=dict(SoftwareRequest._meta.get_field("status").choices)[row["status"]],
                )
                for row in requests.values("status").annotate(count=Count("pk"))
            ],
            "proposal_counts": [
                dict(row, label=dict(Proposal.STATES)[row["status"]])
                for row in proposals.values("status").annotate(count=Count("pk"))
            ],
            "forecast": total(items),
            "accepted": proposals_for(request.user)
            .filter(status="ACCEPTED")
            .aggregate(value=Sum("accepted_total_cop"))["value"]
            or 0,
            "clients": items.values("sprint__proposal__software_request__client__name").annotate(
                cost=Sum(subtotal_expression())
            ),
            "sprints": items.values("sprint__number").annotate(cost=Sum(subtotal_expression())),
            "proposals": proposals.order_by("-created_at", "-pk"),
        },
    )


@login_required
def reports(request):
    form = ReportForm(request.GET)
    if request.user.role == "CLIENT":
        form.fields.pop("client")
    objects = proposals_for(request.user)
    if form.is_valid():
        data = form.cleaned_data
        if not data["history"]:
            objects = latest(objects)
        if data.get("q"):
            objects = objects.filter(
                Q(software_request__title__icontains=data["q"])
                | Q(software_request__client__name__icontains=data["q"])
            )
        if data.get("client"):
            objects = objects.filter(software_request__client=data["client"])
        if data["status"]:
            objects = objects.filter(status=data["status"])
        if data["start"]:
            objects = objects.filter(created_at__date__gte=data["start"])
        if data["end"]:
            objects = objects.filter(created_at__date__lte=data["end"])
        if data["sprint"]:
            objects = objects.filter(sprints__number=data["sprint"]).distinct()
    else:
        objects = objects.none()
    proposal_id = request.GET.get("proposal")
    if proposal_id:
        try:
            proposal_id = int(proposal_id)
        except (ValueError, TypeError):
            raise Http404
        selected = get_object_or_404(proposals_for(request.user), pk=proposal_id)
        objects = objects.filter(pk=selected.pk)
    breakdown = budget_breakdown(
        objects, form.cleaned_data.get("sprint") if form.is_valid() else None
    )
    return render(
        request,
        "reports.html",
        {
            "title": "Propuestas" if request.path == "/proposals/" else "Reportes",
            "is_proposal_list": request.path == "/proposals/",
            "proposal_count": objects.count(),
            "accepted_count": objects.filter(status="ACCEPTED").count(),
            "negotiating_count": objects.filter(status="NEGOTIATING").count(),
            "status_chart": status_chart(objects),
            "sprint_chart": bar_rows(breakdown["sprints"]),
            "form": form,
            "objects": objects,
            **paginate(request, objects),
            **breakdown,
        },
    )
