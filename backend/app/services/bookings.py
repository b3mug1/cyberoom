import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.models import Booking, BookingSource, BookingStatus, Club, Computer, ComputerStatus, Membership, Payment, PromoCode, Review, Session, StaffAssignment, User, UserRole
from app.schemas import BookingCreate, BookingQuoteResponse, BookingReschedule, BusyInterval, ClubAvailability, ClubReviewResponse, ComputerAvailability, ReviewCreate, SessionExtend, WalkInCreate
from app.services.audit import record_audit
from app.services.errors import ServiceError
from app.services.notifications import cancel_booking_reminders, enqueue_notification, notify_waitlist_for_slot
from app.services import payments
from app.services.pricing import apply_discount, calculate_interval_price, calculate_price
from app.services.transitions import transition_booking

ACTIVE_STATUSES = (BookingStatus.PENDING, BookingStatus.CONFIRMED, BookingStatus.ACTIVE)


def _booking_options():
    return (
        joinedload(Booking.computer).joinedload(Computer.club),
        joinedload(Booking.review).joinedload(Review.computer),
        joinedload(Booking.promo_code),
        joinedload(Booking.payment),
    )


async def _price_with_promo(
    session: AsyncSession,
    *,
    club: Club,
    user_id: uuid.UUID | None,
    start_time: datetime,
    end_time: datetime,
    code: str | None,
    lock_promo: bool = False,
) -> tuple[Decimal, Decimal, Decimal, PromoCode | None]:
    subtotal = calculate_price(start_time, end_time, club.tariffs, club.timezone)
    if not code:
        return subtotal, subtotal, Decimal("0.00"), None

    query = select(PromoCode).where(
        PromoCode.club_id == club.id,
        PromoCode.code == code.strip().upper(),
        PromoCode.is_active.is_(True),
        PromoCode.starts_at <= datetime.now(timezone.utc),
        PromoCode.ends_at > datetime.now(timezone.utc),
    )
    if lock_promo:
        query = query.with_for_update()
    promo = await session.scalar(query)
    if promo is None:
        raise ServiceError("PROMO_CODE_INVALID", "This promo code is invalid or unavailable.", 422)
    if promo.usage_limit is not None and promo.used_count >= promo.usage_limit:
        raise ServiceError("PROMO_CODE_EXHAUSTED", "This promo code has reached its usage limit.", 409)
    if user_id is not None:
        user_uses = await session.scalar(
            select(func.count(Booking.id)).where(
                Booking.user_id == user_id,
                Booking.promo_code_id == promo.id,
                Booking.status.not_in((BookingStatus.CANCELLED, BookingStatus.EXPIRED)),
            )
        )
        if (user_uses or 0) >= promo.per_user_limit:
            raise ServiceError("PROMO_CODE_USER_LIMIT", "You have already used this promo code the maximum number of times.", 409)
    total, discount = apply_discount(subtotal, promo.discount_type, promo.discount_value)
    return subtotal, total, discount, promo


async def _membership_for_interval(
    session: AsyncSession, *, user_id: uuid.UUID, club_id: uuid.UUID, minutes: int, lock: bool,
) -> Membership:
    now = datetime.now(timezone.utc)
    query = select(Membership).where(
        Membership.user_id == user_id,
        Membership.club_id == club_id,
        Membership.starts_at <= now,
        Membership.expires_at > now,
        Membership.remaining_minutes >= minutes,
    ).order_by(Membership.expires_at, Membership.created_at)
    if lock:
        query = query.with_for_update(of=Membership)
    membership = await session.scalar(query)
    if membership is None:
        raise ServiceError("MEMBERSHIP_HOURS_UNAVAILABLE", "No active membership has enough hours for this session.", 409)
    return membership


async def _reload_booking(session: AsyncSession, booking_id: uuid.UUID) -> Booking:
    booking = await session.scalar(select(Booking).where(Booking.id == booking_id).options(*_booking_options()))
    assert booking is not None
    return booking


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


