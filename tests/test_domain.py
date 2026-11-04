from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, connections, transaction
from django.utils import timezone

from apps.accounts.forms import RegistrationForm
from apps.accounts.models import User
from apps.budgets.models import BudgetItem, ExchangeRateSnapshot, Sprint, TariffProfile
from apps.clients.models import Client
from apps.common.money import total
from apps.proposals.models import Proposal
from apps.proposals.selectors import latest, proposal_total
from apps.proposals.services import add_note, new_version, transition

pytestmark = pytest.mark.django_db


def test_decimal_rounding_and_orm_sum(world):
    assert world["item"].subtotal == Decimal("13000.00")
    assert proposal_total(world["proposal"]) == Decimal("13000.00")
    world["item"].delete()
    for index, hours in enumerate(["0.25", "0.50"]):
        BudgetItem.objects.create(
            sprint=world["sprint"],
            tariff_profile=world["tariff"],
            profile_name="Backend",
            profile_level="JR",
            user_story=str(index),
            estimated_hours=Decimal(hours),
            hourly_rate_cop=Decimal("0.01"),
            infrastructure_cost_cop=0,
        )
    assert total(world["sprint"].items.all()) == Decimal("0.01")
    assert total(BudgetItem.objects.none()) == 0


def test_registration_fixed_role_and_rollback(world):
    data = dict(
        username="new",
        email="new@example.invalid",
        organization_name="New org",
        industry="IT",
        password1="Complex-pass-9142!",
        password2="Complex-pass-9142!",
        role="DEVELOPER",
        is_staff=True,
        client=world["other"].pk,
    )
    form = RegistrationForm(data)
    assert form.is_valid(), form.errors
    user = form.save()
    assert user.role == "CLIENT" and not user.is_staff and user.client_id != world["other"].pk
    data.update(username="another", email="another@example.invalid")
    form = RegistrationForm(data)
    assert form.is_valid(), form.errors
    count = Client.objects.count()
    with patch.object(User, "save", side_effect=IntegrityError):
        with pytest.raises(IntegrityError):
            form.save()
    assert Client.objects.count() == count


def test_database_constraints(world):
    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.create_user(
            username="duplicate", email="CLIENT@EXAMPLE.INVALID", client=world["org"]
        )
    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.create_user(username="missing", email="missing@example.invalid")
    with pytest.raises(IntegrityError), transaction.atomic():
        TariffProfile.objects.create(profile="BACKEND", level="JR", hourly_rate_cop=1)
    with pytest.raises(IntegrityError), transaction.atomic():
        Proposal.objects.create(
            software_request=world["request"], version=1, created_by=world["dev"]
        )
    with pytest.raises(IntegrityError), transaction.atomic():
        Sprint.objects.create(
            proposal=world["proposal"], number=1, start_date="2026-01-01", end_date="2026-01-02"
        )
    with pytest.raises(IntegrityError), transaction.atomic():
        BudgetItem.objects.create(
            sprint=world["sprint"],
            tariff_profile=world["tariff"],
            user_story="HU-01",
            estimated_hours=1,
            hourly_rate_cop=1,
            infrastructure_cost_cop=0,
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("estimated_hours", "0"),
        ("hourly_rate_cop", "-1"),
        ("infrastructure_cost_cop", "-1"),
        ("estimated_hours", "1000000"),
        ("estimated_hours", "1.001"),
    ],
)
def test_invalid_money_rejected(world, field, value):
    item = world["item"]
    setattr(item, field, Decimal(value))
    with pytest.raises(ValidationError):
        item.full_clean()


def test_sprint_dates_and_number(world):
    sprint = world["sprint"]
    sprint.end_date = "2025-01-01"
    with pytest.raises(ValidationError):
        sprint.full_clean()
    sprint.end_date = sprint.start_date
    sprint.number = 0
    with pytest.raises(ValidationError):
        sprint.full_clean()


def test_submit_requirements_and_roles(world):
    proposal = world["proposal"]
    proposal.technical_scope = ""
    proposal.save()
    with pytest.raises(ValidationError):
        transition(world["dev"], proposal.pk, "submit")
    with pytest.raises(PermissionDenied):
        transition(world["client"], proposal.pk, "submit")
    proposal.technical_scope = "Complete"
    proposal.save()
    world["item"].delete()
    with pytest.raises(ValidationError):
        transition(world["dev"], proposal.pk, "submit")


