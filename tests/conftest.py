import secrets
from datetime import date
from decimal import Decimal

import pytest

from apps.accounts.models import User
from apps.budgets.models import BudgetItem, Sprint, TariffProfile
from apps.clients.models import Client, SoftwareRequest
from apps.proposals.services import new_version


@pytest.fixture
def world(db):
    org = Client.objects.create(
        name="Synthetic A", industry="Services", contact_email="a@example.invalid"
    )
    other = Client.objects.create(
        name="Synthetic B", industry="Services", contact_email="b@example.invalid"
    )
    dev = User.objects.create_user(
        username="dev",
        email="dev@example.invalid",
        password=secrets.token_urlsafe(24),
        role="DEVELOPER",
    )
    client = User.objects.create_user(
        username="client",
        email="client@example.invalid",
        password=secrets.token_urlsafe(24),
        client=org,
    )
    outsider = User.objects.create_user(
        username="outsider",
        email="outsider@example.invalid",
        password=secrets.token_urlsafe(24),
        client=other,
    )
    request = SoftwareRequest.objects.create(
        client=org, title="Portal", description="Operations portal", created_by=client
    )
    proposal = new_version(dev, request.pk)
    for field in ["technical_scope", "technologies", "exclusions", "service_conditions"]:
        setattr(proposal, field, "Complete requirements")
    proposal.save()
    sprint = Sprint.objects.create(
        proposal=proposal,
        number=1,
        goal="Delivery",
        deliverables="Working portal",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 14),
    )
    tariff = TariffProfile.objects.create(
        profile="Backend", level="JR", hourly_rate_cop=Decimal(10000)
    )
    item = BudgetItem.objects.create(
        sprint=sprint,
        tariff_profile=tariff,
        profile_name="Backend",
        profile_level="JR",
        user_story="HU-01",
        estimated_hours=Decimal("1.25"),
        hourly_rate_cop=tariff.hourly_rate_cop,
        infrastructure_cost_cop=Decimal(500),
    )
    return dict(
        org=org,
        other=other,
        dev=dev,
        client=client,
        outsider=outsider,
        request=request,
        proposal=proposal,
        sprint=sprint,
        tariff=tariff,
        item=item,
    )


@pytest.fixture(autouse=True)
def forbid_unmocked_http(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("External HTTP must be explicitly mocked in automated tests")

    monkeypatch.setattr("integrations.exchange_rates.httpx.get", blocked)
