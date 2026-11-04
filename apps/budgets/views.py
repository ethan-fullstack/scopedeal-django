import base64
import secrets

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.budgets.forms import (
    ItemForm,
    SprintForm,
    TariffForm,
    UploadForm,
)
from apps.budgets.importers import ITEM_HEADERS, TARIFF_HEADERS, import_csv
from apps.budgets.models import BudgetItem, Sprint, TariffProfile
from apps.budgets.services import delete_component, save_component
from apps.common.authorization import developer
from apps.common.money import money
from apps.common.views import draft, form_page, paginate, proposal_object
from apps.proposals.selectors import proposal_total
from integrations.exchange_rates import ExchangeRateUnavailable, get_rate


@login_required
def budget_edit(request, kind, pk=None, parent=None):
    developer(request.user)
    model, form_class = {
        "sprint": (Sprint, SprintForm),
        "item": (BudgetItem, ItemForm),
        "tariff": (TariffProfile, TariffForm),
    }[kind]
    instance = get_object_or_404(model, pk=pk) if pk else None
    proposal = None
    sprint = None
    if kind == "sprint":
        proposal = instance.proposal if instance else proposal_object(request.user, parent)
    if kind == "item":
        sprint = instance.sprint if instance else get_object_or_404(Sprint, pk=parent)
        proposal = sprint.proposal
    if proposal:
        draft(proposal)
    form = form_class(request.POST if request.method == "POST" else None, instance=instance)
    if kind == "item":
        form.fields["tariff_profile"].queryset = TariffProfile.objects.filter(is_active=True)
    if request.method == "POST" and form.is_valid():
        try:
            obj = form.save(commit=False)
            if kind == "sprint":
                obj.proposal = proposal
            if kind == "item":
                obj.sprint = sprint
            save_component(request.user, obj, proposal)
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            return redirect("proposal-detail", pk=proposal.pk) if proposal else redirect("tariffs")
    return form_page(
        request,
        form,
        {"sprint": "Sprint", "item": "Partida presupuestal", "tariff": "Perfil y tarifa"}[kind],
    )


@login_required
@require_POST
def budget_delete(request, kind, pk):
    developer(request.user)
    obj = get_object_or_404(Sprint if kind == "sprint" else BudgetItem, pk=pk)
    proposal = obj.proposal if kind == "sprint" else obj.sprint.proposal
    draft(proposal)
    if request.POST.get("review") == "yes":
        return render(
            request,
            "actions/confirmation.html",
            {
                "subject": str(obj),
                "explanation": "Se eliminará este contenido del borrador. Al eliminar un sprint, también se eliminan sus partidas.",
                "cancel_url": f"/proposals/{proposal.pk}/budget/",
            },
        )
    try:
        delete_component(request.user, obj, proposal)
    except ValidationError:
        messages.error(request, "Solo se puede eliminar contenido de un borrador.")
    return redirect("proposal-detail", pk=proposal.pk)


@login_required
def tariffs(request):
    developer(request.user)
    return render(
        request,
        "list.html",
        {
            "title": "Perfiles y tarifas",
            "objects": paginate(
                request, TariffProfile.objects.filter(profile__icontains=request.GET.get("q", ""))
            )["page_obj"],
            **paginate(
                request, TariffProfile.objects.filter(profile__icontains=request.GET.get("q", ""))
            ),
            "kind": "tariff",
            "new_url": "/tariffs/new/",
        },
    )


@login_required
def upload(request, pk=None):
    developer(request.user)
    if pk:
        draft(proposal_object(request.user, pk))
    form = UploadForm(request.POST if request.method == "POST" else None, request.FILES or None)
    preview = None
    if request.method == "POST" and request.POST.get("action") == "commit":
        stored = request.session.get("csv_preview")
        if (
            not stored
            or stored.get("proposal_id") != pk
            or not secrets.compare_digest(
                stored.get("token", ""), request.POST.get("preview_token", "")
            )
            or timezone.now().timestamp() - stored.get("timestamp", 0) > 900
        ):
            form.add_error(
                None,
                "La vista previa venció o no corresponde a esta propuesta. Valide el archivo nuevamente.",
            )
        else:
            file = SimpleUploadedFile(
                stored["name"],
                base64.b64decode(stored["content"]),
                content_type=stored["content_type"],
            )
            try:
                created, updated = import_csv(request.user, file, pk)
            except (ValidationError, IntegrityError) as exc:
                form.add_error(
                    None,
                    exc
                    if isinstance(exc, ValidationError)
                    else "Conflicto de datos. No se guardaron filas.",
                )
            else:
                request.session.pop("csv_preview", None)
                messages.success(
                    request, f"Importación completada. Creados: {created}. Actualizados: {updated}."
                )
                return redirect("proposal-detail", pk=pk) if pk else redirect("tariffs")
    elif request.method == "POST" and form.is_valid() and request.POST.get("action") == "preview":
        file = form.cleaned_data["file"]
        try:
            preview = import_csv(request.user, file, pk, dry_run=True)
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            file.seek(0)
            token = secrets.token_urlsafe(32)
            request.session["csv_preview"] = {
                "token": token,
                "proposal_id": pk,
                "timestamp": timezone.now().timestamp(),
                "name": file.name,
                "content_type": file.content_type,
                "content": base64.b64encode(file.read()).decode("ascii"),
            }
            preview["token"] = token
            preview["filename"] = file.name
    elif request.method == "POST" and form.is_valid():
        try:
            created, updated = import_csv(request.user, form.cleaned_data["file"], pk)
        except (ValidationError, IntegrityError) as exc:
            form.add_error(
                None,
                exc
                if isinstance(exc, ValidationError)
                else "Conflicto de datos; no se guardó el archivo.",
            )
        else:
            messages.success(request, f"Creados: {created}. Actualizados: {updated}.")
            return redirect("proposal-detail", pk=pk) if pk else redirect("tariffs")
    return render(
        request,
        "imports/upload.html",
        {
            "title": "Importar CSV",
            "preview": preview,
            "proposal_id": pk,
            "headers": ITEM_HEADERS if pk else TARIFF_HEADERS,
            "form": form,
            "help": "UTF-8, coma, máximo 2 MiB y 1.000 filas. Se valida todo antes de guardar. Encabezados exactos: "
            + ",".join(ITEM_HEADERS if pk else TARIFF_HEADERS),
        },
    )


@login_required
def exchange_rate(request, pk):
    obj = proposal_object(request.user, pk)
    context = {"object": obj, "total": proposal_total(obj)}
    try:
        rate, stale = get_rate()
        context.update(rate=rate, stale=stale, usd=money(context["total"] / rate.cop_per_usd))
    except ExchangeRateUnavailable as exc:
        context["error"] = str(exc)
    return render(request, "exchange.html", context)


@login_required
def exchange_overview(request):
    context = {}
    try:
        rate, stale = get_rate()
        context.update(rate=rate, stale=stale)
    except ExchangeRateUnavailable as exc:
        context["error"] = str(exc)
    return render(request, "exchange_overview.html", context)