def test_transitions_clone_acceptance_history(world):
    p = transition(world["dev"], world["proposal"].pk, "submit")
    add_note(
        world["client"],
        p.pk,
        dict(type="COUNTEROFFER", message="Discuss scope", proposed_amount_cop=100),
    )
    p.refresh_from_db()
    assert p.status == "SUBMITTED"
    add_note(
        world["dev"],
        p.pk,
        dict(type="COMMENT", message="Review accepted", proposed_amount_cop=None),
        True,
    )
    p.refresh_from_db()
    assert p.status == "NEGOTIATING"
    for user in [world["dev"], world["outsider"]]:
        with pytest.raises(PermissionDenied):
            transition(user, p.pk, "accept")
    ExchangeRateSnapshot.objects.create(cop_per_usd=4000, effective_at=timezone.now())
    p = transition(world["client"], p.pk, "accept")
    assert p.accepted_total_cop == Decimal("13000.00") and p.accepted_total_usd == Decimal("3.25")
    assert p.accepted_by == world["client"] and p.accepted_at
    revision = new_version(world["dev"], world["request"].pk, p.pk)
    assert revision.version == 2 and revision.notes.count() == 0 and revision.sprints.count() == 1
    assert proposal_total(revision) == proposal_total(p)
    world["tariff"].hourly_rate_cop = 99999
    world["tariff"].save()
    assert proposal_total(p) == Decimal("13000.00")
    assert proposal_total(revision) == Decimal("13000.00")
    transition(world["dev"], revision.pk, "submit")
    transition(world["client"], revision.pk, "accept")
    p.refresh_from_db()
    assert p.status == "SUPERSEDED" and p.accepted_total_cop == Decimal("13000.00")
    assert latest(Proposal.objects.all()).count() == 1
    with pytest.raises(ValidationError):
        new_version(world["dev"], world["request"].pk, p.pk)
    with pytest.raises(ValidationError):
        add_note(world["client"], p.pk, dict(type="COMMENT", message="Late"))


def test_reject_terminal_and_closed_request(world):
    p = transition(world["dev"], world["proposal"].pk, "submit")
    transition(world["client"], p.pk, "reject")
    with pytest.raises(ValidationError):
        transition(world["client"], p.pk, "accept")
    world["request"].status = "CLOSED"
    world["request"].save()
    with pytest.raises(ValidationError):
        new_version(world["dev"], world["request"].pk, p.pk)


def test_acceptance_without_fx(world):
    transition(world["dev"], world["proposal"].pk, "submit")
    p = transition(world["client"], world["proposal"].pk, "accept")
    assert p.accepted_total_cop == 13000 and p.accepted_total_usd is None


@pytest.mark.django_db(transaction=True)
def test_concurrent_versions_use_separate_connections(world):
    def clone():
        connections.close_all()
        try:
            user = User.objects.get(pk=world["dev"].pk)
            try:
                return new_version(user, world["request"].pk, world["proposal"].pk).version
            except ValidationError:
                return "conflict"
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: clone(), range(2)))
    assert sorted(str(x) for x in results) == ["2", "conflict"]
    assert Proposal.objects.filter(software_request=world["request"]).count() == 2


@pytest.mark.django_db(transaction=True)
def test_concurrent_acceptance_has_one_current_agreement(world):
    p1 = transition(world["dev"], world["proposal"].pk, "submit")
    p2 = new_version(world["dev"], world["request"].pk, p1.pk)
    transition(world["dev"], p2.pk, "submit")

    def accept(pk):
        connections.close_all()
        try:
            try:
                return transition(User.objects.get(pk=world["client"].pk), pk, "accept").pk
            except ValidationError:
                return "conflict"
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(accept, [p1.pk, p2.pk]))
    assert Proposal.objects.filter(status="ACCEPTED").count() == 1
    assert Proposal.objects.get(pk=p2.pk).status == "ACCEPTED"
