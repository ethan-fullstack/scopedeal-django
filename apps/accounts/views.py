from django.contrib.auth import login
from django.db import IntegrityError
from django.shortcuts import redirect, render

from apps.accounts.forms import RegistrationForm
from apps.accounts.services import registration_allowed


def register(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = RegistrationForm(request.POST if request.method == "POST" else None)
    if request.method == "POST":
        if not registration_allowed(request.META.get("REMOTE_ADDR", "unknown")):
            form.add_error(None, "Demasiados intentos. Espere cinco minutos.")
        elif form.is_valid():
            try:
                user = form.save()
            except IntegrityError:
                form.add_error(None, "Usuario o correo ya registrado.")
            else:
                login(request, user)
                return redirect("dashboard")
    return render(request, "form.html", {"form": form, "title": "Crear cuenta de cliente"})
