import uuid
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.models import (
    AuditLog,
    Booking,
    BookingStatus,
    Club,
    Computer,
    ComputerStatus,
    MembershipPlan,
    PromoCode,
    StaffAssignment,
    StaffShift,
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
    MembershipPlanCreate,
    MembershipPlanStatusUpdate,
    OwnerClubMetric,
    OwnerDashboard,
    OwnerReport,
    OwnerReportComputer,
    OwnerReportDay,
    OwnerReportHour,
    PromoCodeCreate,
    PromoCodeStatusUpdate,
    StaffBookingResponse,
    StaffDashboard,
    StaffComputerResponse,
    StaffAssignmentCreate,
    StaffMemberResponse,
    StaffShiftCreate,
    StaffShiftResponse,
    SessionExtend,
    TariffCreate,
    TariffUpdate,
    UserActiveUpdate,
    UserAdminResponse,
)
from app.services.errors import ServiceError
from app.services.audit import record_audit
from app.services import bookings
from app.services import payments
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


async def owner_report(session: AsyncSession, owner: User, start_date: date, end_date: date) -> OwnerReport:
    span = (end_date - start_date).days
    if span < 0 or span > 90:
        raise ServiceError("INVALID_REPORT_RANGE", "Choose a date range of up to 90 days.", 422)

    clubs = list(await session.scalars(select(Club).where(Club.owner_id == owner.id)))
    daily_values: dict[date, list[Decimal | int]] = {}
    current_day = start_date
    while current_day <= end_date:
        daily_values[current_day] = [0, Decimal("0")]
        current_day += timedelta(days=1)
    hourly_values = [0] * 24
    computer_values: dict[uuid.UUID, list[Decimal | int | str]] = {}
    total_bookings = 0
    total_value = Decimal("0")

    for club in clubs:
        zone = ZoneInfo(club.timezone)
        interval_start = datetime.combine(start_date, time.min, tzinfo=zone).astimezone(timezone.utc)
        interval_end = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=zone).astimezone(timezone.utc)
        local_start = func.timezone(club.timezone, Booking.start_time)
        where = (
            Computer.club_id == club.id,
            Booking.start_time >= interval_start,
            Booking.start_time < interval_end,
        )
        value_expression = func.coalesce(
            func.sum(case((Booking.status.in_(REVENUE_BOOKING_STATUSES), Booking.total_price), else_=Decimal("0"))),
            Decimal("0"),
        )

        daily_rows = await session.execute(
            select(func.date(local_start), func.count(Booking.id), value_expression)
            .select_from(Booking).join(Computer, Booking.computer_id == Computer.id).where(*where).group_by(func.date(local_start))
        )
        for bucket_date, count, value in daily_rows:
            metrics = daily_values[bucket_date]
            metrics[0] += count
            metrics[1] += value
            total_bookings += count
            total_value += value

        hourly_rows = await session.execute(
            select(func.extract("hour", local_start), func.count(Booking.id))
            .select_from(Booking).join(Computer, Booking.computer_id == Computer.id).where(*where).group_by(func.extract("hour", local_start))
        )
        for hour, count in hourly_rows:
            hourly_values[int(hour)] += count

        computer_rows = await session.execute(
            select(Computer.id, Computer.name, func.count(Booking.id), value_expression)
            .select_from(Booking).join(Computer, Booking.computer_id == Computer.id).where(*where)
            .group_by(Computer.id, Computer.name).order_by(Computer.name)
        )
        for computer_id, computer_name, count, value in computer_rows:
            metrics = computer_values.setdefault(computer_id, [computer_name, 0, Decimal("0")])
            metrics[1] += count
            metrics[2] += value

    return OwnerReport(
        start_date=start_date,
        end_date=end_date,
        bookings=total_bookings,
        booking_value=total_value,
        daily=[OwnerReportDay(date=day, bookings=int(values[0]), booking_value=values[1]) for day, values in daily_values.items()],
        hourly=[OwnerReportHour(hour=hour, bookings=count) for hour, count in enumerate(hourly_values)],
        computers=[
            OwnerReportComputer(computer_id=computer_id, computer_name=str(values[0]), bookings=int(values[1]), booking_value=values[2])
            for computer_id, values in computer_values.items()
        ],
    )


async def owner_audit(session: AsyncSession, owner: User, limit: int) -> list[AuditLog]:
    club_ids = select(Club.id).where(Club.owner_id == owner.id)
    return list(await session.scalars(
        select(AuditLog).where(AuditLog.club_id.in_(club_ids)).order_by(AuditLog.created_at.desc()).limit(limit)
    ))


