import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.dependencies import get_current_user, require_roles
from app.models import AuditLog, BookingStatus, MembershipPlan, PromoCode, StaffAssignment, StaffShift, User, UserRole
from app.schemas import (
    AccessToken,
    AdminBookingStatusUpdate,
    AdminDashboard,
    AuditLogResponse,
    BookingResponse,
    ClubCreate,
    ClubResponse,
    ClubUpdate,
    ComputerCreate,
    ComputerResponse,
    ComputerStatusUpdate,
    ComputerUpdate,
    ManagedClubResponse,
    OwnerDashboard,
    OwnerReport,
    MembershipPlanCreate,
    MembershipPlanResponse,
    MembershipPlanStatusUpdate,
    PromoCodeCreate,
    PromoCodeResponse,
    PromoCodeStatusUpdate,
    QRVerifyRequest,
    StaffAssignmentCreate,
    StaffBookingResponse,
    StaffDashboard,
    StaffComputerResponse,
    StaffMemberResponse,
    StaffShiftCreate,
    StaffShiftResponse,
    SessionExtend,
    TariffCreate,
    TariffResponse,
    TariffUpdate,
    UserActiveUpdate,
    UserAdminResponse,
    WalkInCreate,
)
from app.services import bookings, role_workflows

router = APIRouter()


@router.get("/owner/dashboard", response_model=OwnerDashboard)
async def owner_dashboard(
    user: User = Depends(require_roles(UserRole.OWNER)), session: AsyncSession = Depends(get_session)
) -> OwnerDashboard:
    return await role_workflows.owner_dashboard(session, user)


@router.get("/owner/reports", response_model=OwnerReport)
async def owner_reports(
    start_date: date,
    end_date: date,
    user: User = Depends(require_roles(UserRole.OWNER)),
    session: AsyncSession = Depends(get_session),
) -> OwnerReport:
    return await role_workflows.owner_report(session, user, start_date, end_date)


@router.get("/owner/audit", response_model=list[AuditLogResponse])
async def owner_audit(
    limit: int = Query(default=100, ge=1, le=500),
    user: User = Depends(require_roles(UserRole.OWNER)),
    session: AsyncSession = Depends(get_session),
) -> list[AuditLog]:
    return await role_workflows.owner_audit(session, user, limit)


@router.get("/owner/promo-codes", response_model=list[PromoCodeResponse])
async def list_owner_promo_codes(
    user: User = Depends(require_roles(UserRole.OWNER)), session: AsyncSession = Depends(get_session),
) -> list[PromoCode]:
    return await role_workflows.owner_promo_codes(session, user)


@router.post("/owner/clubs/{club_id}/promo-codes", response_model=PromoCodeResponse, status_code=201)
async def create_owner_promo_code(
    club_id: uuid.UUID, payload: PromoCodeCreate,
    user: User = Depends(require_roles(UserRole.OWNER)), session: AsyncSession = Depends(get_session),
) -> PromoCode:
    return await role_workflows.create_promo_code(session, user, club_id, payload)


@router.patch("/owner/promo-codes/{promo_id}", response_model=PromoCodeResponse)
async def update_owner_promo_code(
    promo_id: uuid.UUID, payload: PromoCodeStatusUpdate,
    user: User = Depends(require_roles(UserRole.OWNER)), session: AsyncSession = Depends(get_session),
) -> PromoCode:
    return await role_workflows.set_promo_code_status(session, user, promo_id, payload)


@router.get("/owner/membership-plans", response_model=list[MembershipPlanResponse])
async def list_owner_membership_plans(
    user: User = Depends(require_roles(UserRole.OWNER)), session: AsyncSession = Depends(get_session),
) -> list[MembershipPlan]:
    return await role_workflows.owner_membership_plans(session, user)


@router.post("/owner/clubs/{club_id}/membership-plans", response_model=MembershipPlanResponse, status_code=201)
async def create_owner_membership_plan(
    club_id: uuid.UUID, payload: MembershipPlanCreate,
    user: User = Depends(require_roles(UserRole.OWNER)), session: AsyncSession = Depends(get_session),
) -> MembershipPlan:
    return await role_workflows.create_membership_plan(session, user, club_id, payload)


@router.patch("/owner/membership-plans/{plan_id}", response_model=MembershipPlanResponse)
async def update_owner_membership_plan(
    plan_id: uuid.UUID, payload: MembershipPlanStatusUpdate,
    user: User = Depends(require_roles(UserRole.OWNER)), session: AsyncSession = Depends(get_session),
) -> MembershipPlan:
    return await role_workflows.set_membership_plan_status(session, user, plan_id, payload)


