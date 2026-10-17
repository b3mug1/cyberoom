import uuid
from datetime import datetime, time
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.models import BookingSource, BookingStatus, ComputerStatus, UserRole


class UserCreate(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=40, pattern=r"^[a-zA-Z0-9_.-]+$")
    full_name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=12, max_length=128)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    username: str
    full_name: str
    role: UserRole

    model_config = ConfigDict(from_attributes=True)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class AccessToken(BaseModel):
    access_token: str
    token_type: str = "bearer"



class ComputerResponse(BaseModel):
    id: uuid.UUID
    name: str
    cpu: str
    gpu: str
    ram_gb: int
    storage: str
    monitor: str
    refresh_rate: int
    status: ComputerStatus
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class StaffComputerResponse(ComputerResponse):
    club_id: uuid.UUID
    club_name: str


class TariffResponse(BaseModel):
    id: uuid.UUID
    name: str
    price_per_hour: Decimal
    start_time: time
    end_time: time

    model_config = ConfigDict(from_attributes=True)


class ClubResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    address: str
    city: str
    phone: str
    rating: Decimal
    is_active: bool
    computers: list[ComputerResponse] = Field(default_factory=list)
    tariffs: list[TariffResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class BookingCreate(BaseModel):
    computer_id: uuid.UUID
    start_time: datetime
    end_time: datetime

    @model_validator(mode="after")
    def validate_interval(self) -> "BookingCreate":
        if self.start_time.tzinfo is None or self.end_time.tzinfo is None:
            raise ValueError("Booking times must include a timezone")
        if self.start_time >= self.end_time:
            raise ValueError("Start time must be before end time")
        if self.start_time.second or self.end_time.second or self.start_time.microsecond or self.end_time.microsecond:
            raise ValueError("Booking times must use whole minutes")
        return self


class WalkInCreate(BaseModel):
    computer_id: uuid.UUID
    guest_name: str = Field(min_length=1, max_length=120)
    end_time: datetime

    @model_validator(mode="after")
    def validate_end_time(self) -> "WalkInCreate":
        if self.end_time.tzinfo is None or self.end_time.second or self.end_time.microsecond:
            raise ValueError("End time must include a timezone and use whole minutes")
        self.guest_name = self.guest_name.strip()
        if not self.guest_name:
            raise ValueError("Guest name is required")
        return self


class SessionExtend(BaseModel):
    end_time: datetime

    @model_validator(mode="after")
    def validate_end_time(self) -> "SessionExtend":
        if self.end_time.tzinfo is None or self.end_time.second or self.end_time.microsecond:
            raise ValueError("End time must include a timezone and use whole minutes")
        return self


class BusyInterval(BaseModel):
    start_time: datetime
    end_time: datetime


class ComputerAvailability(BaseModel):
    computer_id: uuid.UUID
    computer_name: str
    status: ComputerStatus
    is_active: bool
    busy: list[BusyInterval]


class ClubAvailability(BaseModel):
    club_id: uuid.UUID
    start_time: datetime
    end_time: datetime
    computers: list[ComputerAvailability]


class BookingQuoteResponse(BaseModel):
    total_price: Decimal
    currency: str = "KZT"


class ClubCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=5000)
    address: str = Field(min_length=3, max_length=240)
    city: str = Field(min_length=2, max_length=100)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    phone: str = Field(default="", max_length=32)
    opening_time: time = time(0)
    closing_time: time = time(23, 59)


class ClubUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=5000)
    address: str | None = Field(default=None, min_length=3, max_length=240)
    city: str | None = Field(default=None, min_length=2, max_length=100)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    phone: str | None = Field(default=None, max_length=32)
    opening_time: time | None = None
    closing_time: time | None = None
    is_active: bool | None = None


class ComputerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    cpu: str = Field(min_length=1, max_length=120)
    gpu: str = Field(min_length=1, max_length=120)
    ram_gb: int = Field(ge=1, le=1024)
    storage: str = Field(min_length=1, max_length=80)
    monitor: str = Field(default="", max_length=120)
    refresh_rate: int = Field(default=60, ge=30, le=1000)


class ComputerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    cpu: str | None = Field(default=None, min_length=1, max_length=120)
    gpu: str | None = Field(default=None, min_length=1, max_length=120)
    ram_gb: int | None = Field(default=None, ge=1, le=1024)
    storage: str | None = Field(default=None, min_length=1, max_length=80)
    monitor: str | None = Field(default=None, max_length=120)
    refresh_rate: int | None = Field(default=None, ge=30, le=1000)
    is_active: bool | None = None


class ComputerStatusUpdate(BaseModel):
    status: ComputerStatus


class TariffCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=240)
    price_per_hour: Decimal = Field(gt=0, le=1000000)
    start_time: time
    end_time: time
    is_active: bool = True


class TariffUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=240)
    price_per_hour: Decimal | None = Field(default=None, gt=0, le=1000000)
    start_time: time | None = None
    end_time: time | None = None
    is_active: bool | None = None


class StaffAssignmentCreate(BaseModel):
    email: EmailStr


class StaffMemberResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    username: str
    full_name: str
    assigned_at: datetime


class QRVerifyRequest(BaseModel):
    qr_token: str = Field(min_length=16, max_length=64)


class UserActiveUpdate(BaseModel):
    is_active: bool


class AdminBookingStatusUpdate(BaseModel):
    status: BookingStatus


class UserAdminResponse(UserResponse):
    is_active: bool
    created_at: datetime


class ManagedClubResponse(ClubResponse):
    owner_id: uuid.UUID
    is_active: bool


class StaffBookingResponse(BaseModel):
    id: uuid.UUID
    club_id: uuid.UUID
    club_name: str
    customer_name: str
    customer_email: EmailStr | None
    source: BookingSource
    computer_id: uuid.UUID
    computer_name: str
    start_time: datetime
    end_time: datetime
    status: BookingStatus
    total_price: Decimal


class OwnerClubMetric(BaseModel):
    id: uuid.UUID
    name: str
    city: str
    is_active: bool
    computers: int
    active_computers: int
    available_computers: int
    bookings_today: int
    revenue_today: Decimal


class OwnerDashboard(BaseModel):
    club_count: int
    computer_count: int
    active_computers: int
    maintenance_computers: int
    bookings_today: int
    revenue_today: Decimal
    clubs: list[OwnerClubMetric]


class StaffDashboard(BaseModel):
    assigned_clubs: int
    bookings_today: int
    upcoming_bookings: int
    active_sessions: int
    bookings: list[StaffBookingResponse]


class AdminDashboard(BaseModel):
    users: int
    active_users: int
    clubs: int
    active_clubs: int
    computers: int
    active_computers: int
    bookings_today: int
    revenue_today: Decimal


class BookingResponse(BaseModel):
    id: uuid.UUID
    computer_id: uuid.UUID
    start_time: datetime
    end_time: datetime
    status: BookingStatus
    source: BookingSource
    total_price: Decimal
    qr_token: str

    model_config = ConfigDict(from_attributes=True)


class ClubPage(BaseModel):
    items: list[ClubResponse]
    page: int
    page_size: int
    total: int
