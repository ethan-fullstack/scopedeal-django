from pathlib import Path

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.budgets.importers import import_csv
from apps.budgets.models import BudgetItem, Sprint, TariffProfile
from apps.proposals.services import transition

pytestmark = pytest.mark.django_db
ROOT = Path(__file__).resolve().parents[1]


def upload(content, name="data.csv"):
    return SimpleUploadedFile(name, content)


def sample(name):
    return upload((ROOT / "sample-data" / name).read_bytes())


def test_tariff_idempotent_snapshot_and_invalid_rollback(world):
    assert import_csv(world["dev"], sample("catalogo_perfiles_y_tarifas.csv")) == (7, 1)
    assert import_csv(world["dev"], sample("catalogo_perfiles_y_tarifas.csv")) == (0, 8)
    world["item"].refresh_from_db()
    assert world["item"].hourly_rate_cop == 10000
    count = TariffProfile.objects.count()
    with pytest.raises(ValidationError):
        import_csv(world["dev"], sample("catalogo_perfiles_y_tarifas_invalid.csv"))
    assert TariffProfile.objects.count() == count


def test_items_idempotent_and_line_errors(world):
    body = b"sprint_number,user_story,profile,level,estimated_hours,infrastructure_cost_cop\n1,HU-01,Backend,JR,12.00,25000.00\n"
    assert import_csv(world["dev"], upload(body), world["proposal"].pk) == (0, 1)
    assert import_csv(world["dev"], upload(body), world["proposal"].pk) == (0, 1)
    import_csv(world["dev"], sample("catalogo_perfiles_y_tarifas.csv"))
    for number in range(2, 5):
        Sprint.objects.create(
            proposal=world["proposal"],
            number=number,
            goal="Delivery",
            deliverables="Features",
            start_date="2026-01-01",
            end_date="2026-01-14",
        )
    before = list(BudgetItem.objects.values())
    with pytest.raises(ValidationError) as exc:
        import_csv(
            world["dev"], sample("items_estimacion_sprint_invalid.csv"), world["proposal"].pk
        )
    assert "Línea 4, profile" in str(exc.value)
    assert "Línea 5, estimated_hours" in str(exc.value)
    assert before == list(BudgetItem.objects.values())


@pytest.mark.parametrize(
    "body,name",
    [
        (b"wrong,header\n1,2\n", "a.csv"),
        (b"\xff", "a.csv"),
        (b"a" * (2 * 1024 * 1024 + 1), "a.csv"),
        (b"profile,level,hourly_rate_cop\n" + b"Backend,JR,1\n" * 1001, "a.csv"),
        (b"profile,level,hourly_rate_cop\nBackend,JR,1\nBackend,JR,2\n", "a.csv"),
        (b"profile,level,hourly_rate_cop\nBackend,XX,1\n", "a.csv"),
        (b"profile,level,hourly_rate_cop\nBackend,JR,0.001\n", "a.csv"),
        (b"profile,level,hourly_rate_cop\nBackend,JR,99999999999\n", "a.csv"),
        (b"profile,level,hourly_rate_cop\nBackend,JR,NaN\n", "a.csv"),
        (b"", "a.txt"),
    ],
)
def test_invalid_csv_zero_changes(world, body, name):
    before = list(TariffProfile.objects.values())
    with pytest.raises(ValidationError):
        import_csv(world["dev"], upload(body, name))
    assert list(TariffProfile.objects.values()) == before


def test_bom_valid_and_authorization(world):
    assert import_csv(
        world["dev"], upload(b"\xef\xbb\xbfprofile,level,hourly_rate_cop\nQA,MID,12.00\n")
    ) == (1, 0)
    with pytest.raises(PermissionDenied):
        import_csv(world["client"], sample("catalogo_perfiles_y_tarifas.csv"))
    transition(world["dev"], world["proposal"].pk, "submit")
    with pytest.raises(ValidationError):
        import_csv(world["dev"], sample("items_estimacion_sprint.csv"), world["proposal"].pk)
