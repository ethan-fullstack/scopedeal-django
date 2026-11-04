from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import httpx
import pytest
from django.utils import timezone

from apps.budgets.models import ExchangeRateSnapshot
from integrations.exchange_rates import ExchangeRateUnavailable, get_rate

pytestmark = pytest.mark.django_db


def response(data, status=200):
    return httpx.Response(
        status, json=data, request=httpx.Request("GET", "https://open.er-api.com/v6/latest/USD")
    )


def valid():
    return {
        "result": "success",
        "base_code": "USD",
        "conversion_rates": {"COP": 4000},
        "time_last_update_unix": int(timezone.now().timestamp()),
    }


def test_fx_success_and_cache():
    with patch("integrations.exchange_rates.httpx.get", return_value=response(valid())) as get:
        rate, stale = get_rate()
        assert rate.cop_per_usd == Decimal(4000) and not stale
        assert get.call_args.kwargs["timeout"] == 5
        assert get_rate()[0].pk == rate.pk
        assert get.call_count == 1


@pytest.mark.parametrize(
    "failure",
    ["timeout", "server", "json", "missing", "zero", "negative", "schema", "base", "timestamp"],
)
def test_fx_failures(failure):
    data = valid()
    if failure == "missing":
        data["conversion_rates"] = {}
    if failure == "zero":
        data["conversion_rates"]["COP"] = 0
    if failure == "negative":
        data["conversion_rates"]["COP"] = -1
    if failure == "schema":
        data["result"] = "error"
    if failure == "base":
        data["base_code"] = "EUR"
    if failure == "timestamp":
        data["time_last_update_unix"] = "invalid"
    result = response(data, 503 if failure == "server" else 200)
    if failure == "json":
        result = httpx.Response(
            200, text="not json", request=httpx.Request("GET", "https://open.er-api.com")
        )
    with patch(
        "integrations.exchange_rates.httpx.get",
        side_effect=httpx.TimeoutException("timeout") if failure == "timeout" else None,
        return_value=result,
    ):
        with pytest.raises(ExchangeRateUnavailable):
            get_rate()
    assert ExchangeRateSnapshot.objects.count() == 0


def test_stale_fallback_and_expiration():
    rate = ExchangeRateSnapshot.objects.create(
        cop_per_usd=4000, effective_at=timezone.now() - timedelta(days=2)
    )
    ExchangeRateSnapshot.objects.filter(pk=rate.pk).update(
        retrieved_at=timezone.now() - timedelta(days=2)
    )
    with patch(
        "integrations.exchange_rates.httpx.get", side_effect=httpx.TimeoutException("timeout")
    ):
        assert get_rate()[1] is True
        ExchangeRateSnapshot.objects.filter(pk=rate.pk).update(
            effective_at=timezone.now() - timedelta(days=8)
        )
        with pytest.raises(ExchangeRateUnavailable):
            get_rate()


def test_observed_open_access_rates_schema():
    data = valid()
    data["rates"] = data.pop("conversion_rates")
    with patch("integrations.exchange_rates.httpx.get", return_value=response(data)):
        rate, stale = get_rate()
    assert rate.cop_per_usd == 4000 and not stale