async def quote_booking(session: AsyncSession, payload: BookingCreate, user: User | None = None) -> BookingQuoteResponse:
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
    subtotal, total, discount, promo = await _price_with_promo(
        session, club=club, user_id=user.id if user else None, start_time=payload.start_time, end_time=payload.end_time, code=payload.promo_code,
    )
    membership_minutes = 0
    membership_credit = Decimal("0.00")
    if payload.use_membership:
        if user is None:
            raise ServiceError("UNAUTHORIZED", "Sign in to use membership hours.", 401)
        membership_minutes = int((payload.end_time - payload.start_time).total_seconds() // 60)
        await _membership_for_interval(session, user_id=user.id, club_id=club.id, minutes=membership_minutes, lock=False)
        total = Decimal("0.00")
        discount = subtotal
        membership_credit = subtotal
    return BookingQuoteResponse(
        total_price=total, subtotal_price=subtotal, discount_amount=discount,
        promo_code=promo.code if promo else None,
        membership_minutes=membership_minutes, membership_credit_amount=membership_credit,
    )


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
    club = await session.scalar(select(Club).where(Club.id == computer.club_id).options(selectinload(Club.tariffs)).with_for_update(of=Club))
    if club is None:
        raise ServiceError("CLUB_NOT_FOUND", "The selected computer's club was not found.", 404)
    if not computer.is_active or not club.is_active or computer.status == ComputerStatus.DISABLED:
        raise ServiceError("COMPUTER_UNAVAILABLE", "The selected computer is not available for booking.", 409)
    if computer.status == ComputerStatus.MAINTENANCE:
        raise ServiceError("COMPUTER_UNAVAILABLE", "The selected computer is under maintenance.", 409)
    await _ensure_no_overdue_session(session, computer.id)

    await _ensure_interval_available(session, computer.id, payload.start_time, payload.end_time)

    subtotal, price, discount, promo = await _price_with_promo(
        session, club=club, user_id=user.id, start_time=payload.start_time, end_time=payload.end_time,
        code=payload.promo_code, lock_promo=bool(payload.promo_code),
    )
    membership = None
    membership_minutes = 0
    membership_credit = Decimal("0.00")
    if payload.use_membership:
        membership_minutes = int((payload.end_time - payload.start_time).total_seconds() // 60)
        membership = await _membership_for_interval(
            session, user_id=user.id, club_id=club.id, minutes=membership_minutes, lock=True,
        )
        membership.remaining_minutes -= membership_minutes
        price = Decimal("0.00")
        discount = subtotal
        membership_credit = subtotal
    booking = Booking(
        user_id=user.id,
        source=BookingSource.ONLINE,
        computer_id=computer.id,
        start_time=payload.start_time,
        end_time=payload.end_time,
        status=BookingStatus.CONFIRMED,
        total_price=price,
        refund_cutoff_hours=club.refund_cutoff_hours,
        subtotal_price=subtotal,
        discount_amount=discount,
        promo_code_id=promo.id if promo else None,
        membership_id=membership.id if membership else None,
        membership_minutes=membership_minutes,
        membership_credit_amount=membership_credit,
    )
    if promo is not None:
        promo.used_count += 1
    session.add(booking)
    try:
        await session.flush()
        record_audit(
            session, actor_id=user.id, action="booking.created", entity_type="booking", entity_id=booking.id, club_id=club.id,
            details={"source": "ONLINE", "total_price": str(price)},
        )
        enqueue_notification(
            session,
            user_id=user.id,
            booking_id=booking.id,
            kind="BOOKING_CONFIRMED",
            title="Booking confirmed",
            message="Your Cyberoom reservation is confirmed.",
            payload={"booking_id": str(booking.id), "club_id": str(club.id)},
        )
        enqueue_notification(
            session,
            user_id=user.id,
            booking_id=booking.id,
            kind="SESSION_REMINDER",
            title="Your session starts soon",
            message="Your gaming session starts in about one hour.",
            payload={"booking_id": str(booking.id), "club_id": str(club.id)},
            scheduled_at=booking.start_time - timedelta(hours=1),
        )
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise ServiceError("BOOKING_CONFLICT", "The selected computer is already booked for this time period.", 409) from error
    return await _reload_booking(session, booking.id)


async def reschedule_booking(session: AsyncSession, user: User, booking_id: uuid.UUID, payload: BookingReschedule) -> Booking:
    booking = await session.scalar(
        select(Booking).where(Booking.id == booking_id).options(
            joinedload(Booking.computer), joinedload(Booking.promo_code),
        ).with_for_update(of=Booking)
    )
    if booking is None:
        raise ServiceError("BOOKING_NOT_FOUND", "Booking not found.", 404)
    if booking.user_id != user.id:
        raise ServiceError("FORBIDDEN", "You can only reschedule your own bookings.", 403)
    if booking.status not in (BookingStatus.PENDING, BookingStatus.CONFIRMED) or booking.start_time <= datetime.now(timezone.utc):
        raise ServiceError("BOOKING_NOT_RESCHEDULABLE", "Only upcoming confirmed bookings can be rescheduled.", 409)
    if payload.start_time <= datetime.now(timezone.utc):
        raise ServiceError("BOOKING_IN_PAST", "A booking cannot start in the past.", 422)
    payment = await session.scalar(select(Payment).where(Payment.booking_id == booking.id).with_for_update())
    if payment is not None and payment.status in ("CHECKOUT_CREATED", "PAID", "REFUND_PENDING", "REFUNDED"):
        raise ServiceError("PAYMENT_ALREADY_STARTED", "Cancel this booking before changing a paid or in-progress payment.", 409)

    previous_computer_id = booking.computer_id
    previous_start_time = booking.start_time
    previous_end_time = booking.end_time
    previous_club_id = booking.computer.club_id
    target_computer = await session.scalar(select(Computer).where(Computer.id == payload.computer_id).with_for_update())
    if target_computer is None:
        raise ServiceError("COMPUTER_NOT_FOUND", "The selected computer was not found.", 404)
    if target_computer.club_id != booking.computer.club_id:
        raise ServiceError("INVALID_RESCHEDULE_COMPUTER", "Choose a computer in the same club.", 422)
    club = await session.scalar(
        select(Club).where(Club.id == target_computer.club_id).options(selectinload(Club.tariffs)).with_for_update(of=Club)
    )
    if club is None or not club.is_active or not target_computer.is_active or target_computer.status in (ComputerStatus.DISABLED, ComputerStatus.MAINTENANCE):
        raise ServiceError("COMPUTER_UNAVAILABLE", "The selected computer is not available for booking.", 409)

    await _ensure_no_overdue_session(session, target_computer.id)
    await _ensure_interval_available(session, target_computer.id, payload.start_time, payload.end_time, booking.id)
    subtotal = calculate_price(payload.start_time, payload.end_time, club.tariffs, club.timezone)
    membership = None
    new_membership_minutes = 0
    membership_credit = Decimal("0.00")
    if booking.membership_id is not None:
        membership = await session.scalar(select(Membership).where(Membership.id == booking.membership_id).with_for_update())
        new_membership_minutes = int((payload.end_time - payload.start_time).total_seconds() // 60)
        if membership is None or membership.club_id != club.id or membership.expires_at <= datetime.now(timezone.utc):
            raise ServiceError("MEMBERSHIP_EXPIRED", "The membership used for this booking is no longer available for rescheduling.", 409)
        available_minutes = membership.remaining_minutes + booking.membership_minutes
        if available_minutes < new_membership_minutes:
            raise ServiceError("MEMBERSHIP_HOURS_UNAVAILABLE", "The membership does not have enough hours for the new interval.", 409)
        membership.remaining_minutes = available_minutes - new_membership_minutes
        price = Decimal("0.00")
        discount = subtotal
        membership_credit = subtotal
    elif booking.promo_code is not None:
        price, discount = apply_discount(subtotal, booking.promo_code.discount_type, booking.promo_code.discount_value)
    else:
        discount = min(booking.discount_amount, subtotal)
        price = subtotal - discount
    booking.computer_id = target_computer.id
    booking.start_time = payload.start_time
    booking.end_time = payload.end_time
    booking.total_price = price
    booking.subtotal_price = subtotal
    booking.discount_amount = discount
    booking.refund_cutoff_hours = club.refund_cutoff_hours
    booking.membership_minutes = new_membership_minutes
    booking.membership_credit_amount = membership_credit
    try:
        record_audit(
            session, actor_id=user.id, action="booking.rescheduled", entity_type="booking", entity_id=booking.id, club_id=club.id,
            details={"computer_id": str(target_computer.id), "start_time": payload.start_time.isoformat(), "end_time": payload.end_time.isoformat(), "total_price": str(price)},
        )
        await cancel_booking_reminders(session, booking.id)
        enqueue_notification(
            session,
            user_id=user.id,
            booking_id=booking.id,
            kind="BOOKING_RESCHEDULED",
            title="Booking updated",
            message="Your reservation time or computer has changed.",
            payload={"booking_id": str(booking.id), "club_id": str(club.id)},
        )
        enqueue_notification(
            session,
            user_id=user.id,
            booking_id=booking.id,
            kind="SESSION_REMINDER",
            title="Your session starts soon",
            message="Your gaming session starts in about one hour.",
            payload={"booking_id": str(booking.id), "club_id": str(club.id)},
            scheduled_at=booking.start_time - timedelta(hours=1),
        )
        if (previous_computer_id, previous_start_time, previous_end_time) != (booking.computer_id, booking.start_time, booking.end_time):
            await notify_waitlist_for_slot(
                session,
                club_id=previous_club_id,
                computer_id=previous_computer_id,
                start_time=previous_start_time,
                end_time=previous_end_time,
            )
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise ServiceError("BOOKING_CONFLICT", "The selected computer is already booked during this interval.", 409) from error
    return await _reload_booking(session, booking.id)


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
    club = await session.scalar(select(Club).where(Club.id == computer.club_id).options(selectinload(Club.tariffs)).with_for_update(of=Club))
    if club is None or not club.is_active or not computer.is_active or computer.status != ComputerStatus.AVAILABLE:
        raise ServiceError("COMPUTER_UNAVAILABLE", "This computer cannot start a walk-in session.", 409)
    if payload.end_time <= now:
        raise ServiceError("INVALID_BOOKING_TIME", "The session must end in the future.", 422)
    price = calculate_price(start, payload.end_time, club.tariffs, club.timezone)
    await _ensure_interval_available(session, computer.id, start, payload.end_time)
    booking = Booking(
        user_id=None, guest_name=payload.guest_name, source=BookingSource.WALK_IN,
        computer_id=computer.id, start_time=start, end_time=payload.end_time,
        status=BookingStatus.ACTIVE, total_price=price, refund_cutoff_hours=club.refund_cutoff_hours,
    )
    session.add(booking)
    try:
        await session.flush()
        session.add(Session(booking_id=booking.id, started_at=now, started_by_user_id=staff.id))
        computer.status = ComputerStatus.OCCUPIED
        record_audit(
            session, actor_id=staff.id, action="booking.walk_in_created", entity_type="booking", entity_id=booking.id, club_id=club.id,
            details={"computer_id": str(computer.id), "total_price": str(price)},
        )
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
    record_audit(
        session, actor_id=staff.id, action="session.started", entity_type="booking", entity_id=booking.id,
        club_id=computer.club_id, details={"computer_id": str(computer.id)},
    )
    await session.commit()


async def extend_session(session: AsyncSession, booking: Booking, payload: SessionExtend, actor: User | None = None) -> None:
    now = datetime.now(timezone.utc)
    if booking.status != BookingStatus.ACTIVE:
        raise ServiceError("SESSION_NOT_ACTIVE", "Only an active session can be extended.", 409)
    if payload.end_time <= booking.end_time or payload.end_time <= now:
        raise ServiceError("INVALID_EXTENSION", "The new end time must be later than the current end time.", 422)
    actual = await session.scalar(select(Session).where(Session.booking_id == booking.id).with_for_update())
    if actual is None or actual.ended_at is not None:
        raise ServiceError("SESSION_NOT_ACTIVE", "The session has already ended.", 409)
    club = await session.scalar(select(Club).where(Club.id == booking.computer.club_id).options(selectinload(Club.tariffs)).with_for_update(of=Club))
    if club is None or not club.is_active:
        raise ServiceError("CLUB_NOT_FOUND", "The club is unavailable.", 409)
    if payload.end_time - booking.start_time > timedelta(hours=8):
        raise ServiceError("INVALID_BOOKING_DURATION", "A session cannot exceed eight hours.", 422)
    # Keep the original quoted amount even if the club has since changed tariffs.
    extension_price = calculate_interval_price(booking.end_time, payload.end_time, club.tariffs, club.timezone)
    await _ensure_interval_available(session, booking.computer_id, booking.start_time, payload.end_time, booking.id)
    booking.end_time = payload.end_time
    booking.total_price += extension_price
    record_audit(
        session, actor_id=actor.id if actor else None, action="session.extended", entity_type="booking", entity_id=booking.id,
        club_id=booking.computer.club_id, details={"end_time": payload.end_time.isoformat(), "additional_price": str(extension_price)},
    )
    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise ServiceError("BOOKING_CONFLICT", "The extension overlaps the next booking.", 409) from error


async def end_session(session: AsyncSession, booking: Booking, staff: User | None, computer: Computer) -> None:
    if booking.status != BookingStatus.ACTIVE:
        raise ServiceError("SESSION_NOT_ACTIVE", "Only an active session can be ended.", 409)
    actual = await session.scalar(select(Session).where(Session.booking_id == booking.id).with_for_update())
    if actual is None or actual.ended_at is not None:
        raise ServiceError("SESSION_NOT_ACTIVE", "The session has already ended.", 409)
    actual.ended_at = datetime.now(timezone.utc)
    actual.ended_by_user_id = staff.id if staff else None
    transition_booking(booking, BookingStatus.COMPLETED)
    if computer.status == ComputerStatus.OCCUPIED:
        computer.status = ComputerStatus.AVAILABLE
    record_audit(
        session, actor_id=staff.id if staff else None, action="session.ended", entity_type="booking", entity_id=booking.id,
        club_id=computer.club_id, details={"ended_at": actual.ended_at.isoformat()},
    )
    if booking.user_id is not None:
        enqueue_notification(
            session,
            user_id=booking.user_id,
            booking_id=booking.id,
            kind="SESSION_COMPLETED",
            title="Your session is complete",
            message="Thanks for playing. You can now leave a review for the club and computer.",
            payload={"booking_id": str(booking.id), "club_id": str(computer.club_id)},
        )
    await session.commit()


async def list_bookings(session: AsyncSession, user: User) -> list[Booking]:
    return list(
        await session.scalars(
            select(Booking)
            .where(Booking.user_id == user.id)
            .options(*_booking_options())
            .order_by(Booking.start_time.desc())
            .limit(100)
        )
    )


async def get_booking(session: AsyncSession, user: User, booking_id: uuid.UUID) -> Booking:
    booking = await session.scalar(select(Booking).where(Booking.id == booking_id).options(*_booking_options()))
    if booking is None:
        raise ServiceError("BOOKING_NOT_FOUND", "Booking not found.", 404)
    if booking.user_id != user.id and user.role != UserRole.ADMIN:
        raise ServiceError("FORBIDDEN", "You can only view your own bookings.", 403)
    payment = await session.scalar(select(Payment.id).where(Payment.booking_id == booking.id))
    if payment is not None and booking.user_id == user.id:
        await payments.get_user_payment(session, user, payment)
        booking = await _reload_booking(session, booking.id)
    return booking


async def cancel_booking(session: AsyncSession, user: User, booking_id: uuid.UUID) -> Booking:
    booking = await session.scalar(select(Booking).where(Booking.id == booking_id).with_for_update())
    if booking is None:
        raise ServiceError("BOOKING_NOT_FOUND", "Booking not found.", 404)
    if booking.user_id != user.id:
        raise ServiceError("FORBIDDEN", "You can only cancel your own bookings.", 403)
    if booking.status not in (BookingStatus.PENDING, BookingStatus.CONFIRMED):
        raise ServiceError("INVALID_BOOKING_TRANSITION", "This booking can no longer be cancelled.", 409)
    computer_id = booking.computer_id
    booked_computer = await session.get(Computer, computer_id)
    if booked_computer is None:
        raise ServiceError("COMPUTER_NOT_FOUND", "The booked computer no longer exists.", 404)
    club_id = booked_computer.club_id
    start_time = booking.start_time
    end_time = booking.end_time
    refund_eligible = start_time - datetime.now(timezone.utc) >= timedelta(hours=booking.refund_cutoff_hours)
    await payments.handle_booking_cancellation(session, booking, refund_eligible=refund_eligible)
    await release_promo_quota(session, booking)
    await release_membership_credits(session, booking)
    transition_booking(booking, BookingStatus.CANCELLED)
    record_audit(session, actor_id=user.id, action="booking.cancelled", entity_type="booking", entity_id=booking.id, club_id=club_id)
    await cancel_booking_reminders(session, booking.id)
    enqueue_notification(
        session,
        user_id=user.id,
        booking_id=booking.id,
        kind="BOOKING_CANCELLED",
        title="Booking cancelled",
        message="Your reservation has been cancelled.",
        payload={"booking_id": str(booking.id), "club_id": str(club_id)},
    )
    await notify_waitlist_for_slot(session, club_id=club_id, computer_id=computer_id, start_time=start_time, end_time=end_time)
    await session.commit()
    return await _reload_booking(session, booking.id)


async def release_promo_quota(session: AsyncSession, booking: Booking) -> None:
    if booking.promo_code_id is None or booking.status not in (BookingStatus.PENDING, BookingStatus.CONFIRMED):
        return
    promo = await session.scalar(select(PromoCode).where(PromoCode.id == booking.promo_code_id).with_for_update())
    if promo is not None and promo.used_count > 0:
        promo.used_count -= 1


async def release_membership_credits(session: AsyncSession, booking: Booking) -> None:
    if booking.membership_id is None or booking.membership_minutes <= 0 or booking.status not in (BookingStatus.PENDING, BookingStatus.CONFIRMED):
        return
    membership = await session.scalar(select(Membership).where(Membership.id == booking.membership_id).with_for_update())
    if membership is not None:
        membership.remaining_minutes = min(membership.total_minutes, membership.remaining_minutes + booking.membership_minutes)


async def create_review(session: AsyncSession, user: User, booking_id: uuid.UUID, payload: ReviewCreate) -> Review:
    booking = await session.scalar(
        select(Booking).where(Booking.id == booking_id).options(joinedload(Booking.computer)).with_for_update(of=Booking)
    )
    if booking is None:
        raise ServiceError("BOOKING_NOT_FOUND", "Booking not found.", 404)
    if booking.user_id != user.id:
        raise ServiceError("FORBIDDEN", "You can only review your own bookings.", 403)
    if booking.source != BookingSource.ONLINE or booking.status != BookingStatus.COMPLETED:
        raise ServiceError("BOOKING_NOT_REVIEWABLE", "A review is available after an online booking is completed.", 409)
    existing = await session.scalar(select(Review.id).where(Review.booking_id == booking.id))
    if existing is not None:
        raise ServiceError("REVIEW_ALREADY_EXISTS", "This booking already has a review.", 409)

    club = await session.scalar(select(Club).where(Club.id == booking.computer.club_id).with_for_update())
    if club is None:
        raise ServiceError("CLUB_NOT_FOUND", "Club not found.", 404)
    review = Review(
        booking_id=booking.id,
        user_id=user.id,
        club_id=club.id,
        computer_id=booking.computer_id,
        club_rating=payload.club_rating,
        computer_rating=payload.computer_rating,
        comment=payload.comment,
    )
    session.add(review)
    try:
        await session.flush()
        record_audit(
            session, actor_id=user.id, action="review.created", entity_type="review", entity_id=review.id, club_id=club.id,
            details={"club_rating": payload.club_rating, "computer_rating": payload.computer_rating},
        )
        average_rating = await session.scalar(select(func.avg(Review.club_rating)).where(Review.club_id == club.id))
        club.rating = average_rating
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise ServiceError("REVIEW_ALREADY_EXISTS", "This booking already has a review.", 409) from error
    result = await session.scalar(
        select(Review).where(Review.id == review.id).options(joinedload(Review.computer))
    )
    assert result is not None
    return result


async def list_club_reviews(session: AsyncSession, club_id: uuid.UUID) -> list[Review]:
    club_exists = await session.scalar(select(Club.id).where(Club.id == club_id, Club.is_active.is_(True)))
    if club_exists is None:
        raise ServiceError("CLUB_NOT_FOUND", "Club not found.", 404)
    return list(await session.scalars(
        select(Review).where(Review.club_id == club_id).options(joinedload(Review.computer))
        .order_by(Review.created_at.desc()).limit(50)
    ))


async def get_booking_review(session: AsyncSession, user: User, booking_id: uuid.UUID) -> Review | None:
    booking = await session.scalar(select(Booking).where(Booking.id == booking_id))
    if booking is None:
        raise ServiceError("BOOKING_NOT_FOUND", "Booking not found.", 404)
    if booking.user_id != user.id and user.role != UserRole.ADMIN:
        raise ServiceError("FORBIDDEN", "You can only view your own booking review.", 403)
    return await session.scalar(
        select(Review).where(Review.booking_id == booking_id).options(joinedload(Review.computer))
    )
