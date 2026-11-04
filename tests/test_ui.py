from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.budgets.models import BudgetItem, ExchangeRateSnapshot, TariffProfile
from apps.common.templatetags.presentation import amount
from apps.proposals.models import Proposal
from apps.proposals.services import new_version, transition

pytestmark = pytest.mark.django_db
ROOT = Path(__file__).resolve().parents[1]
CDN = "https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4"


def tariff_upload():
    return SimpleUploadedFile(
        "catalog.csv",
        b"profile,level,hourly_rate_cop\nArchitect,SR,90000.00\n",
        content_type="text/csv",
    )


def test_shared_shell_cdn_navigation_and_scoped_dashboard(client, world):
    transition(world["dev"], world["proposal"].pk, "submit")
    client.force_login(world["client"])
    client.post(
        f"/proposals/{world['proposal'].pk}/notes/new/",
        dict(type="COMMENT", message="Visible history", proposed_amount_cop=""),
    )
    page = client.get("/dashboard/")
    assert page.status_code == 200
    assert page.content.decode().count(CDN) == 1
    assert "cdn.tailwindcss.com" not in page.content.decode()
    assert page.context["proposal_count"] == 1
    assert page.context["pending_count"] == 1
    assert page.context["status_chart"]["count"] == 1
    assert b"Visible history" in page.content
    assert b'aria-controls="app-sidebar"' in page.content
    assert b"/tariffs/" not in page.content
    client.force_login(world["outsider"])
    page = client.get("/dashboard/")
    assert page.context["proposal_count"] == 0
    assert not page.context["recent_notes"]
    assert b"Visible history" not in page.content


def test_budget_screen_decimal_totals_and_mobile_cards(client, world):
    ExchangeRateSnapshot.objects.create(cop_per_usd=4000, effective_at=timezone.now())
    client.force_login(world["dev"])
    page = client.get(f"/proposals/{world['proposal'].pk}/budget/")
    assert page.status_code == 200
    assert page.context["budget_only"] is True
    budget = page.context["budget"]
    assert budget["hours"] == Decimal("1.25")
    assert budget["development"] == Decimal("12500.00")
    assert budget["infrastructure"] == Decimal("500.00")
    assert budget["total"] == Decimal("13000.00")
    assert budget["usd"] == Decimal("3.25")
    assert budget["sprints"][0].items.all()[0].subtotal_usd == Decimal("3.25")
    assert b"lg:hidden" in page.content
    assert "13.000,00" in page.content.decode()
    assert b"ExchangeRate-API" in page.content
    assert b"Fecha efectiva" in page.content
    client.force_login(world["client"])
    page = client.get(f"/proposals/{world['proposal'].pk}/budget/")
    assert b"/items/new/" not in page.content and b"/delete/" not in page.content
    client.force_login(world["outsider"])
    assert client.get(f"/proposals/{world['proposal'].pk}/budget/").status_code == 404


def test_proposal_search_combines_filters_and_never_leaks_clients(client, world):
    client.force_login(world["dev"])
    result = client.get("/proposals/?q=Portal&status=DRAFT&sprint=1")
    assert list(result.context["objects"]) == [world["proposal"]]
    assert client.get("/proposals/?q=missing").context["proposal_count"] == 0
    client.force_login(world["outsider"])
    assert client.get("/proposals/?q=Portal").context["proposal_count"] == 0
    assert b"Portal" not in client.get("/proposals/").content


def test_preview_does_not_write_commit_is_explicit_and_token_single_use(client, world):
    client.force_login(world["dev"])
    count = TariffProfile.objects.count()
    response = client.post("/imports/tariffs/", {"action": "preview", "file": tariff_upload()})
    assert response.status_code == 200
    assert TariffProfile.objects.count() == count
    preview = response.context["preview"]
    assert preview["row_count"] == 1 and preview["created"] == 1
    assert "Aún no se ha guardado ningún cambio" in response.content.decode()
    assert (
        client.post(
            "/imports/tariffs/", {"action": "commit", "preview_token": preview["token"]}
        ).status_code
        == 302
    )
    assert TariffProfile.objects.count() == count + 1
    replay = client.post(
        "/imports/tariffs/", {"action": "commit", "preview_token": preview["token"]}
    )
    assert replay.status_code == 200 and replay.context["form"].errors
    assert TariffProfile.objects.count() == count + 1


