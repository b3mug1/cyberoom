import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.db import SessionFactory, engine
from app.models import Booking, BookingStatus, Computer, ComputerStatus, Session
from app.services.audit import record_audit
from app.services.bookings import end_session, release_membership_credits, release_promo_quota
from app.services.notifications import cancel_booking_reminders, enqueue_notification
from app.services.payments import handle_booking_cancellation
from app.services.transitions import transition_booking

logger = logging.getLogger(__name__)
POLL_SECONDS = 15
BATCH_SIZE = 100


async def _booking_pairs(session, *conditions):
    rows = await session.execute(
        select(Booking.id, Booking.computer_id).where(*conditions).order_by(Booking.start_time).limit(BATCH_SIZE)
    )
    return list(rows)


async def run_session_automation_once() -> None:
    now = datetime.now(timezone.utc)
    async with SessionFactory() as session:
        due_to_end = await _booking_pairs(session, Booking.status == BookingStatus.ACTIVE, Booking.end_time <= now)
        for booking_id, computer_id in due_to_end:
            computer = await session.scalar(select(Computer).where(Computer.id == computer_id).with_for_update())
            booking = await session.scalar(select(Booking).where(Booking.id == booking_id).with_for_update())
            if computer is None or booking is None or booking.status != BookingStatus.ACTIVE or booking.end_time > now:
                await session.rollback()
                continue
            await end_session(session, booking, None, computer)

        expired = await _booking_pairs(
            session,
            Booking.status.in_((BookingStatus.PENDING, BookingStatus.CONFIRMED)),
            Booking.end_time <= now,
        )
        for booking_id, computer_id in expired:
            computer = await session.scalar(select(Computer).where(Computer.id == computer_id).with_for_update())
            booking = await session.scalar(select(Booking).where(Booking.id == booking_id).with_for_update())
            if computer is None or booking is None or booking.status not in (BookingStatus.PENDING, BookingStatus.CONFIRMED) or booking.end_time > now:
                await session.rollback()
                continue
            await release_promo_quota(session, booking)
            await release_membership_credits(session, booking)
            await handle_booking_cancellation(session, booking, refund_eligible=False)
            transition_booking(booking, BookingStatus.EXPIRED)
            await cancel_booking_reminders(session, booking.id)
            record_audit(session, actor_id=None, action="booking.auto_expired", entity_type="booking", entity_id=booking.id,
                         club_id=computer.club_id, details={"expired_at": now.isoformat()})
            if booking.user_id is not None:
                enqueue_notification(
                    session,
                    user_id=booking.user_id,
                    booking_id=booking.id,
                    kind="BOOKING_EXPIRED",
                    title="Booking expired",
                    message="The reserved session ended without being checked in.",
                    payload={"booking_id": str(booking.id), "club_id": str(computer.club_id)},
                )
            await session.commit()

        due_to_start = await _booking_pairs(
            session,
            Booking.status == BookingStatus.CONFIRMED,
            Booking.start_time <= now,
            Booking.end_time > now,
        )
        for booking_id, computer_id in due_to_start:
            computer = await session.scalar(select(Computer).where(Computer.id == computer_id).with_for_update())
            booking = await session.scalar(select(Booking).where(Booking.id == booking_id).with_for_update())
            if (
                computer is None
                or booking is None
                or booking.status != BookingStatus.CONFIRMED
                or booking.start_time > now
                or booking.end_time <= now
                or not computer.is_active
                or computer.status != ComputerStatus.AVAILABLE
            ):
                await session.rollback()
                continue
            transition_booking(booking, BookingStatus.ACTIVE)
            session.add(Session(booking_id=booking.id, started_at=now))
            computer.status = ComputerStatus.OCCUPIED
            record_audit(session, actor_id=None, action="session.auto_started", entity_type="booking", entity_id=booking.id,
                         club_id=computer.club_id, details={"started_at": now.isoformat(), "computer_id": str(computer.id)})
            if booking.user_id is not None:
                enqueue_notification(
                    session,
                    user_id=booking.user_id,
                    booking_id=booking.id,
                    kind="SESSION_STARTED",
                    title="Your session has started",
                    message="Your reserved session has started automatically.",
                    payload={"booking_id": str(booking.id), "club_id": str(computer.club_id)},
                )
            await session.commit()


async def run_worker() -> None:
    logger.info("Cyberoom session automation worker started")
    try:
        while True:
            try:
                await run_session_automation_once()
            except Exception:
                logger.exception("Session automation cycle failed")
            await asyncio.sleep(POLL_SECONDS)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_worker())
