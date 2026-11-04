from django.conf import settings
from django.db import models


class Client(models.Model):
    name = models.CharField(max_length=160, verbose_name="Nombre")
    industry = models.CharField(max_length=100, verbose_name="Sector")
    contact_email = models.EmailField(verbose_name="Correo de contacto")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class SoftwareRequest(models.Model):
    client = models.ForeignKey(Client, on_delete=models.PROTECT)
    title = models.CharField(max_length=180, verbose_name="Título")
    description = models.TextField(verbose_name="Descripción")
    priority = models.CharField(
        max_length=10,
        choices=[("LOW", "Baja"), ("MEDIUM", "Media"), ("HIGH", "Alta")],
        default="MEDIUM",
        verbose_name="Prioridad",
    )
    status = models.CharField(
        max_length=12,
        choices=[("NEW", "Nueva"), ("IN_REVIEW", "En revisión"), ("CLOSED", "Cerrada")],
        default="NEW",
    )
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title