@router.get("/owner/shifts", response_model=list[StaffShiftResponse])
async def list_owner_shifts(
    limit: int = Query(default=100, ge=1, le=500),
    user: User = Depends(require_roles(UserRole.OWNER)),
    session: AsyncSession = Depends(get_session),
) -> list[StaffShift]:
    return await role_workflows.owner_staff_shifts(session, user, limit)


@router.post("/owner/clubs/{club_id}/shifts", response_model=StaffShiftResponse, status_code=201)
async def create_owner_shift(
    club_id: uuid.UUID,
    payload: StaffShiftCreate,
    user: User = Depends(require_roles(UserRole.OWNER)),
    session: AsyncSession = Depends(get_session),
) -> StaffShift:
    return await role_workflows.create_staff_shift(session, user, club_id, payload)


@router.delete("/owner/shifts/{shift_id}", status_code=204)
async def delete_owner_shift(
    shift_id: uuid.UUID,
    user: User = Depends(require_roles(UserRole.OWNER)),
    session: AsyncSession = Depends(get_session),
) -> Response:
    await role_workflows.delete_staff_shift(session, user, shift_id)
    return Response(status_code=204)


@router.get("/owner/clubs", response_model=list[ClubResponse])
async def owner_clubs(
    user: User = Depends(require_roles(UserRole.OWNER)), session: AsyncSession = Depends(get_session)
):
    return await role_workflows.owner_clubs(session, user)


@router.post("/owner/clubs", response_model=ClubResponse, status_code=201)
async def create_owner_club(
    payload: ClubCreate,
    user: User = Depends(require_roles(UserRole.OWNER)),
    session: AsyncSession = Depends(get_session),
):
    club = await role_workflows.create_club(session, user, payload)
    await session.refresh(club, attribute_names=["computers", "tariffs"])
    return club


@router.patch("/owner/clubs/{club_id}", response_model=ClubResponse)
async def update_owner_club(
    club_id: uuid.UUID,
    payload: ClubUpdate,
    user: User = Depends(require_roles(UserRole.OWNER)),
    session: AsyncSession = Depends(get_session),
):
    return await role_workflows.update_club(session, user, club_id, payload)


@router.post("/owner/clubs/{club_id}/computers", response_model=ComputerResponse, status_code=201)
async def create_owner_computer(
    club_id: uuid.UUID,
    payload: ComputerCreate,
    user: User = Depends(require_roles(UserRole.OWNER)),
    session: AsyncSession = Depends(get_session),
):
    return await role_workflows.create_computer(session, user, club_id, payload)


@router.patch("/owner/computers/{computer_id}", response_model=ComputerResponse)
async def update_owner_computer(
    computer_id: uuid.UUID,
    payload: ComputerUpdate,
    user: User = Depends(require_roles(UserRole.OWNER)),
    session: AsyncSession = Depends(get_session),
):
    return await role_workflows.update_computer(session, user, computer_id, payload)


@router.patch("/owner/computers/{computer_id}/status", response_model=ComputerResponse)
async def set_owner_computer_status(
    computer_id: uuid.UUID,
    payload: ComputerStatusUpdate,
    user: User = Depends(require_roles(UserRole.OWNER)),
    session: AsyncSession = Depends(get_session),
):
    return await role_workflows.owner_update_computer_status(session, user, computer_id, payload)


@router.post("/owner/clubs/{club_id}/tariffs", response_model=TariffResponse, status_code=201)
async def create_owner_tariff(
    club_id: uuid.UUID,
    payload: TariffCreate,
    user: User = Depends(require_roles(UserRole.OWNER)),
    session: AsyncSession = Depends(get_session),
):
    return await role_workflows.create_tariff(session, user, club_id, payload)


@router.patch("/owner/tariffs/{tariff_id}", response_model=TariffResponse)
async def update_owner_tariff(
    tariff_id: uuid.UUID,
    payload: TariffUpdate,
    user: User = Depends(require_roles(UserRole.OWNER)),
    session: AsyncSession = Depends(get_session),
):
    return await role_workflows.update_tariff(session, user, tariff_id, payload)


