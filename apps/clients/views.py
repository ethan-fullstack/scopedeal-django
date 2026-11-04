from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.clients.forms import (
    ClientForm,
    DeveloperRequestForm,
    RequestForm,
)
from apps.clients.models import Client, SoftwareRequest
from apps.common.authorization import developer, scoped
from apps.common.views import form_page, paginate, request_object
from apps.proposals.selectors import proposals_for


@login_required
def clients(request):
    developer(request.user)
    objects = Client.objects.filter(name__icontains=request.GET.get("q", ""))
    return render(
        request,
        "list.html",
        {
            "title": "Organizaciones",
            "objects": paginate(request, objects)["page_obj"],
            **paginate(request, objects),
            "kind": "client",
            "new_url": "/clients/new/",
        },
    )


@login_required
def client_edit(request, pk=None):
    developer(request.user)
    instance = get_object_or_404(Client, pk=pk) if pk else None
    form = ClientForm(request.POST if request.method == "POST" else None, instance=instance)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("clients")
    return form_page(request, form, "Organización")


@login_required
def client_me(request):
    return render(
        request,
        "client.html",
        {
            "client": get_object_or_404(Client, pk=request.user.client_id),
            "client_requests": SoftwareRequest.objects.filter(
                client_id=request.user.client_id
            ).order_by("-created_at")[:10],
        },
    )


@login_required
def requests_list(request):
    objects = scoped(SoftwareRequest.objects.select_related("client"), request.user).filter(
        title__icontains=request.GET.get("q", "")
    )
    return render(
        request,
        "list.html",
        {
            "title": "Solicitudes",
            "objects": paginate(request, objects)["page_obj"],
            **paginate(request, objects),
            "kind": "request",
            "new_url": "/requests/new/",
        },
    )


@login_required
def request_edit(request, pk=None):
    instance = request_object(request.user, pk) if pk else None
    if instance and (instance.status != "NEW" or instance.proposals.exists()):
        raise PermissionDenied
    form_class = (
        DeveloperRequestForm if request.user.role == "DEVELOPER" and not pk else RequestForm
    )
    form = form_class(request.POST if request.method == "POST" else None, instance=instance)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            if instance:
                locked = SoftwareRequest.objects.select_for_update().get(pk=pk)
                if locked.status != "NEW" or locked.proposals.exists():
                    raise PermissionDenied
            obj = form.save(commit=False)
            if not pk:
                obj.created_by = request.user
                if request.user.role == "CLIENT":
                    obj.client_id = request.user.client_id
            obj.full_clean()
            obj.save()
        return redirect("request-detail", pk=obj.pk)
    return form_page(request, form, "Solicitud")


@login_required
def request_detail(request, pk):
    obj = request_object(request.user, pk)
    return render(
        request,
        "request.html",
        {"object": obj, "proposals": proposals_for(request.user).filter(software_request=obj)},
    )


@login_required
@require_POST
def request_action(request, pk, action):
    obj = request_object(request.user, pk)
    if request.POST.get("review") == "yes" and action in ["close", "delete"]:
        if action == "close":
            developer(request.user)
        elif obj.status != "NEW" or obj.proposals.exists():
            raise PermissionDenied
        return render(
            request,
            "actions/confirmation.html",
            {
                "subject": obj.title,
                "explanation": "La solicitud se cerrará y no admitirá nuevas propuestas."
                if action == "close"
                else "Se eliminará esta solicitud sin propuestas. Esta acción es irreversible.",
                "cancel_url": f"/requests/{pk}/",
            },
        )
    with transaction.atomic():
        obj = SoftwareRequest.objects.select_for_update().get(pk=obj.pk)
        if action == "delete":
            if obj.status != "NEW" or obj.proposals.exists():
                raise PermissionDenied
            obj.delete()
            return redirect("requests")
        developer(request.user)
        target = {"review": "IN_REVIEW", "close": "CLOSED"}.get(action)
        if not target or obj.status == "CLOSED" or (target == "IN_REVIEW" and obj.status != "NEW"):
            raise PermissionDenied
        obj.status = target
        obj.save()
    return redirect("request-detail", pk=pk)


@login_required
def client_detail(request, pk):
    developer(request.user)
    client = get_object_or_404(Client, pk=pk)
    return render(
        request,
        "client.html",
        {
            "client": client,
            "client_requests": SoftwareRequest.objects.filter(client=client).order_by(
                "-created_at"
            )[:10],
        },
    )
