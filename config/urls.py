from django.contrib import admin
from django.contrib.auth import views as auth
from django.urls import path

from apps.accounts import views as a
from apps.budgets import views as b
from apps.clients import views as c
from apps.common import views as v
from apps.proposals import views as p
from apps.reports import views as r

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", v.home, name="home"),
    path("health/", v.health),
    path("accounts/register/", a.register, name="register"),
    path(
        "accounts/login/",
        auth.LoginView.as_view(template_name="registration/login.html"),
        name="login",
    ),
    path("accounts/logout/", auth.LogoutView.as_view(), name="logout"),
    path("accounts/password_reset/", auth.PasswordResetView.as_view(), name="password_reset"),
    path(
        "accounts/password_reset/done/",
        auth.PasswordResetDoneView.as_view(),
        name="password_reset_done",
    ),
    path(
        "accounts/reset/<uidb64>/<token>/",
        auth.PasswordResetConfirmView.as_view(),
        name="password_reset_confirm",
    ),
    path(
        "accounts/reset/done/",
        auth.PasswordResetCompleteView.as_view(),
        name="password_reset_complete",
    ),
    path("dashboard/", r.dashboard, name="dashboard"),
    path("clients/", c.clients, name="clients"),
    path("clients/new/", c.client_edit),
    path("clients/me/", c.client_me),
    path("clients/<int:pk>/edit/", c.client_edit),
    path("clients/<int:pk>/", c.client_detail, name="client-detail"),
    path("requests/", c.requests_list, name="requests"),
    path("requests/new/", c.request_edit),
    path("requests/<int:pk>/", c.request_detail, name="request-detail"),
    path("requests/<int:pk>/edit/", c.request_edit),
    path("requests/<int:pk>/actions/<str:action>/", c.request_action),
    path("requests/<int:pk>/proposals/new/", p.proposal_new),
    path("proposals/", r.reports, name="proposals"),
    path("proposals/<int:pk>/", p.proposal_detail, name="proposal-detail"),
    path("proposals/<int:pk>/edit/", p.proposal_edit, name="proposal-edit"),
    path("proposals/<int:pk>/notes/new/", p.note_new),
    path("proposals/<int:pk>/negotiate/", p.note_new, {"negotiate": True}),
    path("proposals/<int:pk>/sprints/", p.proposal_detail),
    path(
        "proposals/<int:pk>/budget/",
        p.proposal_detail,
        {"budget_only": True},
        name="proposal-budget",
    ),
    path("proposals/<int:parent>/sprints/new/", b.budget_edit, {"kind": "sprint"}),
    path("sprints/<int:pk>/edit/", b.budget_edit, {"kind": "sprint"}),
    path("sprints/<int:pk>/delete/", b.budget_delete, {"kind": "sprint"}),
    path("sprints/<int:parent>/items/new/", b.budget_edit, {"kind": "item"}),
    path("budget-items/<int:pk>/edit/", b.budget_edit, {"kind": "item"}),
    path("budget-items/<int:pk>/delete/", b.budget_delete, {"kind": "item"}),
    path("exchange-rate/", b.exchange_overview, name="exchange-overview"),
    path("tariffs/", b.tariffs, name="tariffs"),
    path("tariffs/new/", b.budget_edit, {"kind": "tariff"}),
    path("tariffs/<int:pk>/edit/", b.budget_edit, {"kind": "tariff"}),
    path("imports/tariffs/", b.upload),
    path("proposals/<int:pk>/imports/budget-items/", b.upload),
    path("proposals/<int:pk>/exchange-rate/", b.exchange_rate),
    path("reports/proposals/", r.reports),
    path("reports/budgets/", r.reports),
    path("proposals/<int:pk>/<str:action>/", p.proposal_action),
]
