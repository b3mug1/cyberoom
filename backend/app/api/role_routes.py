import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.dependencies import get_current_user, require_roles
from app.models import BookingStatus, StaffAssignment, User, UserRole
from app.schemas import (
    AccessToken,
    AdminBookingStatusUpdate,
    AdminDashboard,
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
    QRVerifyRequest,
    StaffAssignmentCreate,
    StaffBookingResponse,
    StaffDashboard,
    StaffComputerResponse,
    StaffMemberResponse,
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
    _: User = Depends(require_roles(UserRole.ADMIN)),
    session: AsyncSession = Depends(get_session),
):
    return await role_workflows.admin_update_user(session, user_id, payload)


@router.get("/admin/clubs", response_model=list[ManagedClubResponse])
async def list_admin_clubs(
    _: User = Depends(require_roles(UserRole.ADMIN)), session: AsyncSession = Depends(get_session)
):
    return await role_workflows.admin_clubs(session)


@router.patch("/admin/clubs/{club_id}/status", response_model=ManagedClubResponse)
async def update_admin_club_status(
    club_id: uuid.UUID,
    payload: ClubUpdate,
    _: User = Depends(require_roles(UserRole.ADMIN)),
    session: AsyncSession = Depends(get_session),
):
    return await role_workflows.admin_update_club(session, club_id, payload)


@router.get("/admin/bookings", response_model=list[StaffBookingResponse])
async def list_admin_bookings(
    _: User = Depends(require_roles(UserRole.ADMIN)), session: AsyncSession = Depends(get_session)
):
    return await role_workflows.admin_bookings(session)


@router.patch("/admin/computers/{computer_id}/status", response_model=ComputerResponse)
async def update_admin_computer_status(
    computer_id: uuid.UUID,
    payload: ComputerStatusUpdate,
    _: User = Depends(require_roles(UserRole.ADMIN)),
    session: AsyncSession = Depends(get_session),
):
    return await role_workflows.admin_update_computer_status(session, computer_id, payload)


@router.patch("/admin/bookings/{booking_id}/status", response_model=StaffBookingResponse)
async def update_admin_booking_status(
    booking_id: uuid.UUID,
    payload: AdminBookingStatusUpdate,
    user: User = Depends(require_roles(UserRole.ADMIN)),
    session: AsyncSession = Depends(get_session),
):
    return await role_workflows.admin_update_booking_status(session, user, booking_id, payload)
