from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError
from django.test import Client as WebClient

from apps.accounts.models import User
from apps.budgets.models import BudgetItem, Sprint
from apps.clients.models import SoftwareRequest
from apps.proposals.models import Proposal
from apps.proposals.services import new_version, transition

pytestmark = pytest.mark.django_db


def test_public_pages_login_logout_csrf_and_health(client, world):
    for url in [
        "/",
        "/accounts/login/",
        "/accounts/register/",
        "/accounts/password_reset/",
        "/health/",
    ]:
        assert client.get(url).status_code == 200
    assert client.get("/dashboard/").status_code == 302
    client.force_login(world["client"])
    assert client.get("/accounts/logout/").status_code == 405
    assert client.post("/accounts/logout/").status_code == 302
    strict = WebClient(enforce_csrf_checks=True)
    strict.force_login(world["dev"])
    assert strict.post(f"/proposals/{world['proposal'].pk}/submit/").status_code == 403
    with patch("apps.common.views.connections") as connections:
        connections.__getitem__.return_value.cursor.side_effect = DatabaseError(
            "private database details"
        )
        result = client.get("/health/")
        assert result.status_code == 503 and b"private" not in result.content


def test_public_registration_http_ignores_privilege_fields(client, world):
    result = client.post(
        "/accounts/register/",
        dict(
            username="public",
            email="public@example.invalid",
            organization_name="Public Organization",
            industry="IT",
            password1="Secure-new-8721!",
            password2="Secure-new-8721!",
            role="DEVELOPER",
            is_staff="true",
            client=world["other"].pk,
        ),
    )
    assert result.status_code == 302
    user = User.objects.get(username="public")
    assert (
        user.role == "CLIENT"
        and not user.is_staff
        and user.client_id not in [world["org"].pk, world["other"].pk]
    )


def test_developer_pages_and_client_navigation(client, world):
    client.force_login(world["dev"])
    p = world["proposal"].pk
    for url in [
        "/dashboard/",
        "/clients/",
        "/clients/new/",
        f"/clients/{world['org'].pk}/edit/",
        "/requests/",
        "/requests/new/",
        f"/requests/{world['request'].pk}/",
        "/proposals/",
        f"/proposals/{p}/",
        f"/proposals/{p}/edit/",
        f"/proposals/{p}/sprints/new/",
        f"/sprints/{world['sprint'].pk}/edit/",
        f"/sprints/{world['sprint'].pk}/items/new/",
        f"/budget-items/{world['item'].pk}/edit/",
        "/tariffs/",
        "/tariffs/new/",
        "/imports/tariffs/",
        f"/proposals/{p}/imports/budget-items/",
        "/reports/proposals/",
        "/reports/budgets/",
    ]:
        response = client.get(url)
        assert response.status_code == 200, (url, response.content[:500])
        assert b"ScopeDeal" in response.content
    client.force_login(world["client"])
    for url in ["/dashboard/", "/clients/me/", "/requests/", "/proposals/", "/reports/budgets/"]:
        assert client.get(url).status_code == 200
    assert b"/tariffs/" not in client.get("/dashboard/").content


def test_tenant_isolation_read_post_and_reports(client, world):
    client.force_login(world["outsider"])
    p = world["proposal"].pk
    for url in [
        f"/requests/{world['request'].pk}/",
        f"/requests/{world['request'].pk}/edit/",
        f"/proposals/{p}/",
        f"/proposals/{p}/exchange-rate/",
        f"/reports/budgets/?proposal={p}",
    ]:
        assert client.get(url).status_code == 404
    for url in [
        f"/proposals/{p}/accept/",
        f"/proposals/{p}/notes/new/",
        f"/requests/{world['request'].pk}/actions/delete/",
    ]:
        assert (
            client.post(url, {"confirm": "yes", "message": "Attack", "type": "COMMENT"}).status_code
            == 404
        )
    response = client.get(f"/reports/budgets/?client={world['org'].pk}&sprint=1")
    assert b"Portal" not in response.content and b"13000" not in response.content
    client.force_login(world["client"])
    for url in [
        "/tariffs/",
        "/clients/",
        "/imports/tariffs/",
        f"/proposals/{p}/edit/",
        f"/sprints/{world['sprint'].pk}/edit/",
        f"/budget-items/{world['item'].pk}/edit/",
        f"/proposals/{p}/imports/budget-items/",
    ]:
        assert client.get(url).status_code == 403
        assert client.post(url).status_code == 403
    assert client.post(f"/proposals/{p}/submit/").status_code == 403


def test_request_creation_edit_lifecycle_and_closed(client, world):
    client.force_login(world["client"])
    response = client.post(
        "/requests/new/",
        dict(
            title="New request",
            description="Work",
            priority="HIGH",
            client=world["other"].pk,
            status="CLOSED",
        ),
    )
    assert response.status_code == 302
    obj = SoftwareRequest.objects.get(title="New request")
    assert obj.client_id == world["org"].pk and obj.status == "NEW"
    assert (
        client.post(
            f"/requests/{obj.pk}/edit/",
            dict(title="Edited", description="New text", priority="LOW"),
        ).status_code
        == 302
    )
    assert client.post(f"/requests/{obj.pk}/actions/review/").status_code == 403
    assert client.get(f"/requests/{world['request'].pk}/edit/").status_code == 403
    assert client.post(f"/requests/{world['request'].pk}/actions/delete/").status_code == 403
    client.force_login(world["dev"])
    assert client.post(f"/requests/{obj.pk}/actions/review/").status_code == 302
    obj.refresh_from_db()
    assert obj.status == "IN_REVIEW"
    assert client.post(f"/requests/{obj.pk}/actions/close/").status_code == 302
    assert client.post(f"/requests/{obj.pk}/proposals/new/").status_code == 302
    assert obj.proposals.count() == 0


