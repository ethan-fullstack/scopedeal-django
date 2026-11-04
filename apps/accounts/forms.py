from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.db import transaction

from apps.accounts.models import User
from apps.clients.models import Client


class RegistrationForm(UserCreationForm):
    organization_name = forms.CharField(max_length=160, label="Organización")
    industry = forms.CharField(max_length=100, label="Sector")
    email = forms.EmailField(label="Correo electrónico")

    class Meta:
        model = User
        fields = ["username", "email", "organization_name", "industry", "password1", "password2"]

    def clean_email(self):
        email = self.cleaned_data["email"].strip()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("El correo ya está registrado.")
        return email

    @transaction.atomic
    def save(self, commit=True):
        organization = Client.objects.create(
            name=self.cleaned_data["organization_name"],
            industry=self.cleaned_data["industry"],
            contact_email=self.cleaned_data["email"],
        )
        user = super().save(commit=False)
        user.role = "CLIENT"
        user.client = organization
        user.save()
        return user

    def _post_clean(self):
        # The organization is assigned atomically after password validation.
        self.instance.role = "DEVELOPER"
        super()._post_clean()
