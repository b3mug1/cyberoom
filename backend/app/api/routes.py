import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_session
from app.dependencies import get_current_user
from app.models import Booking, Club, Computer, Tariff, User
from app.core.config import get_settings
from app.schemas import AccessToken, BookingCreate, BookingQuoteResponse, BookingResponse, ClubAvailability, ClubPage, ClubResponse, UserCreate, UserLogin, UserResponse
from app.services import auth, bookings
from app.services.errors import ServiceError

router = APIRouter()


@router.post("/auth/register", response_model=AccessToken, status_code=201)
async def register(payload: UserCreate, response: Response, session: AsyncSession = Depends(get_session)) -> AccessToken:
    _, tokens = await auth.register(session, payload)
    _set_refresh_cookie(response, tokens.refresh_token)
    return AccessToken(access_token=tokens.access_token)


@router.post("/auth/login", response_model=AccessToken)
async def login(payload: UserLogin, response: Response, session: AsyncSession = Depends(get_session)) -> AccessToken:
    _, tokens = await auth.login(session, payload)
    _set_refresh_cookie(response, tokens.refresh_token)
    return AccessToken(access_token=tokens.access_token)


@router.post("/auth/refresh", response_model=AccessToken)
async def refresh(request: Request, response: Response, session: AsyncSession = Depends(get_session)) -> AccessToken:
    token = request.cookies.get("cyberbook_refresh")
    if not token:
        raise ServiceError("INVALID_REFRESH_TOKEN", "The refresh token is invalid or expired.", 401)
    _require_trusted_cookie_origin(request)
    tokens = await auth.refresh(session, token)
    _set_refresh_cookie(response, tokens.refresh_token)
    return AccessToken(access_token=tokens.access_token)


@router.post("/auth/logout", status_code=204)
async def logout(request: Request, response: Response, session: AsyncSession = Depends(get_session)) -> None:
    token = request.cookies.get("cyberbook_refresh")
    if token:
        _require_trusted_cookie_origin(request)
        await auth.logout(session, token)
    response.delete_cookie("cyberbook_refresh", path="/api/v1/auth", httponly=True, samesite="lax")


def _require_trusted_cookie_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    trusted = {value.rstrip("/") for value in get_settings().allowed_origins}
    trusted.add(str(request.base_url).rstrip("/"))
    if origin not in trusted:
        raise ServiceError("UNTRUSTED_ORIGIN", "Refresh-cookie requests require a trusted Origin header.", 403)


def _set_refresh_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        "cyberbook_refresh",
        token,
        max_age=settings.jwt_refresh_token_expire_days * 24 * 60 * 60,
        httponly=True,
        secure=settings.app_env == "production",
        samesite="lax",
        path="/api/v1/auth",
    )


@router.get("/auth/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user)) -> User:
    return user


@router.get("/clubs", response_model=ClubPage)
async def list_clubs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=12, ge=1, le=50),
    search: str | None = Query(default=None, max_length=100),
    city: str | None = Query(default=None, max_length=100),
    min_rating: float | None = Query(default=None, ge=0, le=5),
    min_ram: int | None = Query(default=None, ge=1, le=512),
    session: AsyncSession = Depends(get_session),
) -> ClubPage:
    statement = select(Club).where(Club.is_active.is_(True)).options(selectinload(Club.computers), selectinload(Club.tariffs))
    filters = []
    if search:
        pattern = f"%{search}%"
        filters.append(or_(Club.name.ilike(pattern), Club.city.ilike(pattern), Club.address.ilike(pattern), Club.computers.any(Computer.gpu.ilike(pattern)), Club.computers.any(Computer.cpu.ilike(pattern))))
    if city:
        filters.append(Club.city.ilike(f"%{city}%"))
    if min_rating is not None:
        filters.append(Club.rating >= min_rating)
    if min_ram is not None:
        filters.append(Club.computers.any(Computer.ram_gb >= min_ram))
    if filters:
        statement = statement.where(*filters)
    total = await session.scalar(select(func.count()).select_from(statement.order_by(None).subquery())) or 0
    result = await session.scalars(statement.order_by(Club.rating.desc(), Club.name).offset((page - 1) * page_size).limit(page_size))
    return ClubPage(items=list(result), page=page, page_size=page_size, total=total)


@router.get("/clubs/{club_id}", response_model=ClubResponse)
async def get_club(club_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> Club:
    club = await session.scalar(select(Club).where(Club.id == club_id, Club.is_active.is_(True)).options(selectinload(Club.computers), selectinload(Club.tariffs)))
    if club is None:
        from app.services.errors import ServiceError

        raise ServiceError("CLUB_NOT_FOUND", "Club not found.", 404)
    return club


@router.get("/clubs/{club_id}/availability", response_model=ClubAvailability)
async def get_club_availability(
    club_id: uuid.UUID,
    start_time: datetime,
    end_time: datetime,
    session: AsyncSession = Depends(get_session),
) -> ClubAvailability:
    return await bookings.club_availability(session, club_id, start_time, end_time)


@router.post("/bookings", response_model=BookingResponse, status_code=201)
async def create_booking(
    payload: BookingCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Booking:
    return await bookings.create_booking(session, user, payload)


@router.post("/bookings/quote", response_model=BookingQuoteResponse)
async def quote_booking(payload: BookingCreate, session: AsyncSession = Depends(get_session)) -> BookingQuoteResponse:
    return BookingQuoteResponse(total_price=await bookings.quote_booking(session, payload))


@router.get("/bookings", response_model=list[BookingResponse])
async def list_bookings(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[Booking]:
    return await bookings.list_bookings(session, user)


@router.get("/bookings/{booking_id}", response_model=BookingResponse)
async def get_booking(
    booking_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Booking:
    return await bookings.get_booking(session, user, booking_id)


@router.post("/bookings/{booking_id}/cancel", response_model=BookingResponse)
async def cancel_booking(
    booking_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Booking:
    return await bookings.cancel_booking(session, user, booking_id)
