import uuid
from datetime import datetime, timezone
from typing import Protocol

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Booking, BookingStatus, Computer, ComputerStatus, Notification, WaitlistEntry
from app.services.errors import ServiceError


class NotificationAdapter(Protocol):
    """Provider-neutral delivery contract for email, SMS, and messenger adapters."""

    channel: str

    async def send(self, destination: str, title: str, message: str, metadata: dict[str, str]) -> None: ...


def enqueue_notification(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    kind: str,
    title: str,
    message: str,
    booking_id: uuid.UUID | None = None,
    payload: dict | None = None,
    scheduled_at: datetime | None = None,
) -> Notification:
    notification = Notification(
        user_id=user_id,
        booking_id=booking_id,
        kind=kind,
        title=title,
        message=message,
        payload=payload or {},
        scheduled_at=scheduled_at or datetime.now(timezone.utc),
    )
    session.add(notification)
    return notification


async def cancel_booking_reminders(session: AsyncSession, booking_id: uuid.UUID) -> None:
    now = datetime.now(timezone.utc)
    await session.execute(
        update(Notification)
        .where(
            Notification.booking_id == booking_id,
            Notification.kind == "SESSION_REMINDER",
            Notification.scheduled_at > now,
            Notification.cancelled_at.is_(None),
        )
        .values(cancelled_at=now)
    )


async def notify_waitlist_for_slot(
    session: AsyncSession,
    *,
    club_id: uuid.UUID,
    computer_id: uuid.UUID,
    start_time: datetime,
    end_time: datetime,
) -> None:
    computer = await session.get(Computer, computer_id)
    if computer is None or computer.club_id != club_id or not computer.is_active or computer.status in (ComputerStatus.DISABLED, ComputerStatus.MAINTENANCE):
        return
    entries = list(await session.scalars(
        select(WaitlistEntry)
        .where(
            WaitlistEntry.club_id == club_id,
            WaitlistEntry.status == "WAITING",
            WaitlistEntry.notified_at.is_(None),
            ((WaitlistEntry.computer_id == computer_id) | WaitlistEntry.computer_id.is_(None)),
            WaitlistEntry.start_time < end_time,
            WaitlistEntry.end_time > start_time,
        )
        .order_by(WaitlistEntry.created_at)
        .limit(100)
        .with_for_update(skip_locked=True)
    ))
    now = datetime.now(timezone.utc)
    for entry in entries:
        overdue = await session.scalar(select(Booking.id).where(
            Booking.computer_id == computer_id,
            Booking.status == BookingStatus.ACTIVE,
            Booking.end_time <= now,
        ))
        conflict = await session.scalar(select(Booking.id).where(
            Booking.computer_id == computer_id,
            Booking.status.in_((BookingStatus.PENDING, BookingStatus.CONFIRMED, BookingStatus.ACTIVE)),
            Booking.start_time < entry.end_time,
            Booking.end_time > entry.start_time,
        ))
        if overdue is not None or conflict is not None:
            continue
        entry.status = "NOTIFIED"
        entry.notified_at = now
        enqueue_notification(
            session,
            user_id=entry.user_id,
            kind="WAITLIST_AVAILABLE",
            title="A computer may be available",
            message="A requested time appears to have opened. Check availability and book it soon.",
            payload={
                "club_id": str(club_id),
                "computer_id": str(computer_id),
                "start_time": entry.start_time.isoformat(),
                "end_time": entry.end_time.isoformat(),
            },
        )
        break


async def list_notifications(session: AsyncSession, user_id: uuid.UUID) -> list[Notification]:
    now = datetime.now(timezone.utc)
    return list(await session.scalars(
        select(Notification)
        .where(
            Notification.user_id == user_id,
            Notification.scheduled_at <= now,
            Notification.cancelled_at.is_(None),
        )
        .order_by(Notification.scheduled_at.desc())
        .limit(100)
    ))


async def mark_notification_read(session: AsyncSession, user_id: uuid.UUID, notification_id: uuid.UUID) -> Notification:
    notification = await session.scalar(
        select(Notification).where(Notification.id == notification_id).with_for_update()
    )
    if notification is None or notification.user_id != user_id:
        raise ServiceError("NOTIFICATION_NOT_FOUND", "Notification not found.", 404)
    if notification.cancelled_at is not None or notification.scheduled_at > datetime.now(timezone.utc):
        raise ServiceError("NOTIFICATION_NOT_AVAILABLE", "This notification is not available yet.", 409)
    if notification.read_at is None:
        notification.read_at = datetime.now(timezone.utc)
        await session.commit()
    return notification
