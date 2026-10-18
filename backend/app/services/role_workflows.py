import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.models import (
    Booking,
    BookingStatus,
    Club,
    Computer,
    ComputerStatus,
    StaffAssignment,
    Tariff,
    User,
    UserRole,
)
from app.schemas import (
    AdminDashboard,
    AdminBookingStatusUpdate,
    ClubCreate,
    ClubUpdate,
    ComputerCreate,
    ComputerResponse,
    ComputerUpdate,
    ComputerStatusUpdate,
    ManagedClubResponse,
    OwnerClubMetric,
    OwnerDashboard,
    StaffBookingResponse,
    StaffDashboard,
    StaffComputerResponse,
    StaffAssignmentCreate,
    StaffMemberResponse,
    SessionExtend,
    TariffCreate,
    TariffUpdate,
    UserActiveUpdate,
    UserAdminResponse,
)
from app.services.errors import ServiceError
from app.services import bookings
from app.services.transitions import transition_booking

ACTIVE_BOOKING_STATUSES = (BookingStatus.PENDING, BookingStatus.CONFIRMED, BookingStatus.ACTIVE)
REVENUE_BOOKING_STATUSES = (BookingStatus.CONFIRMED, BookingStatus.ACTIVE, BookingStatus.COMPLETED)


def _today_start() -> datetime:
    return datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)


def _today_end() -> datetime:
    return _today_start() + timedelta(days=1)


async def _owned_club(session: AsyncSession, owner: User, club_id: uuid.UUID, lock: bool = False) -> Club:
    query = select(Club).where(Club.id == club_id, Club.owner_id == owner.id)
    if lock:
        query = query.with_for_update(of=Club)
    club = await session.scalar(query)
    if club is None:
        raise ServiceError("CLUB_NOT_FOUND", "Club not found in your account.", 404)
    return club


async def _owned_computer(session: AsyncSession, owner: User, computer_id: uuid.UUID, lock: bool = False) -> Computer:
    query = select(Computer).join(Club).where(Computer.id == computer_id, Club.owner_id == owner.id)
    if lock:
        query = query.with_for_update(of=Computer)
    computer = await session.scalar(query)
    if computer is None:
        raise ServiceError("COMPUTER_NOT_FOUND", "Computer not found in your clubs.", 404)
    return computer


async def _owned_tariff(session: AsyncSession, owner: User, tariff_id: uuid.UUID) -> Tariff:
    tariff = await session.scalar(
        select(Tariff).join(Club).where(Tariff.id == tariff_id, Club.owner_id == owner.id)
    )
    if tariff is None:
        raise ServiceError("TARIFF_NOT_FOUND", "Tariff not found in your clubs.", 404)
    return tariff


async def _ensure_no_active_session(session: AsyncSession, computer_id: uuid.UUID) -> None:
    active = await session.scalar(select(Booking.id).where(
        Booking.computer_id == computer_id, Booking.status == BookingStatus.ACTIVE
    ))
    if active is not None:
        raise ServiceError("SESSION_ACTIVE", "End the active session before changing this computer's status.", 409)


async def _ensure_no_live_booking(session: AsyncSession, computer_id: uuid.UUID) -> None:
    booking = await session.scalar(select(Booking.id).where(
        Booking.computer_id == computer_id,
        Booking.status.in_(ACTIVE_BOOKING_STATUSES),
        (Booking.status == BookingStatus.ACTIVE) | (Booking.end_time > datetime.now(timezone.utc)),
    ))
    if booking is not None:
        raise ServiceError("COMPUTER_HAS_BOOKINGS", "Resolve active and upcoming bookings before changing this computer.", 409)


async def _staff_club_ids(session: AsyncSession, staff: User) -> list[uuid.UUID]:
    return list(await session.scalars(select(StaffAssignment.club_id).where(StaffAssignment.staff_user_id == staff.id)))


async def _staff_booking(session: AsyncSession, staff: User, booking_id: uuid.UUID, lock: bool = False) -> Booking:
    club_ids = await _staff_club_ids(session, staff)
    if not club_ids:
        raise ServiceError("FORBIDDEN", "You are not assigned to a club.", 403)
    query = (
        select(Booking)
        .join(Computer, Booking.computer_id == Computer.id)
        .where(Booking.id == booking_id, Computer.club_id.in_(club_ids))
    )
    if lock:
        query = query.with_for_update(of=Booking)
    booking = await session.scalar(query)
    if booking is None:
        raise ServiceError("BOOKING_NOT_FOUND", "Booking not found in your assigned clubs.", 404)
    await session.refresh(booking, attribute_names=["user", "computer"])
    return booking


