from django import forms

from apps.clients.models import Client
from apps.proposals.models import Proposal


class ReportForm(forms.Form):
    q = forms.CharField(required=False, max_length=180, label="Buscar propuesta")
    client = forms.ModelChoiceField(queryset=Client.objects.all(), required=False, label="Cliente")
    status = forms.ChoiceField(
        choices=[("", "Todos")] + Proposal.STATES, required=False, label="Estado"
    )
    start = forms.DateField(
        required=False, label="Desde", widget=forms.DateInput(attrs={"type": "date"})
    )
    end = forms.DateField(
        required=False, label="Hasta", widget=forms.DateInput(attrs={"type": "date"})
    )
    sprint = forms.IntegerField(min_value=1, required=False, label="Sprint")
    history = forms.BooleanField(required=False, label="Incluir historial de versiones")

    def clean(self):
        data = super().clean()
        if data.get("start") and data.get("end") and data["start"] > data["end"]:
            raise forms.ValidationError("Rango de fechas inválido.")
        return data
