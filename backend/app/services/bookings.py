import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.models import Booking, BookingSource, BookingStatus, Club, Computer, ComputerStatus, Session, StaffAssignment, User, UserRole
from app.schemas import BookingCreate, BusyInterval, ClubAvailability, ComputerAvailability, SessionExtend, WalkInCreate
from app.services.errors import ServiceError
from app.services.pricing import calculate_price
from app.services.transitions import transition_booking

ACTIVE_STATUSES = (BookingStatus.PENDING, BookingStatus.CONFIRMED, BookingStatus.ACTIVE)


async def _ensure_no_overdue_session(session: AsyncSession, computer_id: uuid.UUID) -> None:
    overdue = await session.scalar(select(Booking.id).where(
        Booking.computer_id == computer_id, Booking.status == BookingStatus.ACTIVE,
        Booking.end_time <= datetime.now(timezone.utc),
    ))
    if overdue is not None:
        raise ServiceError("SESSION_OVERDUE", "An active session is overdue. Staff must extend or end it first.", 409)


async def _ensure_interval_available(
    session: AsyncSession, computer_id: uuid.UUID, start: datetime, end: datetime,
    exclude_booking_id: uuid.UUID | None = None,
) -> None:
    query = select(Booking.id).where(
        Booking.computer_id == computer_id, Booking.status.in_(ACTIVE_STATUSES),
        Booking.start_time < end, Booking.end_time > start,
    )
    if exclude_booking_id is not None:
        query = query.where(Booking.id != exclude_booking_id)
    if await session.scalar(query) is not None:
        raise ServiceError("BOOKING_CONFLICT", "This computer is already booked during the requested interval.", 409)


async def club_availability(session: AsyncSession, club_id: uuid.UUID, start: datetime, end: datetime) -> ClubAvailability:
    if start.tzinfo is None or end.tzinfo is None or start >= end or end - start > timedelta(days=7):
        raise ServiceError("INVALID_AVAILABILITY_RANGE", "Choose a timezone-aware interval of at most seven days.", 422)
    club = await session.get(Club, club_id)
    if club is None or not club.is_active:
        raise ServiceError("CLUB_NOT_FOUND", "Club not found.", 404)
    computers = list(await session.scalars(select(Computer).where(Computer.club_id == club_id).order_by(Computer.name)))
    bookings = list(await session.scalars(
        select(Booking).join(Computer, Booking.computer_id == Computer.id)
        .where(Computer.club_id == club_id, Booking.status.in_(ACTIVE_STATUSES),
               ((Booking.start_time < end) & (Booking.end_time > start)) |
               ((Booking.status == BookingStatus.ACTIVE) & (Booking.end_time <= datetime.now(timezone.utc)) & (Booking.start_time < end)))
        .order_by(Booking.start_time)
    ))
    by_computer: dict[uuid.UUID, list[BusyInterval]] = {computer.id: [] for computer in computers}
    for booking in bookings:
        effective_end = end if booking.status == BookingStatus.ACTIVE and booking.end_time <= datetime.now(timezone.utc) else booking.end_time
        by_computer[booking.computer_id].append(BusyInterval(start_time=booking.start_time, end_time=effective_end))
    return ClubAvailability(
        club_id=club_id, start_time=start, end_time=end,
        computers=[ComputerAvailability(
            computer_id=computer.id, computer_name=computer.name,
            status=computer.status, is_active=computer.is_active, busy=by_computer[computer.id],
        ) for computer in computers],
    )


async def quote_booking(session: AsyncSession, payload: BookingCreate):
    if payload.start_time <= datetime.now(timezone.utc):
        raise ServiceError("BOOKING_IN_PAST", "A booking cannot start in the past.", 422)
    computer = await session.get(Computer, payload.computer_id)
    if computer is None:
        raise ServiceError("COMPUTER_NOT_FOUND", "The selected computer was not found.", 404)
    club = await session.scalar(select(Club).where(Club.id == computer.club_id).options(selectinload(Club.tariffs)))
    if club is None or not club.is_active or not computer.is_active or computer.status in (ComputerStatus.DISABLED, ComputerStatus.MAINTENANCE):
        raise ServiceError("COMPUTER_UNAVAILABLE", "The selected computer is not available for booking.", 409)
    await _ensure_no_overdue_session(session, computer.id)
    await _ensure_interval_available(session, computer.id, payload.start_time, payload.end_time)
    return calculate_price(payload.start_time, payload.end_time, club.tariffs)


