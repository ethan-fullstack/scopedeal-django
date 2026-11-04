from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class Proposal(models.Model):
    STATES = [
        ("DRAFT", "Borrador"),
        ("SUBMITTED", "Enviada"),
        ("NEGOTIATING", "En negociación"),
        ("ACCEPTED", "Aceptada"),
        ("REJECTED", "Rechazada"),
        ("SUPERSEDED", "Sustituida"),
    ]
    software_request = models.ForeignKey(
        "clients.SoftwareRequest", on_delete=models.PROTECT, related_name="proposals"
    )
    version = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    status = models.CharField(max_length=12, choices=STATES, default="DRAFT")
    technical_scope = models.TextField(blank=True, verbose_name="Alcance técnico")
    technologies = models.TextField(blank=True, verbose_name="Tecnologías")
    exclusions = models.TextField(blank=True, verbose_name="Exclusiones")
    service_conditions = models.TextField(blank=True, verbose_name="Condiciones de servicio")
    sla_response_hours = models.PositiveIntegerField(
        default=24, verbose_name="Respuesta SLA (horas)"
    )
    warranty_days = models.PositiveIntegerField(default=30, verbose_name="Garantía (días)")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="proposals_created"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    accepted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="proposals_accepted",
    )
    accepted_at = models.DateTimeField(null=True, blank=True)
    accepted_total_cop = models.DecimalField(max_digits=24, decimal_places=2, null=True, blank=True)
    accepted_exchange_rate = models.DecimalField(
        max_digits=18, decimal_places=6, null=True, blank=True
    )
    accepted_exchange_rate_at = models.DateTimeField(null=True, blank=True)
    accepted_total_usd = models.DecimalField(max_digits=24, decimal_places=2, null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["software_request", "version"], name="unique_version"),
            models.UniqueConstraint(
                fields=["software_request"],
                condition=models.Q(status="ACCEPTED"),
                name="one_accepted",
            ),
            models.CheckConstraint(condition=models.Q(version__gte=1), name="positive_version"),
        ]
        indexes = [models.Index(fields=["status", "created_at"])]

    def __str__(self):
        return f"{self.software_request} · v{self.version}"


class NegotiationNote(models.Model):
    proposal = models.ForeignKey(Proposal, on_delete=models.PROTECT, related_name="notes")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    type = models.CharField(
        max_length=12,
        choices=[("COMMENT", "Comentario"), ("COUNTEROFFER", "Contrapropuesta")],
        verbose_name="Tipo",
    )
    message = models.TextField(verbose_name="Mensaje")
    proposed_amount_cop = models.DecimalField(
        max_digits=24,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        verbose_name="Monto alternativo COP",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(proposed_amount_cop__gte=0)
                | models.Q(proposed_amount_cop__isnull=True),
                name="note_amount_nonnegative",
            )
        ]
