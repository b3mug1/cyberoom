from datetime import datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from app.models import Tariff
from app.services.errors import ServiceError


def _duration_minutes(start: datetime, end: datetime) -> tuple[datetime, int]:
    if start.tzinfo is None or end.tzinfo is None:
        raise ServiceError("INVALID_BOOKING_TIME", "A valid timezone-aware booking interval is required.")
    start_utc = start.astimezone(timezone.utc)
    duration_seconds = (end.astimezone(timezone.utc) - start_utc).total_seconds()
    if duration_seconds <= 0 or duration_seconds % 60:
        raise ServiceError("INVALID_BOOKING_TIME", "Booking times must form a positive whole-minute interval.")
    return start_utc, int(duration_seconds // 60)


def calculate_price(start: datetime, end: datetime, tariffs: list[Tariff], club_timezone: str) -> Decimal:
    _, duration_minutes = _duration_minutes(start, end)
    if duration_minutes < 15 or duration_minutes > 8 * 60:
        raise ServiceError("INVALID_BOOKING_DURATION", "Bookings must be between 15 minutes and 8 hours.")
    return calculate_interval_price(start, end, tariffs, club_timezone)


def calculate_interval_price(start: datetime, end: datetime, tariffs: list[Tariff], club_timezone: str) -> Decimal:
    start_utc, duration_minutes = _duration_minutes(start, end)
    zone = ZoneInfo(club_timezone)

    total = Decimal("0")
    for minute in range(duration_minutes):
        local_datetime = (start_utc + timedelta(minutes=minute)).astimezone(zone)
        local_time = local_datetime.time()
        matching = [
            tariff for tariff in tariffs
            if tariff.is_active
            and _contains(tariff.start_time, tariff.end_time, local_time)
            and _applies_on_day(tariff, local_datetime)
        ]
        if len(matching) != 1:
            raise ServiceError("TARIFF_UNAVAILABLE", "No unambiguous active tariff covers the selected time.", 422)
        total += matching[0].price_per_hour / Decimal(60)

    return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def apply_discount(subtotal: Decimal, discount_type: str | None, discount_value: Decimal | None) -> tuple[Decimal, Decimal]:
    if discount_type is None or discount_value is None:
        return subtotal, Decimal("0.00")
    if discount_type == "PERCENT":
        discount = (subtotal * discount_value / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    else:
        discount = min(subtotal, discount_value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return (subtotal - discount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), discount


def _contains(start: time, end: time, value: time) -> bool:
    if start <= end:
        return start <= value < end
    return value >= start or value < end


def _applies_on_day(tariff: Tariff, local_datetime: datetime) -> bool:
    days = tariff.days_of_week or list(range(7))
    service_day = local_datetime.date()
    if tariff.start_time > tariff.end_time and local_datetime.time() < tariff.end_time:
        service_day -= timedelta(days=1)
    return service_day.weekday() in days
