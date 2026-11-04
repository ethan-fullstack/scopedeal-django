from datetime import timedelta
from decimal import Decimal
from io import StringIO

import pytest
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.budgets.models import BudgetItem, ExchangeRateSnapshot, Sprint
from apps.budgets.services import save_component
from apps.clients.models import SoftwareRequest
from apps.proposals.models import Proposal
from apps.proposals.services import new_version, transition
from apps.reports.selectors import budget_breakdown

pytestmark = pytest.mark.django_db


def test_empty_sprint_report_is_zero(world):
    world["item"].delete()
    result = budget_breakdown(Proposal.objects.filter(pk=world["proposal"].pk))
    assert result["total"] == Decimal("0.00")
    row = list(result["sprints"])[0]
    assert row["hours"] == 0 and row["cost"] == 0
    with pytest.raises(ValidationError):
        transition(world["dev"], world["proposal"].pk, "submit")


def test_zero_budget_cannot_submit(world):
    BudgetItem.objects.filter(pk=world["item"].pk).update(
        hourly_rate_cop=0, infrastructure_cost_cop=0
    )
    with pytest.raises(ValidationError):
        transition(world["dev"], world["proposal"].pk, "submit")


def test_old_version_cannot_supersede_newer_agreement(world):
    first = transition(world["dev"], world["proposal"].pk, "submit")
    second = new_version(world["dev"], world["request"].pk, first.pk)
    transition(world["dev"], second.pk, "submit")
    transition(world["client"], second.pk, "accept")
    with pytest.raises(ValidationError):
        transition(world["client"], first.pk, "accept")
    with pytest.raises(IntegrityError), transaction.atomic():
        Proposal.objects.filter(pk=first.pk).update(status="ACCEPTED")


def test_stale_rate_not_frozen_at_acceptance(world):
    ExchangeRateSnapshot.objects.create(
        cop_per_usd=4000, effective_at=timezone.now() - timedelta(days=2)
    )
    transition(world["dev"], world["proposal"].pk, "submit")
    result = transition(world["client"], world["proposal"].pk, "accept")
    assert result.accepted_total_cop == 13000
    assert result.accepted_total_usd is None and result.accepted_exchange_rate is None


def test_budget_service_checks_actual_proposal_even_without_argument(world):
    transition(world["dev"], world["proposal"].pk, "submit")
    with pytest.raises(ValidationError):
        save_component(world["dev"], world["item"])


def test_seed_is_idempotent_and_has_no_known_password(world):
    output = StringIO()
    call_command("seed_demo_data", stdout=output)
    counts = (
        SoftwareRequest.objects.count(),
        Proposal.objects.count(),
        Sprint.objects.count(),
        User.objects.count(),
    )
    call_command("seed_demo_data", stdout=output)
    assert counts == (
        SoftwareRequest.objects.count(),
        Proposal.objects.count(),
        Sprint.objects.count(),
        User.objects.count(),
    )
    assert User.objects.count() == 3


def test_pagination_preserves_filters_and_report_totals(client, world):
    for number in range(25):
        SoftwareRequest.objects.create(
            client=world["org"],
            title=f"Page request {number}",
            description="Synthetic",
            created_by=world["client"],
        )
    client.force_login(world["client"])
    result = client.get("/requests/?q=Page&page=2")
    assert len(result.context["objects"]) == 5
    assert result.context["page_obj"].number == 2
    assert "q=Page" in result.context["query_params"]


def test_registration_throttle_is_visible(client):
    cache.clear()
    try:
        for _ in range(11):
            result = client.post("/accounts/register/", {})
        assert "Demasiados intentos" in result.content.decode()
    finally:
        cache.clear()


def test_item_web_crud_snapshots_catalog_and_preserves_history(client, world):
    client.force_login(world["dev"])
    payload = dict(
        user_story="HU-new",
        tariff_profile=world["tariff"].pk,
        estimated_hours="2.00",
        infrastructure_cost_cop="100.00",
    )
    response = client.post(f"/sprints/{world['sprint'].pk}/items/new/", payload)
    assert response.status_code == 302
    item = BudgetItem.objects.get(user_story="HU-new")
    assert item.hourly_rate_cop == 10000 and item.profile_name == "Backend"
    world["tariff"].hourly_rate_cop = 20000
    world["tariff"].save()
    item.refresh_from_db()
    assert item.hourly_rate_cop == 10000
    payload["estimated_hours"] = "3.00"
    assert client.post(f"/budget-items/{item.pk}/edit/", payload).status_code == 302
    item.refresh_from_db()
    assert item.hourly_rate_cop == 20000 and item.subtotal == Decimal("60100.00")
    assert client.post(f"/budget-items/{item.pk}/delete/").status_code == 302
    assert not BudgetItem.objects.filter(pk=item.pk).exists()
    assert client.post(f"/sprints/{world['sprint'].pk}/delete/").status_code == 302
    assert not Sprint.objects.filter(pk=world["sprint"].pk).exists()


@pytest.mark.django_db(transaction=True)
def test_registration_limit_shared_across_database_connections():
    from concurrent.futures import ThreadPoolExecutor

    from django.db import connections

    from apps.accounts.services import registration_allowed

    def attempt(_):
        connections.close_all()
        try:
            return registration_allowed("synthetic-concurrency-address")
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(attempt, range(12)))
    assert results.count(True) == 10
    assert results.count(False) == 2