async def owner_promo_codes(session: AsyncSession, owner: User) -> list[PromoCode]:
    club_ids = select(Club.id).where(Club.owner_id == owner.id)
    return list(await session.scalars(
        select(PromoCode).where(PromoCode.club_id.in_(club_ids)).order_by(PromoCode.created_at.desc()).limit(200)
    ))


async def create_promo_code(session: AsyncSession, owner: User, club_id: uuid.UUID, payload: PromoCodeCreate) -> PromoCode:
    club = await _owned_club(session, owner, club_id, lock=True)
    promo = PromoCode(club_id=club.id, **payload.model_dump())
    session.add(promo)
    try:
        await session.flush()
        record_audit(
            session, actor_id=owner.id, action="promo_code.created", entity_type="promo_code", entity_id=promo.id,
            club_id=club.id, details={"code": promo.code, "discount_type": promo.discount_type},
        )
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise ServiceError("PROMO_CODE_EXISTS", "A promo code with this name already exists for this club.", 409) from error
    await session.refresh(promo)
    return promo


async def set_promo_code_status(
    session: AsyncSession, owner: User, promo_id: uuid.UUID, payload: PromoCodeStatusUpdate,
) -> PromoCode:
    promo = await session.scalar(
        select(PromoCode).join(Club).where(PromoCode.id == promo_id, Club.owner_id == owner.id).with_for_update(of=PromoCode)
    )
    if promo is None:
        raise ServiceError("PROMO_CODE_NOT_FOUND", "Promo code not found in your clubs.", 404)
    promo.is_active = payload.is_active
    record_audit(
        session, actor_id=owner.id, action="promo_code.status_changed", entity_type="promo_code", entity_id=promo.id,
        club_id=promo.club_id, details={"is_active": promo.is_active},
    )
    await session.commit()
    await session.refresh(promo)
    return promo


async def owner_membership_plans(session: AsyncSession, owner: User) -> list[MembershipPlan]:
    club_ids = select(Club.id).where(Club.owner_id == owner.id)
    return list(await session.scalars(
        select(MembershipPlan).where(MembershipPlan.club_id.in_(club_ids)).order_by(MembershipPlan.created_at.desc()).limit(200)
    ))


async def create_membership_plan(
    session: AsyncSession, owner: User, club_id: uuid.UUID, payload: MembershipPlanCreate,
) -> MembershipPlan:
    club = await _owned_club(session, owner, club_id, lock=True)
    plan = MembershipPlan(club_id=club.id, **payload.model_dump())
    session.add(plan)
    await session.flush()
    record_audit(
        session, actor_id=owner.id, action="membership_plan.created", entity_type="membership_plan", entity_id=plan.id,
        club_id=club.id, details={"hours": plan.hours, "price": str(plan.price)},
    )
    await session.commit()
    await session.refresh(plan)
    return plan


async def set_membership_plan_status(
    session: AsyncSession, owner: User, plan_id: uuid.UUID, payload: MembershipPlanStatusUpdate,
) -> MembershipPlan:
    plan = await session.scalar(
        select(MembershipPlan).join(Club).where(MembershipPlan.id == plan_id, Club.owner_id == owner.id).with_for_update(of=MembershipPlan)
    )
    if plan is None:
        raise ServiceError("MEMBERSHIP_PLAN_NOT_FOUND", "Membership plan not found in your clubs.", 404)
    plan.is_active = payload.is_active
    record_audit(
        session, actor_id=owner.id, action="membership_plan.status_changed", entity_type="membership_plan", entity_id=plan.id,
        club_id=plan.club_id, details={"is_active": plan.is_active},
    )
    await session.commit()
    await session.refresh(plan)
    return plan


async def admin_audit(session: AsyncSession, limit: int) -> list[AuditLog]:
    return list(await session.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)))


async def owner_clubs(session: AsyncSession, owner: User) -> list[Club]:
    return list(
        await session.scalars(
            select(Club).where(Club.owner_id == owner.id).options(selectinload(Club.computers), selectinload(Club.tariffs)).order_by(Club.name)
        )
    )


async def create_club(session: AsyncSession, owner: User, payload: ClubCreate) -> Club:
    club = Club(owner_id=owner.id, **payload.model_dump())
    session.add(club)
    await session.flush()
    record_audit(session, actor_id=owner.id, action="club.created", entity_type="club", entity_id=club.id, club_id=club.id)
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
    if changes:
        record_audit(session, actor_id=owner.id, action="club.updated", entity_type="club", entity_id=club.id, club_id=club.id,
                     details={"fields": sorted(changes)})
    await session.commit()
    await session.refresh(club)
    return club