@router.get("/owner/clubs/{club_id}/staff", response_model=list[StaffMemberResponse])
async def list_owner_staff(
    club_id: uuid.UUID,
    user: User = Depends(require_roles(UserRole.OWNER)),
    session: AsyncSession = Depends(get_session),
):
    return await role_workflows.list_club_staff(session, user, club_id)


@router.post("/owner/clubs/{club_id}/staff", response_model=StaffMemberResponse, status_code=201)
async def assign_owner_staff(
    club_id: uuid.UUID,
    payload: StaffAssignmentCreate,
    user: User = Depends(require_roles(UserRole.OWNER)),
    session: AsyncSession = Depends(get_session),
):
    assignment = await role_workflows.assign_staff(session, user, club_id, payload)
    staff = await session.get(User, assignment.staff_user_id)
    return StaffMemberResponse(
        id=staff.id,
        email=staff.email,
        username=staff.username,
        full_name=staff.full_name,
        assigned_at=assignment.assigned_at,
    )


@router.delete("/owner/clubs/{club_id}/staff/{staff_user_id}", status_code=204)
async def remove_owner_staff(
    club_id: uuid.UUID,
    staff_user_id: uuid.UUID,
    user: User = Depends(require_roles(UserRole.OWNER)),
    session: AsyncSession = Depends(get_session),
) -> None:
    await role_workflows.remove_staff(session, user, club_id, staff_user_id)


@router.get("/owner/bookings", response_model=list[StaffBookingResponse])
async def list_owner_bookings(
    user: User = Depends(require_roles(UserRole.OWNER)), session: AsyncSession = Depends(get_session)
):
    return await role_workflows.owner_bookings(session, user)


@router.get("/staff/dashboard", response_model=StaffDashboard)
async def staff_dashboard(
    user: User = Depends(require_roles(UserRole.STAFF)), session: AsyncSession = Depends(get_session)
) -> StaffDashboard:
    return await role_workflows.staff_dashboard(session, user)


@router.get("/staff/bookings", response_model=list[StaffBookingResponse])
async def list_staff_bookings(
    user: User = Depends(require_roles(UserRole.STAFF)), session: AsyncSession = Depends(get_session)
):
    return await role_workflows.staff_bookings(session, user)


@router.get("/staff/computers", response_model=list[StaffComputerResponse])
async def list_staff_computers(
    user: User = Depends(require_roles(UserRole.STAFF)), session: AsyncSession = Depends(get_session)
):
    return await role_workflows.staff_computers(session, user)


@router.get("/staff/shifts", response_model=list[StaffShiftResponse])
async def list_staff_shifts(
    limit: int = Query(default=100, ge=1, le=500),
    user: User = Depends(require_roles(UserRole.STAFF)),
    session: AsyncSession = Depends(get_session),
) -> list[StaffShift]:
    return await role_workflows.staff_shifts(session, user, limit)


@router.post("/staff/bookings/verify-qr", response_model=StaffBookingResponse)
async def verify_staff_qr(
    payload: QRVerifyRequest,
    user: User = Depends(require_roles(UserRole.STAFF)),
    session: AsyncSession = Depends(get_session),
):
    return await role_workflows.verify_staff_qr(session, user, payload.qr_token)


@router.post("/staff/walk-ins", response_model=StaffBookingResponse, status_code=201)
async def staff_create_walk_in(
    payload: WalkInCreate,
    user: User = Depends(require_roles(UserRole.STAFF)),
    session: AsyncSession = Depends(get_session),
):
    booking = await bookings.create_walk_in(session, user, payload)
    return await role_workflows.staff_booking_details(session, user, booking.id)


@router.post("/staff/bookings/{booking_id}/start", response_model=StaffBookingResponse)
async def staff_start_session(
    booking_id: uuid.UUID,
    user: User = Depends(require_roles(UserRole.STAFF)),
    session: AsyncSession = Depends(get_session),
):
    return await role_workflows.staff_session_action(session, user, booking_id, "start")


@router.post("/staff/bookings/{booking_id}/extend", response_model=StaffBookingResponse)
async def staff_extend_session(
    booking_id: uuid.UUID,
    payload: SessionExtend,
    user: User = Depends(require_roles(UserRole.STAFF)),
    session: AsyncSession = Depends(get_session),
):
    return await role_workflows.staff_session_action(session, user, booking_id, "extend", payload)