def _staff_booking_response(booking: Booking) -> StaffBookingResponse:
    return StaffBookingResponse(
        id=booking.id,
        club_id=booking.computer.club_id,
        club_name=booking.computer.club.name,
        customer_name=booking.user.full_name if booking.user else booking.guest_name or "Guest",
        customer_email=booking.user.email if booking.user else None,
        source=booking.source,
        computer_id=booking.computer_id,
        computer_name=booking.computer.name,
        start_time=booking.start_time,
        end_time=booking.end_time,
        status=booking.status,
        total_price=booking.total_price,
    )


async def owner_dashboard(session: AsyncSession, owner: User) -> OwnerDashboard:
    clubs = list(
        await session.scalars(
            select(Club).where(Club.owner_id == owner.id).options(selectinload(Club.computers)).order_by(Club.name)
        )
    )
    today = _today_start()
    metrics: list[OwnerClubMetric] = []
    for club in clubs:
        computer_count = len(club.computers)
        active_count = sum(computer.is_active for computer in club.computers)
        available_count = sum(computer.is_active and computer.status == ComputerStatus.AVAILABLE for computer in club.computers)
        maintenance_count = sum(computer.status == ComputerStatus.MAINTENANCE for computer in club.computers)
        booking_rows = await session.execute(
            select(Booking.status, Booking.total_price)
            .join(Computer, Booking.computer_id == Computer.id)
            .where(Computer.club_id == club.id, Booking.start_time >= today, Booking.start_time < _today_end())
        )
        rows = list(booking_rows)
        metrics.append(
            OwnerClubMetric(
                id=club.id,
                name=club.name,
                city=club.city,
                is_active=club.is_active,
                computers=computer_count,
                active_computers=active_count,
                available_computers=available_count,
                bookings_today=len(rows),
                revenue_today=sum((price for status, price in rows if status in REVENUE_BOOKING_STATUSES), Decimal("0")),
            )
        )
    return OwnerDashboard(
        club_count=len(clubs),
        computer_count=sum(metric.computers for metric in metrics),
        active_computers=sum(metric.active_computers for metric in metrics),
        maintenance_computers=sum(sum(computer.status == ComputerStatus.MAINTENANCE for computer in club.computers) for club in clubs),
        bookings_today=sum(metric.bookings_today for metric in metrics),
        revenue_today=sum((metric.revenue_today for metric in metrics), Decimal("0")),
        clubs=metrics,
    )


async def owner_clubs(session: AsyncSession, owner: User) -> list[Club]:
    return list(
        await session.scalars(
            select(Club).where(Club.owner_id == owner.id).options(selectinload(Club.computers), selectinload(Club.tariffs)).order_by(Club.name)
        )
    )


async def create_club(session: AsyncSession, owner: User, payload: ClubCreate) -> Club:
    club = Club(owner_id=owner.id, **payload.model_dump())
    session.add(club)
    await session.commit()
    await session.refresh(club)
    return club


async def update_club(session: AsyncSession, owner: User, club_id: uuid.UUID, payload: ClubUpdate) -> Club:
    club = await _owned_club(session, owner, club_id, lock=True)
    changes = payload.model_dump(exclude_unset=True)
    if "timezone" in changes and changes["timezone"] != club.timezone:
        upcoming = await session.scalar(
            select(Booking.id).join(Computer, Booking.computer_id == Computer.id).where(
                Computer.club_id == club.id,
                Booking.status.in_(ACTIVE_BOOKING_STATUSES),
                (Booking.status == BookingStatus.ACTIVE) | (Booking.end_time > datetime.now(timezone.utc)),
            )
        )
        if upcoming is not None:
            raise ServiceError("CLUB_HAS_BOOKINGS", "Resolve active and upcoming bookings before changing the club time zone.", 409)
    for key, value in changes.items():
        setattr(club, key, value)
    await session.commit()
    await session.refresh(club)
    return club


async def create_computer(session: AsyncSession, owner: User, club_id: uuid.UUID, payload: ComputerCreate) -> Computer:
    await _owned_club(session, owner, club_id)
    computer = Computer(club_id=club_id, **payload.model_dump())
    session.add(computer)
    await session.commit()
    await session.refresh(computer)
    return computer


