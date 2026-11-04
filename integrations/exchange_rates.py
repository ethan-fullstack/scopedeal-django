from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation

import httpx
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.budgets.models import ExchangeRateSnapshot


class ExchangeRateUnavailable(Exception):
    pass


def current_snapshot(hours):
    cutoff = timezone.now() - timedelta(hours=hours)
    return (
        ExchangeRateSnapshot.objects.filter(
            retrieved_at__gte=cutoff,
            effective_at__gte=cutoff,
            effective_at__lte=timezone.now() + timedelta(minutes=5),
        )
        .order_by("-retrieved_at")
        .first()
    )


def get_rate():
    cached = current_snapshot(24)
    if cached:
        return cached, False
    try:
        response = httpx.get("https://open.er-api.com/v6/latest/USD", timeout=5)
        response.raise_for_status()
        data = response.json(parse_float=Decimal)
        if data.get("result") != "success" or data.get("base_code") != "USD":
            raise ValueError("schema")
        rate_map = data["conversion_rates"] if "conversion_rates" in data else data["rates"]
        rate = Decimal(str(rate_map["COP"]))
        effective = datetime.fromtimestamp(data["time_last_update_unix"], tz=UTC)
        if (
            not rate.is_finite()
            or rate <= 0
            or effective > timezone.now() + timedelta(minutes=5)
            or effective < timezone.now() - timedelta(hours=24)
        ):
            raise ValueError("rate")
        snapshot = ExchangeRateSnapshot(cop_per_usd=rate, effective_at=effective)
        snapshot.full_clean()
        snapshot.save()
        return snapshot, False
    except (
        httpx.HTTPError,
        ValueError,
        KeyError,
        TypeError,
        InvalidOperation,
        OverflowError,
        ValidationError,
    ) as exc:
        stale = current_snapshot(168)
        if stale:
            return stale, True
        raise ExchangeRateUnavailable(
            "Tasa no disponible. Puede continuar operando en COP."
        ) from exc