@router.post("/staff/bookings/{booking_id}/end", response_model=StaffBookingResponse)
async def staff_end_session(
    booking_id: uuid.UUID,
    user: User = Depends(require_roles(UserRole.STAFF)),
    session: AsyncSession = Depends(get_session),
):
    return await role_workflows.staff_session_action(session, user, booking_id, "end")


@router.post("/staff/bookings/{booking_id}/check-in", response_model=StaffBookingResponse)
async def staff_check_in(
    booking_id: uuid.UUID,
    user: User = Depends(require_roles(UserRole.STAFF)),
    session: AsyncSession = Depends(get_session),
):
    return await role_workflows.staff_transition_booking(session, user, booking_id, BookingStatus.ACTIVE)


@router.post("/staff/bookings/{booking_id}/complete", response_model=StaffBookingResponse)
async def staff_complete_booking(
    booking_id: uuid.UUID,
    user: User = Depends(require_roles(UserRole.STAFF)),
    session: AsyncSession = Depends(get_session),
):
    return await role_workflows.staff_transition_booking(session, user, booking_id, BookingStatus.COMPLETED)


@router.patch("/staff/computers/{computer_id}/status", response_model=ComputerResponse)
async def staff_set_computer_status(
    computer_id: uuid.UUID,
    payload: ComputerStatusUpdate,
    user: User = Depends(require_roles(UserRole.STAFF)),
    session: AsyncSession = Depends(get_session),
):
    return await role_workflows.staff_update_computer_status(session, user, computer_id, payload)


@router.get("/admin/dashboard", response_model=AdminDashboard)
async def admin_dashboard(
    _: User = Depends(require_roles(UserRole.ADMIN)), session: AsyncSession = Depends(get_session)
) -> AdminDashboard:
    return await role_workflows.admin_dashboard(session)


@router.get("/admin/audit", response_model=list[AuditLogResponse])
async def admin_audit(
    limit: int = Query(default=100, ge=1, le=500),
    _: User = Depends(require_roles(UserRole.ADMIN)),
    session: AsyncSession = Depends(get_session),
) -> list[AuditLog]:
    return await role_workflows.admin_audit(session, limit)


@router.get("/admin/users", response_model=list[UserAdminResponse])
async def list_admin_users(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    _: User = Depends(require_roles(UserRole.ADMIN)),
    session: AsyncSession = Depends(get_session),
):
    return await role_workflows.admin_users(session, page, page_size)


@router.patch("/admin/users/{user_id}/status", response_model=UserAdminResponse)
async def update_admin_user_status(
    user_id: uuid.UUID,
    payload: UserActiveUpdate,
    admin: User = Depends(require_roles(UserRole.ADMIN)),
    session: AsyncSession = Depends(get_session),
):
    return await role_workflows.admin_update_user(session, admin, user_id, payload)


@router.get("/admin/clubs", response_model=list[ManagedClubResponse])
async def list_admin_clubs(
    _: User = Depends(require_roles(UserRole.ADMIN)), session: AsyncSession = Depends(get_session)
):
    return await role_workflows.admin_clubs(session)


@router.patch("/admin/clubs/{club_id}/status", response_model=ManagedClubResponse)
async def update_admin_club_status(
    club_id: uuid.UUID,
    payload: ClubUpdate,
    admin: User = Depends(require_roles(UserRole.ADMIN)),
    session: AsyncSession = Depends(get_session),
):
    return await role_workflows.admin_update_club(session, admin, club_id, payload)


@router.get("/admin/bookings", response_model=list[StaffBookingResponse])
async def list_admin_bookings(
    _: User = Depends(require_roles(UserRole.ADMIN)), session: AsyncSession = Depends(get_session)
):
    return await role_workflows.admin_bookings(session)


@router.patch("/admin/computers/{computer_id}/status", response_model=ComputerResponse)
async def update_admin_computer_status(
    computer_id: uuid.UUID,
    payload: ComputerStatusUpdate,
    admin: User = Depends(require_roles(UserRole.ADMIN)),
    session: AsyncSession = Depends(get_session),
):
    return await role_workflows.admin_update_computer_status(session, admin, computer_id, payload)


@router.patch("/admin/bookings/{booking_id}/status", response_model=StaffBookingResponse)
async def update_admin_booking_status(
    booking_id: uuid.UUID,
    payload: AdminBookingStatusUpdate,
    user: User = Depends(require_roles(UserRole.ADMIN)),
    session: AsyncSession = Depends(get_session),
):
    return await role_workflows.admin_update_booking_status(session, user, booking_id, payload)
