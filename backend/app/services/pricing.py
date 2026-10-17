from datetime import datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP

from app.models import Tariff
from app.services.errors import ServiceError


def calculate_price(start: datetime, end: datetime, tariffs: list[Tariff]) -> Decimal:
    if start.tzinfo is None or end.tzinfo is None or start >= end:
        raise ServiceError("INVALID_BOOKING_TIME", "A valid timezone-aware booking interval is required.")
    duration_minutes = int((end - start).total_seconds() // 60)
    if duration_minutes < 15 or duration_minutes > 8 * 60:
        raise ServiceError("INVALID_BOOKING_DURATION", "Bookings must be between 15 minutes and 8 hours.")

    total = Decimal("0")
    for minute in range(duration_minutes):
        current = start + timedelta(minutes=minute)
        local_time = current.timetz().replace(tzinfo=None)
        matching = [tariff for tariff in tariffs if tariff.is_active and _contains(tariff.start_time, tariff.end_time, local_time)]
        if len(matching) != 1:
            raise ServiceError("TARIFF_UNAVAILABLE", "No unambiguous active tariff covers the selected time.", 422)
        total += matching[0].price_per_hour / Decimal(60)

    return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _contains(start: time, end: time, value: time) -> bool:
    if start <= end:
        return start <= value < end
    return value >= start or value < end