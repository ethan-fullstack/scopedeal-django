from decimal import ROUND_HALF_UP, Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.db.models.functions import Lower


class Sprint(models.Model):
    proposal = models.ForeignKey(
        "proposals.Proposal", on_delete=models.CASCADE, related_name="sprints"
    )
    number = models.PositiveIntegerField(validators=[MinValueValidator(1)], verbose_name="Número")
    goal = models.CharField(max_length=240, verbose_name="Objetivo")
    deliverables = models.TextField(verbose_name="Entregables")
    start_date = models.DateField(verbose_name="Fecha inicial")
    end_date = models.DateField(verbose_name="Fecha final")

    class Meta:
        ordering = ["number"]
        constraints = [
            models.UniqueConstraint(fields=["proposal", "number"], name="unique_sprint"),
            models.CheckConstraint(condition=models.Q(number__gte=1), name="positive_sprint"),
            models.CheckConstraint(
                condition=models.Q(start_date__lte=models.F("end_date")), name="sprint_dates"
            ),
        ]

    def __str__(self):
        return f"Sprint {self.number}"


class TariffProfile(models.Model):
    profile = models.CharField(max_length=80, verbose_name="Perfil")
    level = models.CharField(
        max_length=3, choices=[("JR", "JR"), ("MID", "MID"), ("SR", "SR")], verbose_name="Nivel"
    )
    hourly_rate_cop = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        verbose_name="Tarifa COP/hora",
    )
    is_active = models.BooleanField(default=True, verbose_name="Activo")

    class Meta:
        constraints = [
            models.UniqueConstraint(Lower("profile"), "level", name="unique_tariff_ci"),
            models.CheckConstraint(
                condition=models.Q(hourly_rate_cop__gte=0), name="tariff_nonnegative"
            ),
        ]

    def __str__(self):
        return f"{self.profile} {self.level}"


class BudgetItem(models.Model):
    sprint = models.ForeignKey(Sprint, on_delete=models.CASCADE, related_name="items")
    tariff_profile = models.ForeignKey(
        TariffProfile, on_delete=models.PROTECT, verbose_name="Perfil tarifario"
    )
    profile_name = models.CharField(max_length=80)
    profile_level = models.CharField(max_length=3)
    user_story = models.CharField(max_length=60, verbose_name="Historia de usuario")
    estimated_hours = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        verbose_name="Horas estimadas",
    )
    hourly_rate_cop = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(0)]
    )
    infrastructure_cost_cop = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        verbose_name="Infraestructura COP",
    )

    @property
    def subtotal(self):
        return (
            self.estimated_hours * self.hourly_rate_cop + self.infrastructure_cost_cop
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["sprint", "user_story", "tariff_profile"], name="unique_item"
            ),
            models.CheckConstraint(
                condition=models.Q(estimated_hours__gt=0), name="hours_positive"
            ),
            models.CheckConstraint(
                condition=models.Q(hourly_rate_cop__gte=0, infrastructure_cost_cop__gte=0),
                name="item_cost_nonnegative",
            ),
        ]


class ExchangeRateSnapshot(models.Model):
    provider = models.CharField(max_length=100, default="ExchangeRate-API")
    base_currency = models.CharField(max_length=3, default="USD")
    quote_currency = models.CharField(max_length=3, default="COP")
    cop_per_usd = models.DecimalField(
        max_digits=18, decimal_places=6, validators=[MinValueValidator(Decimal("0.000001"))]
    )
    effective_at = models.DateTimeField()
    retrieved_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(cop_per_usd__gt=0), name="fx_positive")
        ]
