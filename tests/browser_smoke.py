"""Run an actual Chromium workflow with ephemeral, randomly generated credentials.

Execute with: uv run --with playwright python tests/browser_smoke.py
"""

import os
import secrets
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

import django

django.setup()

from playwright.sync_api import sync_playwright

from apps.accounts.models import User
from apps.proposals.models import Proposal


def database_call(function):
    from concurrent.futures import ThreadPoolExecutor

    from django.db import connections

    def execute():
        try:
            return function()
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(execute).result()


def run():
    token = secrets.token_hex(5)
    password = secrets.token_urlsafe(24)
    developer = User.objects.create_user(
        username=f"browser-dev-{token}",
        email=f"browser-dev-{token}@example.invalid",
        password=password,
        role="DEVELOPER",
    )
    server = subprocess.Popen(
        [sys.executable, "manage.py", "runserver", "127.0.0.1:8001", "--noreload"],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base = "http://127.0.0.1:8001"
    try:
        for _ in range(50):
            try:
                if urlopen(base + "/health/", timeout=1).status == 200:
                    break
            except OSError:
                time.sleep(0.1)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(args=["--disable-gpu"])
            page = browser.new_page(viewport={"width": 1440, "height": 1000}, locale="es-CO")
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on(
                "console",
                lambda message: errors.append(message.text) if message.type == "error" else None,
            )
            page.goto(base + "/accounts/register/")
            for field, value in {
                "username": f"browser-client-{token}",
                "email": f"browser-client-{token}@example.invalid",
                "organization_name": f"Smoke Organization {token}",
                "industry": "Synthetic services",
                "password1": password,
                "password2": password,
            }.items():
                page.locator(f"#id_{field}").fill(value)
            page.get_by_role("button", name="Crear mi cuenta").click()
            page.wait_for_url("**/dashboard/")
            page.goto(base + "/requests/new/")
            page.locator("#id_title").fill(f"Browser portal {token}")
            page.locator("#id_description").fill("Synthetic full browser workflow.")
            page.get_by_role("button", name="Guardar").click()
            page.wait_for_url("**/requests/*/")
            request_url = page.url
            page.locator("#app-sidebar").get_by_role("button", name="Cerrar sesión").click()
            page.goto(base + "/accounts/login/")
            page.locator("#id_username").fill(developer.username)
            page.locator("#id_password").fill(password)
            page.get_by_role("button", name="Ingresar").click()
            page.wait_for_url("**/dashboard/")
            page.goto(request_url)
            page.get_by_role("button", name="Crear propuesta v1").click()
            page.wait_for_url("**/edit/")
            for field in ["technical_scope", "technologies", "exclusions", "service_conditions"]:
                page.locator(f"#id_{field}").fill("Complete synthetic scope and conditions.")
            page.get_by_role("button", name="Guardar").click()
            page.wait_for_url("**/proposals/*/")
            proposal_url = page.url
            proposal_id = int(proposal_url.rstrip("/").split("/")[-1])
            for number in range(1, 5):
                page.goto(proposal_url + "#sprints")
                page.get_by_role("link", name="Añadir sprint").first.click()
                for field, value in {
                    "number": str(number),
                    "goal": f"Delivery {number}",
                    "deliverables": "Validated features",
                    "start_date": "2026-10-25",
                    "end_date": "2026-11-07",
                }.items():
                    page.locator(f"#id_{field}").fill(value)
                page.get_by_role("button", name="Guardar").click()
                page.wait_for_url(proposal_url)
            for url, filename in [
                ("/imports/tariffs/", "catalogo_perfiles_y_tarifas.csv"),
                (f"/proposals/{proposal_id}/imports/budget-items/", "items_estimacion_sprint.csv"),
            ]:
                page.goto(base + url)
                page.locator("#id_file").set_input_files(ROOT / "sample-data" / filename)
                page.get_by_role("button", name="Validar y previsualizar").click()
                page.screenshot(path=f"/workspace/import-preview-{filename}.png", full_page=True)
                page.get_by_role("button", name="Confirmar importación", exact=False).click()
                page.wait_for_load_state("networkidle")
            page.goto(proposal_url)
            assert page.get_by_text("HU-08", exact=True).count() >= 1
            page.screenshot(path="/workspace/scopedeal-desktop.png", full_page=True)
            page.get_by_role("button", name="Enviar propuesta").click()
            page.get_by_role("button", name="Confirmar envío").click()
            page.wait_for_load_state("networkidle")
            page.locator("#app-sidebar").get_by_role("button", name="Cerrar sesión").click()
            page.goto(base + "/accounts/login/")
            page.locator("#id_username").fill(f"browser-client-{token}")
            page.locator("#id_password").fill(password)
            page.get_by_role("button", name="Ingresar").click()
            page.wait_for_url("**/dashboard/")
            page.goto(proposal_url)
            page.get_by_role("link", name="Historial de negociación", exact=True).click()
            page.locator("#id_type").select_option("COUNTEROFFER")
            page.locator("#id_message").fill("Discuss delivery dates and pricing.")
            page.locator("#id_proposed_amount_cop").fill("3000000")
            page.get_by_role("button", name="Publicar observación").click()
            page.wait_for_load_state("networkidle")
            page.get_by_role("button", name="Revisar aceptación").click()
            page.get_by_role("button", name="Acepto esta versión y sus condiciones").click()
            page.wait_for_load_state("networkidle")
            assert database_call(lambda: Proposal.objects.get(pk=proposal_id).status) == "ACCEPTED"
            page.set_viewport_size({"width": 390, "height": 844})
            page.screenshot(path="/workspace/scopedeal-mobile.png", full_page=True)
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            page.goto(base + "/reports/budgets/?status=ACCEPTED&sprint=1")
            assert page.get_by_role("heading", name="Costos por sprint").count() == 1
            page.goto(proposal_url + "exchange-rate/")
            assert page.get_by_role("heading", name="Conversión indicativa COP / USD").count() == 1
            page.set_viewport_size({"width": 1440, "height": 1000})
            page.locator("#app-sidebar").get_by_role("button", name="Cerrar sesión").click()
            page.goto(base + "/accounts/login/")
            page.locator("#id_username").fill(developer.username)
            page.locator("#id_password").fill(password)
            page.get_by_role("button", name="Ingresar").click()
            page.wait_for_url("**/dashboard/")
            page.goto(proposal_url)
            page.get_by_role("button", name="Crear nueva versión").click()
            page.get_by_role("button", name="Crear nueva versión").click()
            page.wait_for_load_state("networkidle")
            assert database_call(
                lambda: Proposal.objects.filter(
                    software_request_id=Proposal.objects.get(pk=proposal_id).software_request_id,
                    version=2,
                    status="DRAFT",
                ).exists()
            )
            revision_url = page.url.removeprefix(base)

            screenshots = Path(
                os.environ.get("SCREENSHOT_DIR", "/workspace/scopedeal-ui-artifacts")
            )
            screenshots.mkdir(parents=True, exist_ok=True)
            for width in [360, 390, 768, 1024, 1440]:
                page.set_viewport_size({"width": width, "height": 1000 if width >= 1024 else 844})
                for name, url in [
                    ("dashboard", "/dashboard/"),
                    ("proposal", f"/proposals/{proposal_id}/"),
                    ("budget", f"/proposals/{proposal_id}/budget/"),
                    ("imports", "/imports/tariffs/"),
                    ("reports", "/reports/budgets/"),
                    ("requests", "/requests/"),
                    ("clients", "/clients/"),
                    ("tariffs", "/tariffs/"),
                    ("negotiation", f"/proposals/{proposal_id}/#negotiation"),
                    ("proposal-form", revision_url + "edit/"),
                    ("request-form", "/requests/new/"),
                    ("client-form", "/clients/new/"),
                    ("tariff-form", "/tariffs/new/"),
                ]:
                    page.goto(base + url)
                    page.wait_for_function(
                        "getComputedStyle(document.body).backgroundColor === 'rgb(245, 248, 252)'"
                    )
                    assert page.evaluate(
                        "document.documentElement.scrollWidth <= window.innerWidth"
                    ), (name, width)
                    assert (
                        page.locator(
                            'script[src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4"]'
                        ).count()
                        == 1
                    )
                    assert page.locator("h1").count() == 1
                    duplicates = page.evaluate(
                        """() => { const seen=new Set(); return [...document.querySelectorAll('[id]')].filter(el=>seen.has(el.id)||!seen.add(el.id)).map(el=>el.id); }"""
                    )
                    assert not duplicates, (name, width, duplicates)
                    assert page.locator("input:not([type=hidden]),select,textarea").evaluate_all(
                        "elements => elements.every(el => el.labels?.length || el.getAttribute('aria-label'))"
                    ), (name, width)
                    page.screenshot(
                        path=str(screenshots / f"{name}-{width}.png"),
                        full_page=name != "negotiation",
                    )
                if width < 1024:
                    page.get_by_role("button", name="Abrir menú").click()
                    assert (
                        page.locator("#navigation-toggle").get_attribute("aria-expanded") == "true"
                    )
                    page.keyboard.press("Escape")
                    assert (
                        page.locator("#navigation-toggle").get_attribute("aria-expanded") == "false"
                    )
            assert not errors, errors
            page.goto(base)
            page.keyboard.press("Tab")
            assert page.locator(".skip").evaluate("element => element === document.activeElement")
            browser.close()
            print(
                "PASS: Chromium registration, request, proposal, four sprints, CSVs, submit, counteroffer, acceptance, clone, reports, FX screen, mobile overflow and keyboard skip link."
            )
    finally:
        server.terminate()
        server.wait(timeout=10)
        User.objects.filter(username__in=[developer.username, f"browser-client-{token}"]).update(
            is_active=False
        )


if __name__ == "__main__":
    run()