async def update_computer(session: AsyncSession, owner: User, computer_id: uuid.UUID, payload: ComputerUpdate) -> Computer:
    computer = await _owned_computer(session, owner, computer_id, lock=True)
    await _ensure_no_live_booking(session, computer.id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(computer, key, value)
    await session.commit()
    await session.refresh(computer)
    return computer


async def owner_update_computer_status(
    session: AsyncSession, owner: User, computer_id: uuid.UUID, payload: ComputerStatusUpdate
) -> Computer:
    computer = await _owned_computer(session, owner, computer_id, lock=True)
    if payload.status == ComputerStatus.OCCUPIED:
        raise ServiceError("INVALID_COMPUTER_STATUS", "Computer occupancy is derived from its active booking.", 422)
    if payload.status in (ComputerStatus.MAINTENANCE, ComputerStatus.DISABLED):
        await _ensure_no_live_booking(session, computer.id)
    else:
        await _ensure_no_active_session(session, computer.id)
    computer.status = payload.status
    await session.commit()
    await session.refresh(computer)
    return computer


async def create_tariff(session: AsyncSession, owner: User, club_id: uuid.UUID, payload: TariffCreate) -> Tariff:
    await _owned_club(session, owner, club_id)
    tariff = Tariff(club_id=club_id, **payload.model_dump())
    session.add(tariff)
    await session.commit()
    await session.refresh(tariff)
    return tariff


async def update_tariff(session: AsyncSession, owner: User, tariff_id: uuid.UUID, payload: TariffUpdate) -> Tariff:
    tariff = await _owned_tariff(session, owner, tariff_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(tariff, key, value)
    await session.commit()
    await session.refresh(tariff)
    return tariff


async def assign_staff(session: AsyncSession, owner: User, club_id: uuid.UUID, payload: StaffAssignmentCreate) -> StaffAssignment:
    await _owned_club(session, owner, club_id)
    staff = await session.scalar(select(User).where(func.lower(User.email) == str(payload.email).lower()))
    if staff is None or staff.role not in (UserRole.USER, UserRole.STAFF) or not staff.is_active:
        raise ServiceError("STAFF_ACCOUNT_INVALID", "Select an active USER or STAFF account by email.", 422)
    existing = await session.scalar(
        select(StaffAssignment).where(StaffAssignment.staff_user_id == staff.id, StaffAssignment.club_id == club_id)
    )
    if existing is not None:
        raise ServiceError("STAFF_ALREADY_ASSIGNED", "This staff member is already assigned to the club.", 409)
    staff.role = UserRole.STAFF
    assignment = StaffAssignment(staff_user_id=staff.id, club_id=club_id, assigned_by_user_id=owner.id)
    session.add(assignment)
    await session.commit()
    await session.refresh(assignment)
    return assignment


async def remove_staff(session: AsyncSession, owner: User, club_id: uuid.UUID, staff_user_id: uuid.UUID) -> None:
    await _owned_club(session, owner, club_id)
    assignment = await session.scalar(
        select(StaffAssignment).where(StaffAssignment.staff_user_id == staff_user_id, StaffAssignment.club_id == club_id)
    )
    if assignment is None:
        raise ServiceError("STAFF_ASSIGNMENT_NOT_FOUND", "Staff assignment not found.", 404)
    await session.delete(assignment)
    remaining = await session.scalar(
        select(func.count()).select_from(StaffAssignment).where(StaffAssignment.staff_user_id == staff_user_id, StaffAssignment.id != assignment.id)
    )
    staff = await session.get(User, staff_user_id)
    if staff is not None and remaining == 0 and staff.role == UserRole.STAFF:
        staff.role = UserRole.USER
    await session.commit()


async def list_club_staff(session: AsyncSession, owner: User, club_id: uuid.UUID) -> list[StaffMemberResponse]:
    await _owned_club(session, owner, club_id)
    rows = await session.execute(
        select(User.id, User.email, User.username, User.full_name, StaffAssignment.assigned_at)
        .join(StaffAssignment, StaffAssignment.staff_user_id == User.id)
        .where(StaffAssignment.club_id == club_id)
        .order_by(User.full_name)
    )
    return [StaffMemberResponse(**row._asdict()) for row in rows]


async def owner_bookings(session: AsyncSession, owner: User) -> list[StaffBookingResponse]:
    rows = await session.scalars(
        select(Booking)
        .join(Computer, Booking.computer_id == Computer.id)
        .join(Club, Computer.club_id == Club.id)
        .where(Club.owner_id == owner.id)
        .options(joinedload(Booking.user), joinedload(Booking.computer).joinedload(Computer.club))
        .order_by(Booking.start_time.desc())
        .limit(250)
    )
    return [_staff_booking_response(booking) for booking in rows]


async def staff_dashboard(session: AsyncSession, staff: User) -> StaffDashboard:
    club_ids = await _staff_club_ids(session, staff)
    if not club_ids:
        return StaffDashboard(assigned_clubs=0, bookings_today=0, upcoming_bookings=0, active_sessions=0, bookings=[])
    today = _today_start()
    tomorrow = _today_end()
    now = datetime.now(timezone.utc)
    rows = list(
        await session.scalars(
            select(Booking)
            .join(Computer, Booking.computer_id == Computer.id)
            .where(Computer.club_id.in_(club_ids), Booking.start_time >= today, Booking.start_time < tomorrow)
            .options(joinedload(Booking.user), joinedload(Booking.computer).joinedload(Computer.club))
            .order_by(Booking.start_time)
            .limit(250)
        )
    )
    queue = list(
        await session.scalars(
            select(Booking)
        .join(Computer, Booking.computer_id == Computer.id)
                .where(Computer.club_id.in_(club_ids), ((Booking.end_time >= now) | (Booking.status == BookingStatus.ACTIVE)), Booking.status.in_(ACTIVE_BOOKING_STATUSES))
                .options(joinedload(Booking.user), joinedload(Booking.computer).joinedload(Computer.club))
                .order_by(Booking.start_time)
                .limit(250)
            )
        )
    return StaffDashboard(
        assigned_clubs=len(club_ids),
        bookings_today=len(rows),
        upcoming_bookings=sum(booking.status in (BookingStatus.PENDING, BookingStatus.CONFIRMED) for booking in queue),
        active_sessions=sum(booking.status == BookingStatus.ACTIVE for booking in queue),
        bookings=[_staff_booking_response(booking) for booking in queue],
    )


async def staff_bookings(session: AsyncSession, staff: User) -> list[StaffBookingResponse]:
    club_ids = await _staff_club_ids(session, staff)
    rows = await session.scalars(
        select(Booking)
        .join(Computer, Booking.computer_id == Computer.id)
        .where(Computer.club_id.in_(club_ids), ((Booking.end_time >= datetime.now(timezone.utc)) | (Booking.status == BookingStatus.ACTIVE)), Booking.status.in_(ACTIVE_BOOKING_STATUSES))
        .options(joinedload(Booking.user), joinedload(Booking.computer).joinedload(Computer.club))
        .order_by(Booking.start_time.desc())
        .limit(250)
    )
    return [_staff_booking_response(booking) for booking in rows]


async def staff_computers(session: AsyncSession, staff: User) -> list[StaffComputerResponse]:
    club_ids = await _staff_club_ids(session, staff)
    rows = await session.execute(
        select(Computer, Club.name).join(Club, Computer.club_id == Club.id).where(Computer.club_id.in_(club_ids)).order_by(Club.name, Computer.name)
    )
    response: list[StaffComputerResponse] = []
    for computer, club_name in rows:
        computer_data = ComputerResponse.model_validate(computer, from_attributes=True).model_dump()
        response.append(StaffComputerResponse(**computer_data, club_id=computer.club_id, club_name=club_name))
    return response


async def verify_staff_qr(session: AsyncSession, staff: User, qr_token: str) -> StaffBookingResponse:
    booking = await session.scalar(
        select(Booking)
        .join(Computer, Booking.computer_id == Computer.id)
        .where(Booking.qr_token == qr_token)
        .options(joinedload(Booking.user), joinedload(Booking.computer).joinedload(Computer.club))
    )
    if booking is None:
        raise ServiceError("BOOKING_NOT_FOUND", "No booking matches this QR code.", 404)
    club_ids = await _staff_club_ids(session, staff)
    if booking.computer.club_id not in club_ids:
        raise ServiceError("FORBIDDEN", "This booking belongs to a club outside your assignment.", 403)
    if booking.status not in (BookingStatus.PENDING, BookingStatus.CONFIRMED, BookingStatus.ACTIVE):
        raise ServiceError("BOOKING_NOT_ACTIVE", "This QR code is for a closed or cancelled booking.", 409)
    return _staff_booking_response(booking)


async def staff_transition_booking(session: AsyncSession, staff: User, booking_id: uuid.UUID, target: BookingStatus) -> StaffBookingResponse:
    if target not in (BookingStatus.ACTIVE, BookingStatus.COMPLETED):
        raise ServiceError("INVALID_BOOKING_TRANSITION", "Unsupported staff session action.", 422)
    return await staff_session_action(session, staff, booking_id, "start" if target == BookingStatus.ACTIVE else "end")


async def staff_session_action(
    session: AsyncSession, staff: User, booking_id: uuid.UUID, action: str, extension: SessionExtend | None = None,
) -> StaffBookingResponse:
    club_ids = await _staff_club_ids(session, staff)
    booking_computer_id = await session.scalar(
        select(Booking.computer_id).join(Computer, Booking.computer_id == Computer.id)
        .where(Booking.id == booking_id, Computer.club_id.in_(club_ids))
    )
    if booking_computer_id is None:
        raise ServiceError("BOOKING_NOT_FOUND", "Booking not found in your assigned clubs.", 404)
    computer = await session.scalar(select(Computer).where(Computer.id == booking_computer_id).with_for_update())
    booking = await _staff_booking(session, staff, booking_id, lock=True)
    if action == "start":
        await bookings.start_session(session, booking, staff, computer)
    elif action == "extend" and extension is not None:
        await bookings.extend_session(session, booking, extension)
    elif action == "end":
        await bookings.end_session(session, booking, staff, computer)
    else:
        raise ServiceError("INVALID_SESSION_ACTION", "Unsupported session action.", 422)
    refreshed = await session.scalar(
        select(Booking).where(Booking.id == booking_id)
        .options(joinedload(Booking.user), joinedload(Booking.computer).joinedload(Computer.club))
        .execution_options(populate_existing=True)
    )
    return _staff_booking_response(refreshed)


async def staff_booking_details(session: AsyncSession, staff: User, booking_id: uuid.UUID) -> StaffBookingResponse:
    booking = await _staff_booking(session, staff, booking_id)
    await session.refresh(booking.computer, attribute_names=["club"])
    return _staff_booking_response(booking)


async def staff_update_computer_status(
    session: AsyncSession, staff: User, computer_id: uuid.UUID, payload: ComputerStatusUpdate
) -> Computer:
    club_ids = await _staff_club_ids(session, staff)
    computer = await session.scalar(select(Computer).where(Computer.id == computer_id, Computer.club_id.in_(club_ids)).with_for_update())
    if computer is None:
        raise ServiceError("COMPUTER_NOT_FOUND", "Computer not found in your assigned clubs.", 404)
    if payload.status == ComputerStatus.OCCUPIED:
        raise ServiceError("INVALID_COMPUTER_STATUS", "Computer occupancy is derived from its active booking.", 422)
    if payload.status in (ComputerStatus.MAINTENANCE, ComputerStatus.DISABLED):
        await _ensure_no_live_booking(session, computer.id)
    else:
        await _ensure_no_active_session(session, computer.id)
    computer.status = payload.status
    await session.commit()
    await session.refresh(computer)
    return computer


async def admin_dashboard(session: AsyncSession) -> AdminDashboard:
    today = _today_start()
    tomorrow = _today_end()
    result = await session.execute(
        select(
            select(func.count()).select_from(User).scalar_subquery(),
            select(func.count()).select_from(User).where(User.is_active.is_(True)).scalar_subquery(),
            select(func.count()).select_from(Club).scalar_subquery(),
            select(func.count()).select_from(Club).where(Club.is_active.is_(True)).scalar_subquery(),
            select(func.count()).select_from(Computer).scalar_subquery(),
            select(func.count()).select_from(Computer).where(Computer.is_active.is_(True)).scalar_subquery(),
            select(func.count()).select_from(Booking).where(Booking.start_time >= today, Booking.start_time < tomorrow).scalar_subquery(),
            select(func.coalesce(func.sum(Booking.total_price), 0)).where(
                Booking.start_time >= today, Booking.start_time < tomorrow, Booking.status.in_(REVENUE_BOOKING_STATUSES)
            ).scalar_subquery(),
        )
    )
    users, active_users, clubs, active_clubs, computers, active_computers, bookings_today, revenue = result.one()
    return AdminDashboard(
        users=users,
        active_users=active_users,
        clubs=clubs,
        active_clubs=active_clubs,
        computers=computers,
        active_computers=active_computers,
        bookings_today=bookings_today,
        revenue_today=revenue,
    )


async def admin_users(session: AsyncSession, page: int = 1, page_size: int = 50) -> list[User]:
    return list(
        await session.scalars(
            select(User).order_by(User.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        )
    )


async def admin_update_user(session: AsyncSession, user_id: uuid.UUID, payload: UserActiveUpdate) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise ServiceError("USER_NOT_FOUND", "User not found.", 404)
    if user.role == UserRole.ADMIN and not payload.is_active:
        active_admins = await session.scalar(select(func.count()).select_from(User).where(User.role == UserRole.ADMIN, User.is_active.is_(True)))
        if active_admins <= 1:
            raise ServiceError("LAST_ADMIN", "The last active administrator cannot be suspended.", 409)
    user.is_active = payload.is_active
    await session.commit()
    await session.refresh(user)
    return user


async def admin_clubs(session: AsyncSession) -> list[Club]:
    return list(await session.scalars(select(Club).options(selectinload(Club.computers), selectinload(Club.tariffs)).order_by(Club.name).limit(500)))


async def admin_update_club(session: AsyncSession, club_id: uuid.UUID, payload: ClubUpdate) -> Club:
    club = await session.get(Club, club_id)
    if club is None:
        raise ServiceError("CLUB_NOT_FOUND", "Club not found.", 404)
    if payload.model_fields_set - {"is_active"}:
        raise ServiceError("ADMIN_STATUS_ONLY", "This endpoint only changes whether a club is active.", 422)
    club.is_active = payload.is_active if payload.is_active is not None else club.is_active
    await session.commit()
    await session.refresh(club)
    return club


async def admin_update_computer_status(
    session: AsyncSession, computer_id: uuid.UUID, payload: ComputerStatusUpdate
) -> Computer:
    computer = await session.scalar(select(Computer).where(Computer.id == computer_id).with_for_update())
    if computer is None:
        raise ServiceError("COMPUTER_NOT_FOUND", "Computer not found.", 404)
    if payload.status == ComputerStatus.OCCUPIED:
        raise ServiceError("INVALID_COMPUTER_STATUS", "Computer occupancy is derived from its active booking.", 422)
    if payload.status in (ComputerStatus.MAINTENANCE, ComputerStatus.DISABLED):
        await _ensure_no_live_booking(session, computer.id)
    else:
        await _ensure_no_active_session(session, computer.id)
    computer.status = payload.status
    await session.commit()
    await session.refresh(computer)
    return computer


async def admin_update_booking_status(
    session: AsyncSession, admin: User, booking_id: uuid.UUID, payload: AdminBookingStatusUpdate
) -> StaffBookingResponse:
    computer_id = await session.scalar(select(Booking.computer_id).where(Booking.id == booking_id))
    if computer_id is None:
        raise ServiceError("BOOKING_NOT_FOUND", "Booking not found.", 404)
    computer = await session.scalar(select(Computer).where(Computer.id == computer_id).with_for_update())
    booking = await session.scalar(select(Booking).where(Booking.id == booking_id).with_for_update())
    if booking is None:
        raise ServiceError("BOOKING_NOT_FOUND", "Booking not found.", 404)
    if payload.status == BookingStatus.ACTIVE:
        await bookings.start_session(session, booking, admin, computer)
    elif payload.status == BookingStatus.COMPLETED:
        await bookings.end_session(session, booking, admin, computer)
    else:
        transition_booking(booking, payload.status)
        await session.commit()
    await session.refresh(booking, attribute_names=["user", "computer"])
    await session.refresh(booking.computer, attribute_names=["club"])
    return _staff_booking_response(booking)


async def admin_bookings(session: AsyncSession) -> list[StaffBookingResponse]:
    rows = await session.scalars(
        select(Booking)
        .options(joinedload(Booking.user), joinedload(Booking.computer).joinedload(Computer.club))
        .order_by(Booking.start_time.desc())
        .limit(500)
    )
    return [_staff_booking_response(booking) for booking in rows]
