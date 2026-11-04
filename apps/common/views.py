from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import DatabaseError, connections
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render

from apps.clients.models import SoftwareRequest
from apps.common.authorization import scoped
from apps.proposals.selectors import proposals_for


def draft(proposal):
    if proposal.status != "DRAFT":
        raise PermissionDenied


def home(request):
    return render(request, "home.html")


def health(request):
    try:
        with connections["default"].cursor() as cursor:
            cursor.execute("SELECT 1")
    except DatabaseError:
        return JsonResponse({"status": "unavailable"}, status=503)
    return JsonResponse({"status": "ok"})


def proposal_object(user, pk):
    return get_object_or_404(proposals_for(user), pk=pk)


def request_object(user, pk):
    return get_object_or_404(scoped(SoftwareRequest.objects.all(), user), pk=pk)


def paginate(request, queryset):
    page = Paginator(queryset.order_by("-pk"), 20).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    return {"page_obj": page, "query_params": params.urlencode()}


def form_page(request, form, title):
    return render(request, "form.html", {"form": form, "title": title})
