from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import User
from apps.budgets.models import Sprint
from apps.clients.models import Client, SoftwareRequest
from apps.proposals.services import new_version


class Command(BaseCommand):
    help = "Create synthetic requests and four draft sprints; no credentials are created."

    @transaction.atomic
    def handle(self, *args, **options):
        developer = User.objects.filter(role="DEVELOPER", is_active=True).first()
        if not developer:
            self.stderr.write("Create an authorized account using createsuperuser first.")
            return
        client, _ = Client.objects.get_or_create(
            name="Organización Horizonte",
            defaults={"industry": "Servicios", "contact_email": "contact@example.invalid"},
        )
        request, _ = SoftwareRequest.objects.get_or_create(
            client=client,
            title="Portal de operaciones",
            defaults={
                "description": "Gestión de tareas y seguimiento de entregables.",
                "created_by": developer,
            },
        )
        proposal = request.proposals.first()
        if not proposal:
            proposal = new_version(developer, request.pk)
        if proposal.status == "DRAFT":
            proposal.technical_scope = "Portal de gestión con roles y reportes."
            proposal.technologies = "Python, Django, PostgreSQL"
            proposal.exclusions = "Pagos y firma electrónica."
            proposal.service_conditions = "Entregas por sprint y revisión conjunta."
            proposal.save()
            for number in range(1, 5):
                Sprint.objects.get_or_create(
                    proposal=proposal,
                    number=number,
                    defaults={
                        "goal": f"Entrega {number}",
                        "deliverables": "Funcionalidad validada",
                        "start_date": date.today() + timedelta(days=(number - 1) * 14),
                        "end_date": date.today() + timedelta(days=number * 14 - 1),
                    },
                )
        self.stdout.write(
            "Synthetic organization, request and four sprints ready. Import sample CSVs through the UI."
        )