@pytest.mark.parametrize(
    "status", ["SUBMITTED", "NEGOTIATING", "ACCEPTED", "REJECTED", "SUPERSEDED"]
)
def test_non_draft_web_content_immutable(client, world, status):
    Proposal.objects.filter(pk=world["proposal"].pk).update(status=status)
    client.force_login(world["dev"])
    for url in [
        f"/proposals/{world['proposal'].pk}/edit/",
        f"/sprints/{world['sprint'].pk}/edit/",
        f"/budget-items/{world['item'].pk}/edit/",
        f"/proposals/{world['proposal'].pk}/imports/budget-items/",
    ]:
        assert client.get(url).status_code == 403
        assert client.post(url, dict(technical_scope="Mutated")).status_code == 403
    assert client.post(f"/budget-items/{world['item'].pk}/delete/").status_code == 403
    assert client.post(f"/sprints/{world['sprint'].pk}/delete/").status_code == 403
    world["proposal"].refresh_from_db()
    assert world["proposal"].technical_scope == "Complete requirements"


def test_combined_reports_and_latest_versions(client, world):
    client.force_login(world["dev"])
    p = world["proposal"]
    revision = new_version(world["dev"], world["request"].pk, p.pk)
    result = client.get(
        f"/reports/budgets/?client={world['org'].pk}&status=DRAFT&start=2020-01-01&end=2030-01-01&sprint=1"
    )
    assert list(result.context["objects"]) == [revision]
    assert result.context["total"] == Decimal("13000.00")
    assert list(result.context["groups"])[0]["hours"] == Decimal("1.25")
    result = client.get("/reports/budgets/?history=on")
    assert result.context["total"] == Decimal("26000.00")
    assert client.get("/reports/proposals/?sprint=-1").context["objects"].count() == 0
    assert (
        client.get("/reports/proposals/?start=2030-01-01&end=2020-01-01").context["objects"].count()
        == 0
    )
    assert client.get("/reports/budgets/?proposal=invalid").status_code == 404
    result = client.get("/dashboard/")
    assert result.context["forecast"] == 13000


def test_full_html_workflow_four_sprints_import_negotiate_accept_clone(client, world):
    client.force_login(world["dev"])
    proposal = world["proposal"]
    for number in range(2, 5):
        result = client.post(
            f"/proposals/{proposal.pk}/sprints/new/",
            dict(
                number=number,
                goal=f"Delivery {number}",
                deliverables="Tested features",
                start_date="2026-02-01",
                end_date="2026-02-14",
            ),
        )
        assert result.status_code == 302, result.content[:300]
    root = Path(__file__).resolve().parents[1]
    for url, name in [
        ("/imports/tariffs/", "catalogo_perfiles_y_tarifas.csv"),
        (f"/proposals/{proposal.pk}/imports/budget-items/", "items_estimacion_sprint.csv"),
    ]:
        upload = SimpleUploadedFile(
            name, (root / "sample-data" / name).read_bytes(), content_type="text/csv"
        )
        result = client.post(url, {"file": upload})
        assert result.status_code == 302, result.content[:300]
    assert Sprint.objects.filter(proposal=proposal).count() == 4
    assert BudgetItem.objects.filter(sprint__proposal=proposal).count() == 8
    result = client.get(f"/proposals/{proposal.pk}/")
    assert b"HU-08" in result.content
    assert client.post(f"/proposals/{proposal.pk}/submit/").status_code == 302
    client.force_login(world["client"])
    assert (
        client.post(
            f"/proposals/{proposal.pk}/notes/new/",
            dict(type="COUNTEROFFER", message="Can we reduce scope?", proposed_amount_cop="100000"),
        ).status_code
        == 302
    )
    proposal.refresh_from_db()
    assert proposal.status == "SUBMITTED"
    client.force_login(world["dev"])
    assert (
        client.post(
            f"/proposals/{proposal.pk}/negotiate/",
            dict(type="COMMENT", message="We can discuss delivery dates.", proposed_amount_cop=""),
        ).status_code
        == 302
    )
    client.force_login(world["client"])
    assert client.post(f"/proposals/{proposal.pk}/accept/").status_code == 200
    proposal.refresh_from_db()
    assert proposal.status == "NEGOTIATING"
    assert client.post(f"/proposals/{proposal.pk}/accept/", {"confirm": "yes"}).status_code == 302
    proposal.refresh_from_db()
    assert proposal.status == "ACCEPTED"
    client.force_login(world["dev"])
    assert client.post(f"/proposals/{proposal.pk}/clone/").status_code == 302
    assert Proposal.objects.filter(version=2, status="DRAFT").exists()


def test_fx_failure_screen_keeps_cop_and_escapes_notes(client, world):
    client.force_login(world["client"])
    with patch(
        "integrations.exchange_rates.httpx.get",
        side_effect=httpx.TimeoutException("secret provider message"),
    ):
        result = client.get(f"/proposals/{world['proposal'].pk}/exchange-rate/")
        assert (
            result.status_code == 200
            and b"COP" in result.content
            and b"secret provider" not in result.content
        )
    transition(world["dev"], world["proposal"].pk, "submit")
    client.post(
        f"/proposals/{world['proposal'].pk}/notes/new/",
        dict(type="COMMENT", message="<script>alert(1)</script>", proposed_amount_cop=""),
    )
    result = client.get(f"/proposals/{world['proposal'].pk}/")
    assert b"<script>alert" not in result.content and b"&lt;script&gt;" in result.content
