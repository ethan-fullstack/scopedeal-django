import csv
import io
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.budgets.models import BudgetItem, Sprint, TariffProfile
from apps.common.authorization import developer
from apps.proposals.models import Proposal
from apps.proposals.services import draft

TARIFF_HEADERS = ["profile", "level", "hourly_rate_cop"]
ITEM_HEADERS = [
    "sprint_number",
    "user_story",
    "profile",
    "level",
    "estimated_hours",
    "infrastructure_cost_cop",
]


class ImportValidationError(ValidationError):
    pass


def read_rows(upload, headers):
    if upload.content_type not in (
        "text/csv",
        "application/csv",
        "text/plain",
        "application/octet-stream",
        "application/vnd.ms-excel",
    ):
        raise ImportValidationError("Archivo: tipo de contenido CSV requerido.")
    if not upload.name.lower().endswith(".csv"):
        raise ImportValidationError("Archivo: se requiere extensión .csv.")
    if upload.size > 2 * 1024 * 1024:
        raise ImportValidationError("Archivo: máximo 2 MiB.")
    try:
        content = upload.read().decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ImportValidationError("Archivo: codificación UTF-8 requerida.") from exc
    try:
        reader = csv.DictReader(io.StringIO(content), strict=True)
        if reader.fieldnames != headers:
            raise ImportValidationError("Encabezados: " + ",".join(headers))
        rows = list(reader)
    except csv.Error as exc:
        raise ImportValidationError("Archivo CSV inválido.") from exc
    if len(rows) > 1000 or not rows:
        raise ImportValidationError("Archivo: entre 1 y 1.000 filas.")
    return rows


def decimal_value(value, digits, positive=False):
    try:
        number = Decimal(value)
    except (InvalidOperation, TypeError) as exc:
        raise ValueError("número inválido") from exc
    if (
        not number.is_finite()
        or number < 0
        or (positive and number == 0)
        or number.as_tuple().exponent < -2
        or number >= Decimal(10) ** (digits - 2)
    ):
        raise ValueError("precisión o rango inválido")
    return number


@transaction.atomic
def import_csv(user, upload, proposal_id=None, *, dry_run=False):
    developer(user)
    proposal = None
    if proposal_id:
        proposal = Proposal.objects.select_for_update().get(pk=proposal_id)
        draft(proposal)
    rows = read_rows(upload, ITEM_HEADERS if proposal else TARIFF_HEADERS)
    errors, prepared, seen = [], [], set()
    for line, row in enumerate(rows, 2):
        field = "fila"
        try:
            if None in row or any(v is None or not v.strip() for v in row.values()):
                raise ValueError("campos vacíos o columnas extra")
            row = {k: v.strip() for k, v in row.items()}
            field = "profile"
            if len(row["profile"]) > 80:
                raise ValueError("máximo 80 caracteres")
            field = "level"
            if row["level"] not in ["JR", "MID", "SR"]:
                raise ValueError("código desconocido")
            if proposal:
                field = "sprint_number"
                sprint = Sprint.objects.filter(
                    proposal=proposal, number=int(row["sprint_number"])
                ).first()
                if not sprint:
                    raise ValueError("sprint desconocido")
                field = "profile"
                tariff = TariffProfile.objects.filter(
                    profile__iexact=row["profile"], level=row["level"], is_active=True
                ).first()
                if not tariff:
                    raise ValueError("perfil desconocido")
                field = "user_story"
                if len(row["user_story"]) > 60:
                    raise ValueError("máximo 60 caracteres")
                key = (sprint.pk, row["user_story"], tariff.pk)
                field = "estimated_hours"
                hours = decimal_value(row[field], 8, True)
                field = "infrastructure_cost_cop"
                cost = decimal_value(row[field], 14)
                prepared.append(
                    (
                        dict(sprint=sprint, user_story=row["user_story"], tariff_profile=tariff),
                        dict(
                            estimated_hours=hours,
                            infrastructure_cost_cop=cost,
                            hourly_rate_cop=tariff.hourly_rate_cop,
                            profile_name=tariff.profile,
                            profile_level=tariff.level,
                        ),
                    )
                )
            else:
                key = (row["profile"].lower(), row["level"])
                field = "hourly_rate_cop"
                rate = decimal_value(row[field], 12)
                prepared.append(
                    (
                        dict(profile__iexact=row["profile"], level=row["level"]),
                        dict(profile=row["profile"], hourly_rate_cop=rate, is_active=True),
                    )
                )
            field = "duplicado"
            if key in seen:
                raise ValueError("clave repetida")
            seen.add(key)
        except (ValueError, InvalidOperation) as exc:
            errors.append(f"Línea {line}, {field}: {exc}")
    if errors:
        raise ImportValidationError(errors)
    created = updated = 0
    model = BudgetItem if proposal else TariffProfile
    if dry_run:
        updated = sum(model.objects.filter(**lookup).exists() for lookup, _ in prepared)
        return {
            "rows": rows[:20],
            "headers": ITEM_HEADERS if proposal else TARIFF_HEADERS,
            "row_count": len(rows),
            "created": len(prepared) - updated,
            "updated": updated,
        }
    for lookup, values in prepared:
        _, was_created = model.objects.update_or_create(**lookup, defaults=values)
        created += int(was_created)
        updated += int(not was_created)
    return created, updated
