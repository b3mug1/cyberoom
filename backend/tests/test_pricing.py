from datetime import datetime, time, timedelta, timezone
from decimal import Decimal

import pytest

from app.models import Tariff
from app.services.errors import ServiceError
from app.services.pricing import calculate_interval_price, calculate_price


@pytest.fixture
def standard_tariffs() -> list[Tariff]:
    return [
        Tariff(name="Night", price_per_hour=Decimal("700"), start_time=time(0), end_time=time(6), is_active=True),
        Tariff(name="Standard", price_per_hour=Decimal("800"), start_time=time(6), end_time=time(18), is_active=True),
        Tariff(name="Prime", price_per_hour=Decimal("1200"), start_time=time(18), end_time=time(0), is_active=True),
    ]


def test_calculates_standard_price(standard_tariffs: list[Tariff]) -> None:
    start = datetime(2026, 9, 28, 12, tzinfo=timezone.utc)
    assert calculate_price(start, datetime(2026, 9, 28, 14, tzinfo=timezone.utc), standard_tariffs, "UTC") == Decimal("1600.00")


def test_calculates_across_tariff_boundary(standard_tariffs: list[Tariff]) -> None:
    start = datetime(2026, 9, 28, 17, 30, tzinfo=timezone.utc)
    assert calculate_price(start, datetime(2026, 9, 28, 18, 30, tzinfo=timezone.utc), standard_tariffs, "UTC") == Decimal("1000.00")


def test_calculates_across_midnight(standard_tariffs: list[Tariff]) -> None:
    start = datetime(2026, 9, 28, 23, tzinfo=timezone.utc)
    assert calculate_price(start, datetime(2026, 9, 29, 1, tzinfo=timezone.utc), standard_tariffs, "UTC") == Decimal("1900.00")


def test_rejects_missing_tariff_coverage() -> None:
    tariff = Tariff(name="Day", price_per_hour=Decimal("800"), start_time=time(8), end_time=time(18), is_active=True)
    start = datetime(2026, 9, 28, 7, tzinfo=timezone.utc)
    with pytest.raises(ServiceError, match="No unambiguous active tariff"):
        calculate_price(start, datetime(2026, 9, 28, 8, tzinfo=timezone.utc), [tariff], "UTC")


def test_rejects_duration_outside_limits(standard_tariffs: list[Tariff]) -> None:
    start = datetime(2026, 9, 28, 12, tzinfo=timezone.utc)
    with pytest.raises(ServiceError, match="between 15 minutes and 8 hours"):
        calculate_price(start, start + timedelta(minutes=10), standard_tariffs, "UTC")


def test_price_uses_club_timezone_not_supplied_offset(standard_tariffs: list[Tariff]) -> None:
    start_utc = datetime(2026, 9, 28, 13, tzinfo=timezone.utc)
    end_utc = start_utc + timedelta(hours=1)
    first = calculate_price(start_utc, end_utc, standard_tariffs, "Asia/Almaty")
    client_offset = timezone(timedelta(hours=-4))
    second = calculate_price(start_utc.astimezone(client_offset), end_utc.astimezone(client_offset), standard_tariffs, "Asia/Almaty")
    assert first == second == Decimal("1200.00")


def test_short_extension_has_price_without_booking_minimum(standard_tariffs: list[Tariff]) -> None:
    start = datetime(2026, 9, 28, 12, tzinfo=timezone.utc)
    assert calculate_interval_price(start, start + timedelta(minutes=5), standard_tariffs, "UTC") == Decimal("66.67")


def test_dst_transition_bills_elapsed_minutes(standard_tariffs: list[Tariff]) -> None:
    # New York skips 02:00–02:59 on this date; 60 elapsed minutes span 01:30–03:30 locally.
    start = datetime(2026, 3, 8, 6, 30, tzinfo=timezone.utc)
    end = start + timedelta(hours=1)
    assert calculate_price(start, end, standard_tariffs, "America/New_York") == Decimal("700.00")
