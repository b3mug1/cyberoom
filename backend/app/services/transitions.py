from app.models import Booking, BookingStatus
from app.services.errors import ServiceError

ALLOWED_TRANSITIONS = {
    BookingStatus.PENDING: {BookingStatus.CONFIRMED, BookingStatus.CANCELLED, BookingStatus.EXPIRED},
    BookingStatus.CONFIRMED: {BookingStatus.ACTIVE, BookingStatus.CANCELLED, BookingStatus.EXPIRED},
    BookingStatus.ACTIVE: {BookingStatus.COMPLETED},
    BookingStatus.COMPLETED: set(),
    BookingStatus.CANCELLED: set(),
    BookingStatus.EXPIRED: set(),
}


def transition_booking(booking: Booking, target: BookingStatus) -> None:
    if target not in ALLOWED_TRANSITIONS[booking.status]:
        raise ServiceError("INVALID_BOOKING_TRANSITION", f"Cannot transition booking from {booking.status.value} to {target.value}.", 409)
    booking.status = target