async def create_computer(session: AsyncSession, owner: User, club_id: uuid.UUID, payload: ComputerCreate) -> Computer:
    await _owned_club(session, owner, club_id)
    computer = Computer(club_id=club_id, **payload.model_dump())
    session.add(computer)
    await session.flush()
    record_audit(session, actor_id=owner.id, action="computer.created", entity_type="computer", entity_id=computer.id, club_id=club_id)
    await session.commit()
    await session.refresh(computer)
    return computer


async def update_computer(session: AsyncSession, owner: User, computer_id: uuid.UUID, payload: ComputerUpdate) -> Computer:
    computer = await _owned_computer(session, owner, computer_id, lock=True)
    await _ensure_no_live_booking(session, computer.id)
    changes = payload.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(computer, key, value)
    if changes:
        record_audit(session, actor_id=owner.id, action="computer.updated", entity_type="computer", entity_id=computer.id,
                     club_id=computer.club_id, details={"fields": sorted(changes)})
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
    previous_status = computer.status
    computer.status = payload.status
    record_audit(session, actor_id=owner.id, action="computer.status_changed", entity_type="computer", entity_id=computer.id,
                 club_id=computer.club_id, details={"from": previous_status.value, "to": payload.status.value})
    await session.commit()
    await session.refresh(computer)
    return computer


async def create_tariff(session: AsyncSession, owner: User, club_id: uuid.UUID, payload: TariffCreate) -> Tariff:
    await _owned_club(session, owner, club_id)
    tariff = Tariff(club_id=club_id, **payload.model_dump())
    session.add(tariff)
    await session.flush()
    record_audit(session, actor_id=owner.id, action="tariff.created", entity_type="tariff", entity_id=tariff.id, club_id=club_id)
    await session.commit()
    await session.refresh(tariff)
    return tariff


async def update_tariff(session: AsyncSession, owner: User, tariff_id: uuid.UUID, payload: TariffUpdate) -> Tariff:
    tariff = await _owned_tariff(session, owner, tariff_id)
    changes = payload.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(tariff, key, value)
    if changes:
        record_audit(session, actor_id=owner.id, action="tariff.updated", entity_type="tariff", entity_id=tariff.id,
                     club_id=tariff.club_id, details={"fields": sorted(changes)})
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
    await session.flush()
    record_audit(session, actor_id=owner.id, action="staff.assigned", entity_type="staff_assignment", entity_id=assignment.id,
                 club_id=club_id, details={"staff_user_id": str(staff.id)})
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
    record_audit(session, actor_id=owner.id, action="staff.unassigned", entity_type="staff_assignment", entity_id=assignment.id,
                 club_id=club_id, details={"staff_user_id": str(staff_user_id)})
    await session.delete(assignment)
    remaining = await session.scalar(
        select(func.count()).select_from(StaffAssignment).where(StaffAssignment.staff_user_id == staff_user_id, StaffAssignment.id != assignment.id)
    )
    staff = await session.get(User, staff_user_id)
    if staff is not None and remaining == 0 and staff.role == UserRole.STAFF:
        staff.role = UserRole.USER
    await session.commit()


async def create_staff_shift(session: AsyncSession, owner: User, club_id: uuid.UUID, payload: StaffShiftCreate) -> StaffShift:
    club = await _owned_club(session, owner, club_id)
    now = datetime.now(timezone.utc)
    if payload.start_time <= now:
        raise ServiceError("SHIFT_IN_PAST", "A shift must start in the future.", 422)
    staff = await session.scalar(
        select(User).join(StaffAssignment, StaffAssignment.staff_user_id == User.id)
        .where(StaffAssignment.club_id == club.id, func.lower(User.email) == str(payload.staff_email).lower(), User.is_active.is_(True))
    )
    if staff is None:
        raise ServiceError("STAFF_NOT_ASSIGNED", "Assign this staff member to the club before scheduling a shift.", 422)
    shift = StaffShift(club_id=club.id, staff_user_id=staff.id, created_by_user_id=owner.id,
                       start_time=payload.start_time, end_time=payload.end_time)
    session.add(shift)
    try:
        await session.flush()
        record_audit(session, actor_id=owner.id, action="staff.shift_created", entity_type="staff_shift", entity_id=shift.id,
                     club_id=club.id, details={"staff_user_id": str(staff.id), "start_time": payload.start_time.isoformat(), "end_time": payload.end_time.isoformat()})
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise ServiceError("STAFF_SHIFT_CONFLICT", "This staff member already has an overlapping shift.", 409) from error
    return await session.scalar(
        select(StaffShift).where(StaffShift.id == shift.id).options(joinedload(StaffShift.club), joinedload(StaffShift.staff_user))
    )