def test_preview_revalidates_target_state_permissions_and_expiration(client, world):
    client.force_login(world["dev"])
    path = f"/proposals/{world['proposal'].pk}/imports/budget-items/"
    body = b"sprint_number,user_story,profile,level,estimated_hours,infrastructure_cost_cop\n1,HU-preview,Backend,JR,2.00,0.00\n"
    response = client.post(
        path,
        {
            "action": "preview",
            "file": SimpleUploadedFile("items.csv", body, content_type="text/csv"),
        },
    )
    token = response.context["preview"]["token"]
    assert not BudgetItem.objects.filter(user_story="HU-preview").exists()
    assert (
        client.post("/imports/tariffs/", {"action": "commit", "preview_token": token})
        .context["form"]
        .errors
    )
    session = client.session
    session["csv_preview"]["timestamp"] -= 901
    session.save()
    assert client.post(path, {"action": "commit", "preview_token": token}).context["form"].errors
    response = client.post(
        path,
        {
            "action": "preview",
            "file": SimpleUploadedFile("items.csv", body, content_type="text/csv"),
        },
    )
    token = response.context["preview"]["token"]
    transition(world["dev"], world["proposal"].pk, "submit")
    assert client.post(path, {"action": "commit", "preview_token": token}).status_code == 403
    assert not BudgetItem.objects.filter(user_story="HU-preview").exists()
    client.force_login(world["client"])
    assert (
        client.post("/imports/tariffs/", {"action": "preview", "file": tariff_upload()}).status_code
        == 403
    )


def test_invalid_preview_reports_line_errors_with_zero_writes(client, world):
    client.force_login(world["dev"])
    before = list(TariffProfile.objects.values())
    content = (ROOT / "sample-data" / "catalogo_perfiles_y_tarifas_invalid.csv").read_bytes()
    response = client.post(
        "/imports/tariffs/",
        {
            "action": "preview",
            "file": SimpleUploadedFile("bad.csv", content, content_type="text/csv"),
        },
    )
    assert response.status_code == 200 and response.context["form"].errors
    assert "Línea 3" in response.content.decode()
    assert "No se guardaron filas parciales" in response.content.decode()
    assert before == list(TariffProfile.objects.values())


def test_confirmation_views_do_not_change_state_or_delete_data(client, world):
    client.force_login(world["dev"])
    proposal = world["proposal"]
    result = client.post(f"/proposals/{proposal.pk}/submit/", {"review": "yes"})
    assert result.status_code == 200 and "Confirmar envío" in result.content.decode()
    proposal.refresh_from_db()
    assert proposal.status == "DRAFT"
    result = client.post(f"/proposals/{proposal.pk}/clone/", {"review": "yes"})
    assert result.status_code == 200 and Proposal.objects.count() == 1
    result = client.post(f"/sprints/{world['sprint'].pk}/delete/", {"review": "yes"})
    assert result.status_code == 200 and BudgetItem.objects.count() == 1
    assert (
        client.post(
            f"/requests/{world['request'].pk}/actions/close/", {"review": "yes"}
        ).status_code
        == 200
    )
    world["request"].refresh_from_db()
    assert world["request"].status == "NEW"


def test_only_latest_open_version_exposes_clone_action(client, world):
    client.force_login(world["dev"])
    revision = new_version(world["dev"], world["request"].pk, world["proposal"].pk)
    old = client.get(f"/proposals/{world['proposal'].pk}/")
    assert not old.context["can_clone"]
    latest = client.get(f"/proposals/{revision.pk}/")
    assert latest.context["can_clone"]
    world["request"].status = "CLOSED"
    world["request"].save()
    assert not client.get(f"/proposals/{revision.pk}/").context["can_clone"]


def test_client_detail_and_tariff_search_are_real_and_authorized(client, world):
    client.force_login(world["dev"])
    page = client.get(f"/clients/{world['org'].pk}/")
    assert page.status_code == 200 and b"Portal" in page.content
    assert len(client.get("/tariffs/?q=Backend").context["objects"]) == 1
    assert len(client.get("/tariffs/?q=NoMatch").context["objects"]) == 0
    client.force_login(world["client"])
    assert client.get(f"/clients/{world['other'].pk}/").status_code == 403
    assert b"Portal" in client.get("/clients/me/").content


def test_global_exchange_card_handles_failure_and_stale_snapshot(client, world):
    client.force_login(world["client"])
    with patch(
        "integrations.exchange_rates.httpx.get", side_effect=httpx.TimeoutException("private error")
    ):
        page = client.get("/exchange-rate/")
        assert page.status_code == 200
        assert (
            "Tasa no disponible" in page.content.decode() and b"private error" not in page.content
        )
    ExchangeRateSnapshot.objects.create(
        cop_per_usd=4000, effective_at=timezone.now() - timedelta(days=2)
    )
    page = client.get("/dashboard/")
    assert page.context["stale"] is True and "Desactualizada" in page.content.decode()


def test_money_filter_preserves_decimal_precision():
    assert amount(Decimal("999999999999.995")) == "1.000.000.000.000,00"
    assert amount(Decimal("0.005")) == "0,01"
    assert amount(None) == "—"