async def create_booking(session: AsyncSession, user: User, payload: BookingCreate) -> Booking:
    now = datetime.now(timezone.utc)
    if payload.start_time <= now:
        raise ServiceError("BOOKING_IN_PAST", "A booking cannot start in the past.", 422)

    computer = await session.scalar(
        select(Computer)
        .where(Computer.id == payload.computer_id)
        .with_for_update()
    )
    if computer is None:
        raise ServiceError("COMPUTER_NOT_FOUND", "The selected computer was not found.", 404)
    club = await session.scalar(select(Club).where(Club.id == computer.club_id).options(selectinload(Club.tariffs)))
    if club is None:
        raise ServiceError("CLUB_NOT_FOUND", "The selected computer's club was not found.", 404)
    if not computer.is_active or not club.is_active or computer.status == ComputerStatus.DISABLED:
        raise ServiceError("COMPUTER_UNAVAILABLE", "The selected computer is not available for booking.", 409)
    if computer.status == ComputerStatus.MAINTENANCE:
        raise ServiceError("COMPUTER_UNAVAILABLE", "The selected computer is under maintenance.", 409)
    await _ensure_no_overdue_session(session, computer.id)

    await _ensure_interval_available(session, computer.id, payload.start_time, payload.end_time)

    price = calculate_price(payload.start_time, payload.end_time, club.tariffs)
    booking = Booking(
        user_id=user.id,
        source=BookingSource.ONLINE,
        computer_id=computer.id,
        start_time=payload.start_time,
        end_time=payload.end_time,
        status=BookingStatus.CONFIRMED,
        total_price=price,
    )
    session.add(booking)
    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise ServiceError("BOOKING_CONFLICT", "The selected computer is already booked for this time period.", 409) from error
    await session.refresh(booking)
    return booking


async def create_walk_in(session: AsyncSession, staff: User, payload: WalkInCreate) -> Booking:
    now = datetime.now(timezone.utc)
    start = now.replace(second=0, microsecond=0)
    computer = await session.scalar(select(Computer).where(Computer.id == payload.computer_id).with_for_update())
    if computer is None:
        raise ServiceError("COMPUTER_NOT_FOUND", "The selected computer was not found.", 404)
    assigned = await session.scalar(select(StaffAssignment.id).where(
        StaffAssignment.staff_user_id == staff.id, StaffAssignment.club_id == computer.club_id
    ))
    if assigned is None:
        raise ServiceError("FORBIDDEN", "You are not assigned to this club.", 403)
    club = await session.scalar(select(Club).where(Club.id == computer.club_id).options(selectinload(Club.tariffs)))
    if club is None or not club.is_active or not computer.is_active or computer.status != ComputerStatus.AVAILABLE:
        raise ServiceError("COMPUTER_UNAVAILABLE", "This computer cannot start a walk-in session.", 409)
    if payload.end_time <= now:
        raise ServiceError("INVALID_BOOKING_TIME", "The session must end in the future.", 422)
    price = calculate_price(start, payload.end_time, club.tariffs)
    await _ensure_interval_available(session, computer.id, start, payload.end_time)
    booking = Booking(
        user_id=None, guest_name=payload.guest_name, source=BookingSource.WALK_IN,
        computer_id=computer.id, start_time=start, end_time=payload.end_time,
        status=BookingStatus.ACTIVE, total_price=price,
    )
    session.add(booking)
    try:
        await session.flush()
        session.add(Session(booking_id=booking.id, started_at=now, started_by_user_id=staff.id))
        computer.status = ComputerStatus.OCCUPIED
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise ServiceError("BOOKING_CONFLICT", "This computer is already booked during the requested session.", 409) from error
    await session.refresh(booking)
    return booking


async def start_session(session: AsyncSession, booking: Booking, staff: User, computer: Computer) -> None:
    now = datetime.now(timezone.utc)
    if booking.status != BookingStatus.CONFIRMED or not booking.start_time <= now < booking.end_time:
        raise ServiceError("SESSION_NOT_STARTABLE", "Check-in is allowed only during a confirmed booking.", 409)
    if not computer.is_active or computer.status != ComputerStatus.AVAILABLE:
        raise ServiceError("COMPUTER_UNAVAILABLE", "This computer cannot start a session.", 409)
    transition_booking(booking, BookingStatus.ACTIVE)
    session.add(Session(booking_id=booking.id, started_at=now, started_by_user_id=staff.id))
    computer.status = ComputerStatus.OCCUPIED
    await session.commit()


