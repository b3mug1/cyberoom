from datetime import datetime, time, timezone
from decimal import Decimal

import pytest

from app.models import Tariff
from app.services.errors import ServiceError
from app.services.pricing import calculate_price


@pytest.fixture
def standard_tariffs() -> list[Tariff]:
    return [
        Tariff(name="Night", price_per_hour=Decimal("700"), start_time=time(0), end_time=time(6), is_active=True),
        Tariff(name="Standard", price_per_hour=Decimal("800"), start_time=time(6), end_time=time(18), is_active=True),
        Tariff(name="Prime", price_per_hour=Decimal("1200"), start_time=time(18), end_time=time(0), is_active=True),
    ]


def test_calculates_standard_price(standard_tariffs: list[Tariff]) -> None:
    start = datetime(2026, 9, 28, 12, tzinfo=timezone.utc)
    assert calculate_price(start, datetime(2026, 9, 28, 14, tzinfo=timezone.utc), standard_tariffs) == Decimal("1600.00")


def test_calculates_across_tariff_boundary(standard_tariffs: list[Tariff]) -> None:
    start = datetime(2026, 9, 28, 17, 30, tzinfo=timezone.utc)
    assert calculate_price(start, datetime(2026, 9, 28, 18, 30, tzinfo=timezone.utc), standard_tariffs) == Decimal("1000.00")


def test_calculates_across_midnight(standard_tariffs: list[Tariff]) -> None:
    start = datetime(2026, 9, 28, 23, tzinfo=timezone.utc)
    assert calculate_price(start, datetime(2026, 9, 29, 1, tzinfo=timezone.utc), standard_tariffs) == Decimal("1900.00")


def test_rejects_missing_tariff_coverage() -> None:
    tariff = Tariff(name="Day", price_per_hour=Decimal("800"), start_time=time(8), end_time=time(18), is_active=True)
    start = datetime(2026, 9, 28, 7, tzinfo=timezone.utc)
    with pytest.raises(ServiceError, match="No unambiguous active tariff"):
        calculate_price(start, datetime(2026, 9, 28, 8, tzinfo=timezone.utc), [tariff])


def test_rejects_duration_outside_limits(standard_tariffs: list[Tariff]) -> None:
    start = datetime(2026, 9, 28, 12, tzinfo=timezone.utc)
    with pytest.raises(ServiceError, match="between 15 minutes and 8 hours"):
        calculate_price(start, start + __import__("datetime").timedelta(minutes=10), standard_tariffs)