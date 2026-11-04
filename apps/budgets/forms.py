from django import forms

from apps.budgets.models import BudgetItem, Sprint, TariffProfile
from apps.common.forms import model_form

SprintForm = forms.modelform_factory(
    Sprint,
    fields=["number", "goal", "deliverables", "start_date", "end_date"],
    widgets={
        field: forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
        for field in ["start_date", "end_date"]
    },
)


TariffForm = model_form(TariffProfile, ["profile", "level", "hourly_rate_cop", "is_active"])


ItemForm = model_form(
    BudgetItem, ["user_story", "tariff_profile", "estimated_hours", "infrastructure_cost_cop"]
)


class UploadForm(forms.Form):
    file = forms.FileField(label="Archivo CSV")