async def extend_session(session: AsyncSession, booking: Booking, payload: SessionExtend) -> None:
    now = datetime.now(timezone.utc)
    if booking.status != BookingStatus.ACTIVE:
        raise ServiceError("SESSION_NOT_ACTIVE", "Only an active session can be extended.", 409)
    if payload.end_time <= booking.end_time or payload.end_time <= now:
        raise ServiceError("INVALID_EXTENSION", "The new end time must be later than the current end time.", 422)
    actual = await session.scalar(select(Session).where(Session.booking_id == booking.id).with_for_update())
    if actual is None or actual.ended_at is not None:
        raise ServiceError("SESSION_NOT_ACTIVE", "The session has already ended.", 409)
    club = await session.scalar(select(Club).where(Club.id == booking.computer.club_id).options(selectinload(Club.tariffs)))
    if club is None or not club.is_active:
        raise ServiceError("CLUB_NOT_FOUND", "The club is unavailable.", 409)
    if payload.end_time - booking.start_time > timedelta(hours=8):
        raise ServiceError("INVALID_BOOKING_DURATION", "A session cannot exceed eight hours.", 422)
    # Keep the original quoted amount even if the club has since changed tariffs.
    extension_price = calculate_price(booking.end_time, payload.end_time, club.tariffs)
    await _ensure_interval_available(session, booking.computer_id, booking.start_time, payload.end_time, booking.id)
    booking.end_time = payload.end_time
    booking.total_price += extension_price
    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise ServiceError("BOOKING_CONFLICT", "The extension overlaps the next booking.", 409) from error


async def end_session(session: AsyncSession, booking: Booking, staff: User, computer: Computer) -> None:
    if booking.status != BookingStatus.ACTIVE:
        raise ServiceError("SESSION_NOT_ACTIVE", "Only an active session can be ended.", 409)
    actual = await session.scalar(select(Session).where(Session.booking_id == booking.id).with_for_update())
    if actual is None or actual.ended_at is not None:
        raise ServiceError("SESSION_NOT_ACTIVE", "The session has already ended.", 409)
    actual.ended_at = datetime.now(timezone.utc)
    actual.ended_by_user_id = staff.id
    transition_booking(booking, BookingStatus.COMPLETED)
    if computer.status == ComputerStatus.OCCUPIED:
        computer.status = ComputerStatus.AVAILABLE
    await session.commit()


async def list_bookings(session: AsyncSession, user: User) -> list[Booking]:
    return list(
        await session.scalars(
            select(Booking)
            .where(Booking.user_id == user.id)
            .options(joinedload(Booking.computer))
            .order_by(Booking.start_time.desc())
            .limit(100)
        )
    )


async def get_booking(session: AsyncSession, user: User, booking_id: uuid.UUID) -> Booking:
    booking = await session.scalar(select(Booking).where(Booking.id == booking_id).options(joinedload(Booking.computer)))
    if booking is None:
        raise ServiceError("BOOKING_NOT_FOUND", "Booking not found.", 404)
    if booking.user_id != user.id and user.role != UserRole.ADMIN:
        raise ServiceError("FORBIDDEN", "You can only view your own bookings.", 403)
    return booking


async def cancel_booking(session: AsyncSession, user: User, booking_id: uuid.UUID) -> Booking:
    booking = await session.scalar(select(Booking).where(Booking.id == booking_id).with_for_update())
    if booking is None:
        raise ServiceError("BOOKING_NOT_FOUND", "Booking not found.", 404)
    if booking.user_id != user.id:
        raise ServiceError("FORBIDDEN", "You can only cancel your own bookings.", 403)
    if booking.status not in (BookingStatus.PENDING, BookingStatus.CONFIRMED):
        raise ServiceError("INVALID_BOOKING_TRANSITION", "This booking can no longer be cancelled.", 409)
    transition_booking(booking, BookingStatus.CANCELLED)
    await session.commit()
    await session.refresh(booking)
    return booking
