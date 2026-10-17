import pytest

from app.models import Booking, BookingStatus
from app.services.errors import ServiceError
from app.services.transitions import transition_booking


def test_confirmed_booking_can_start_and_complete() -> None:
    booking = Booking(status=BookingStatus.CONFIRMED)
    transition_booking(booking, BookingStatus.ACTIVE)
    transition_booking(booking, BookingStatus.COMPLETED)
    assert booking.status is BookingStatus.COMPLETED


@pytest.mark.parametrize("status", [BookingStatus.ACTIVE, BookingStatus.COMPLETED, BookingStatus.CANCELLED, BookingStatus.EXPIRED])
def test_only_pending_or_confirmed_booking_can_be_cancelled(status: BookingStatus) -> None:
    booking = Booking(status=status)
    with pytest.raises(ServiceError, match="Cannot transition booking"):
        transition_booking(booking, BookingStatus.CANCELLED)


def test_cancelled_booking_cannot_be_reactivated() -> None:
    booking = Booking(status=BookingStatus.CANCELLED)
    with pytest.raises(ServiceError):
        transition_booking(booking, BookingStatus.ACTIVE)