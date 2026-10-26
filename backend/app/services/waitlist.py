import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Booking, BookingStatus, Club, Computer, ComputerStatus, User, WaitlistEntry
from app.schemas import WaitlistCreate
from app.services.audit import record_audit
from app.services.errors import ServiceError
from app.services.pricing import calculate_price


async def create_waitlist_entry(session: AsyncSession, user: User, payload: WaitlistCreate) -> WaitlistEntry:
    now = datetime.now(timezone.utc)
    if payload.start_time <= now:
        raise ServiceError("WAITLIST_IN_PAST", "A waitlist request must start in the future.", 422)
    club = await session.scalar(
        select(Club).where(Club.id == payload.club_id, Club.is_active.is_(True))
        .options(selectinload(Club.computers), selectinload(Club.tariffs))
    )
    if club is None:
        raise ServiceError("CLUB_NOT_FOUND", "Club not found.", 404)

    candidates = [computer for computer in club.computers if computer.is_active and computer.status not in (ComputerStatus.DISABLED, ComputerStatus.MAINTENANCE)]
    if payload.computer_id is not None:
        candidates = [computer for computer in candidates if computer.id == payload.computer_id]
        if not candidates:
            raise ServiceError("COMPUTER_UNAVAILABLE", "Choose an active computer in this club.", 422)
    if not candidates:
        raise ServiceError("NO_BOOKABLE_COMPUTERS", "This club has no computers that can be booked.", 409)

    calculate_price(payload.start_time, payload.end_time, club.tariffs, club.timezone)
    available = False
    for computer in candidates:
        overdue = await session.scalar(select(Booking.id).where(
            Booking.computer_id == computer.id,
            Booking.status == BookingStatus.ACTIVE,
            Booking.end_time <= now,
        ))
        conflict = await session.scalar(select(Booking.id).where(
            Booking.computer_id == computer.id,
            Booking.status.in_((BookingStatus.PENDING, BookingStatus.CONFIRMED, BookingStatus.ACTIVE)),
            Booking.start_time < payload.end_time,
            Booking.end_time > payload.start_time,
        ))
        if overdue is None and conflict is None:
            available = True
            break
    if available:
        raise ServiceError("WAITLIST_NOT_NEEDED", "A computer is available for this time. Book it directly.", 409)

    duplicate = await session.scalar(select(WaitlistEntry.id).where(
        WaitlistEntry.user_id == user.id,
        WaitlistEntry.club_id == payload.club_id,
        WaitlistEntry.computer_id == payload.computer_id if payload.computer_id is not None else WaitlistEntry.computer_id.is_(None),
        WaitlistEntry.start_time == payload.start_time,
        WaitlistEntry.end_time == payload.end_time,
        WaitlistEntry.status.in_(("WAITING", "NOTIFIED")),
    ))
    if duplicate is not None:
        raise ServiceError("WAITLIST_ALREADY_EXISTS", "You already have a request for this time.", 409)

    entry = WaitlistEntry(
        user_id=user.id,
        club_id=payload.club_id,
        computer_id=payload.computer_id,
        start_time=payload.start_time,
        end_time=payload.end_time,
    )
    session.add(entry)
    record_audit(
        session, actor_id=user.id, action="waitlist.created", entity_type="waitlist", entity_id=entry.id, club_id=club.id,
        details={"computer_id": str(payload.computer_id) if payload.computer_id else None},
    )
    await session.commit()
    await session.refresh(entry)
    return entry


async def list_waitlist_entries(session: AsyncSession, user: User) -> list[WaitlistEntry]:
    return list(await session.scalars(
        select(WaitlistEntry).where(WaitlistEntry.user_id == user.id).order_by(WaitlistEntry.created_at.desc()).limit(100)
    ))


async def cancel_waitlist_entry(session: AsyncSession, user: User, entry_id: uuid.UUID) -> WaitlistEntry:
    entry = await session.scalar(select(WaitlistEntry).where(WaitlistEntry.id == entry_id).with_for_update())
    if entry is None or entry.user_id != user.id:
        raise ServiceError("WAITLIST_NOT_FOUND", "Waitlist request not found.", 404)
    if entry.status != "CANCELLED":
        entry.status = "CANCELLED"
        record_audit(session, actor_id=user.id, action="waitlist.cancelled", entity_type="waitlist", entity_id=entry.id, club_id=entry.club_id)
        await session.commit()
        await session.refresh(entry)
    return entry