async def owner_staff_shifts(session: AsyncSession, owner: User, limit: int = 100) -> list[StaffShift]:
    return list(await session.scalars(
        select(StaffShift).join(Club, StaffShift.club_id == Club.id)
        .where(Club.owner_id == owner.id)
        .options(joinedload(StaffShift.club), joinedload(StaffShift.staff_user))
        .order_by(StaffShift.start_time.desc()).limit(limit)
    ))


async def staff_shifts(session: AsyncSession, staff: User, limit: int = 100) -> list[StaffShift]:
    club_ids = await _staff_club_ids(session, staff)
    if not club_ids:
        return []
    return list(await session.scalars(
        select(StaffShift).where(StaffShift.staff_user_id == staff.id, StaffShift.club_id.in_(club_ids))
        .options(joinedload(StaffShift.club), joinedload(StaffShift.staff_user))
        .order_by(StaffShift.start_time).limit(limit)
    ))


async def delete_staff_shift(session: AsyncSession, owner: User, shift_id: uuid.UUID) -> None:
    shift = await session.scalar(
        select(StaffShift).join(Club, StaffShift.club_id == Club.id)
        .where(StaffShift.id == shift_id, Club.owner_id == owner.id).with_for_update(of=StaffShift)
    )
    if shift is None:
        raise ServiceError("STAFF_SHIFT_NOT_FOUND", "Shift not found in your clubs.", 404)
    record_audit(session, actor_id=owner.id, action="staff.shift_cancelled", entity_type="staff_shift", entity_id=shift.id, club_id=shift.club_id)
    await session.delete(shift)
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
        await bookings.extend_session(session, booking, extension, staff)
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


async def admin_update_user(session: AsyncSession, admin: User, user_id: uuid.UUID, payload: UserActiveUpdate) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise ServiceError("USER_NOT_FOUND", "User not found.", 404)
    if user.role == UserRole.ADMIN and not payload.is_active:
        active_admins = await session.scalar(select(func.count()).select_from(User).where(User.role == UserRole.ADMIN, User.is_active.is_(True)))
        if active_admins <= 1:
            raise ServiceError("LAST_ADMIN", "The last active administrator cannot be suspended.", 409)
    was_active = user.is_active
    user.is_active = payload.is_active
    record_audit(session, actor_id=admin.id, action="user.status_changed", entity_type="user", entity_id=user.id,
                 details={"from": was_active, "to": user.is_active})
    await session.commit()
    await session.refresh(user)
    return user


async def admin_clubs(session: AsyncSession) -> list[Club]:
    return list(await session.scalars(select(Club).options(selectinload(Club.computers), selectinload(Club.tariffs)).order_by(Club.name).limit(500)))


async def admin_update_club(session: AsyncSession, admin: User, club_id: uuid.UUID, payload: ClubUpdate) -> Club:
    club = await session.get(Club, club_id)
    if club is None:
        raise ServiceError("CLUB_NOT_FOUND", "Club not found.", 404)
    if payload.model_fields_set - {"is_active"}:
        raise ServiceError("ADMIN_STATUS_ONLY", "This endpoint only changes whether a club is active.", 422)
    was_active = club.is_active
    club.is_active = payload.is_active if payload.is_active is not None else club.is_active
    record_audit(session, actor_id=admin.id, action="club.status_changed", entity_type="club", entity_id=club.id, club_id=club.id,
                 details={"from": was_active, "to": club.is_active})
    await session.commit()
    await session.refresh(club)
    return club


async def admin_update_computer_status(
    session: AsyncSession, admin: User, computer_id: uuid.UUID, payload: ComputerStatusUpdate
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
    previous_status = computer.status
    computer.status = payload.status
    record_audit(session, actor_id=admin.id, action="computer.status_changed", entity_type="computer", entity_id=computer.id,
                 club_id=computer.club_id, details={"from": previous_status.value, "to": payload.status.value})
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
        if payload.status in (BookingStatus.CANCELLED, BookingStatus.EXPIRED):
            refund_eligible = (
                payload.status == BookingStatus.CANCELLED
                and booking.start_time - datetime.now(timezone.utc) >= timedelta(hours=booking.refund_cutoff_hours)
            )
            await payments.handle_booking_cancellation(session, booking, refund_eligible=refund_eligible)
            await bookings.release_promo_quota(session, booking)
            await bookings.release_membership_credits(session, booking)
            await bookings.cancel_booking_reminders(session, booking.id)
        record_audit(session, actor_id=admin.id, action="booking.status_changed", entity_type="booking", entity_id=booking.id,
                     club_id=computer.club_id, details={"to": payload.status.value})
        transition_booking(booking, payload.status)
        if payload.status == BookingStatus.CANCELLED:
            await bookings.notify_waitlist_for_slot(
                session, club_id=computer.club_id, computer_id=computer.id,
                start_time=booking.start_time, end_time=booking.end_time,
            )
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
