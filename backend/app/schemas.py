import uuid
from typing import Any, Literal
from datetime import date, datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AliasPath, BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

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
    days_of_week: list[int]

    model_config = ConfigDict(from_attributes=True)


class ClubResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    address: str
    city: str
    timezone: str
    refund_cutoff_hours: int
    price_menu: dict[str, Any] = Field(default_factory=dict)
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
    promo_code: str | None = Field(default=None, min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_-]+$")
    use_membership: bool = False

    @model_validator(mode="after")
    def validate_interval(self) -> "BookingCreate":
        if self.start_time.tzinfo is None or self.end_time.tzinfo is None:
            raise ValueError("Booking times must include a timezone")
        if self.start_time >= self.end_time:
            raise ValueError("Start time must be before end time")
        if self.start_time.second or self.end_time.second or self.start_time.microsecond or self.end_time.microsecond:
            raise ValueError("Booking times must use whole minutes")
        if self.promo_code is not None:
            self.promo_code = self.promo_code.strip().upper()
        if self.promo_code and self.use_membership:
            raise ValueError("A promo code cannot be combined with membership hours")
        return self


class BookingReschedule(BaseModel):
    computer_id: uuid.UUID
    start_time: datetime
    end_time: datetime

    @model_validator(mode="after")
    def validate_interval(self) -> "BookingReschedule":
        if self.start_time.tzinfo is None or self.end_time.tzinfo is None:
            raise ValueError("Booking times must include a timezone")
        if self.start_time >= self.end_time:
            raise ValueError("Start time must be before end time")
        if self.start_time.second or self.end_time.second or self.start_time.microsecond or self.end_time.microsecond:
            raise ValueError("Booking times must use whole minutes")
        return self


class ReviewCreate(BaseModel):
    club_rating: int = Field(ge=1, le=5)
    computer_rating: int = Field(ge=1, le=5)
    comment: str = Field(default="", max_length=2000)

    @field_validator("comment")
    @classmethod
    def normalize_comment(cls, value: str) -> str:
        return value.strip()


class ReviewResponse(BaseModel):
    id: uuid.UUID
    club_rating: int
    computer_rating: int
    comment: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ClubReviewResponse(ReviewResponse):
    computer_name: str = Field(validation_alias=AliasPath("computer", "name"))


class NotificationResponse(BaseModel):
    id: uuid.UUID
    booking_id: uuid.UUID | None
    kind: str
    title: str
    message: str
    payload: dict[str, Any]
    scheduled_at: datetime
    read_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class AuditLogResponse(BaseModel):
    id: uuid.UUID
    actor_id: uuid.UUID | None
    club_id: uuid.UUID | None
    action: str
    entity_type: str
    entity_id: str
    details: dict[str, Any]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WaitlistCreate(BaseModel):
    club_id: uuid.UUID
    computer_id: uuid.UUID | None = None
    start_time: datetime
    end_time: datetime

    @model_validator(mode="after")
    def validate_interval(self) -> "WaitlistCreate":
        if self.start_time.tzinfo is None or self.end_time.tzinfo is None:
            raise ValueError("Waitlist times must include a timezone")
        if self.start_time >= self.end_time:
            raise ValueError("Start time must be before end time")
        if self.start_time.second or self.end_time.second or self.start_time.microsecond or self.end_time.microsecond:
            raise ValueError("Waitlist times must use whole minutes")
        return self


class WaitlistResponse(BaseModel):
    id: uuid.UUID
    club_id: uuid.UUID
    computer_id: uuid.UUID | None
    start_time: datetime
    end_time: datetime
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


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
    subtotal_price: Decimal
    discount_amount: Decimal
    promo_code: str | None = None
    membership_minutes: int = 0
    membership_credit_amount: Decimal = Decimal("0.00")
    currency: str = "KZT"


class PromoCodeCreate(BaseModel):
    code: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_-]+$")
    discount_type: Literal["PERCENT", "FIXED"]
    discount_value: Decimal = Field(gt=0, le=1000000)
    starts_at: datetime
    ends_at: datetime
    usage_limit: int | None = Field(default=None, ge=1, le=10000000)
    per_user_limit: int = Field(default=1, ge=1, le=1000)

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.strip().upper()

    @model_validator(mode="after")
    def validate_promo(self) -> "PromoCodeCreate":
        if self.starts_at.tzinfo is None or self.ends_at.tzinfo is None:
            raise ValueError("Promotion times must include a timezone")
        if self.starts_at >= self.ends_at:
            raise ValueError("Promotion start must be before its end")
        if self.discount_type == "PERCENT" and self.discount_value > 100:
            raise ValueError("Percentage discounts cannot exceed 100")
        return self


class PromoCodeStatusUpdate(BaseModel):
    is_active: bool


class PromoCodeResponse(BaseModel):
    id: uuid.UUID
    club_id: uuid.UUID
    code: str
    discount_type: str
    discount_value: Decimal
    starts_at: datetime
    ends_at: datetime
    usage_limit: int | None
    used_count: int
    per_user_limit: int
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MembershipPlanCreate(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    description: str = Field(default="", max_length=500)
    hours: int = Field(ge=1, le=1000)
    price: Decimal = Field(gt=0, le=100000000)
    validity_days: int = Field(default=30, ge=1, le=3650)


class MembershipPlanStatusUpdate(BaseModel):
    is_active: bool


class MembershipPlanResponse(BaseModel):
    id: uuid.UUID
    club_id: uuid.UUID
    name: str
    description: str
    hours: int
    price: Decimal
    validity_days: int
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class MembershipResponse(BaseModel):
    id: uuid.UUID
    club_id: uuid.UUID
    club_name: str
    plan_name: str
    total_minutes: int
    remaining_minutes: int
    starts_at: datetime
    expires_at: datetime


class PaymentResponse(BaseModel):
    id: uuid.UUID
    booking_id: uuid.UUID | None
    membership_plan_id: uuid.UUID | None
    amount: Decimal
    currency: str
    status: str
    checkout_url: str | None
    refund_amount: Decimal
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ClubCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=5000)
    address: str = Field(min_length=3, max_length=240)
    city: str = Field(min_length=2, max_length=100)
    timezone: str = Field(default="Asia/Almaty", min_length=1, max_length=64)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    phone: str = Field(default="", max_length=32)
    opening_time: time = time(0)
    closing_time: time = time(23, 59)
    refund_cutoff_hours: int = Field(default=24, ge=0, le=720)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise ValueError("Use a valid IANA time zone, such as Asia/Almaty") from error
        return value


class ClubUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=5000)
    address: str | None = Field(default=None, min_length=3, max_length=240)
    city: str | None = Field(default=None, min_length=2, max_length=100)
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    phone: str | None = Field(default=None, max_length=32)
    opening_time: time | None = None
    closing_time: time | None = None
    refund_cutoff_hours: int | None = Field(default=None, ge=0, le=720)
    is_active: bool | None = None

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str | None) -> str | None:
        if value is None:
            raise ValueError("Time zone cannot be null")
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise ValueError("Use a valid IANA time zone, such as Asia/Almaty") from error
        return value


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
    days_of_week: list[int] = Field(default_factory=lambda: list(range(7)))
    is_active: bool = True

    @field_validator("days_of_week")
    @classmethod
    def validate_days_of_week(cls, value: list[int]) -> list[int]:
        if not value or len(set(value)) != len(value) or any(day < 0 or day > 6 for day in value):
            raise ValueError("Choose one or more days using values 0 (Monday) through 6 (Sunday)")
        return sorted(value)


class TariffUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=240)
    price_per_hour: Decimal | None = Field(default=None, gt=0, le=1000000)
    start_time: time | None = None
    end_time: time | None = None
    days_of_week: list[int] | None = None
    is_active: bool | None = None

    @field_validator("days_of_week")
    @classmethod
    def validate_days_of_week(cls, value: list[int] | None) -> list[int] | None:
        if value is None:
            raise ValueError("Days of week cannot be null")
        if not value or len(set(value)) != len(value) or any(day < 0 or day > 6 for day in value):
            raise ValueError("Choose one or more days using values 0 (Monday) through 6 (Sunday)")
        return sorted(value)


class StaffAssignmentCreate(BaseModel):
    email: EmailStr


class StaffShiftCreate(BaseModel):
    staff_email: EmailStr
    start_time: datetime
    end_time: datetime

    @model_validator(mode="after")
    def validate_shift(self) -> "StaffShiftCreate":
        if self.start_time.tzinfo is None or self.end_time.tzinfo is None:
            raise ValueError("Shift times must include a timezone")
        if self.start_time >= self.end_time:
            raise ValueError("Shift start must be before its end")
        if self.start_time.second or self.end_time.second or self.start_time.microsecond or self.end_time.microsecond:
            raise ValueError("Shift times must use whole minutes")
        return self


class StaffShiftResponse(BaseModel):
    id: uuid.UUID
    club_id: uuid.UUID
    club_name: str = Field(validation_alias=AliasPath("club", "name"))
    staff_user_id: uuid.UUID
    staff_name: str = Field(validation_alias=AliasPath("staff_user", "full_name"))
    staff_email: EmailStr = Field(validation_alias=AliasPath("staff_user", "email"))
    start_time: datetime
    end_time: datetime
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


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


class OwnerReportDay(BaseModel):
    date: date
    bookings: int
    booking_value: Decimal


class OwnerReportHour(BaseModel):
    hour: int
    bookings: int


class OwnerReportComputer(BaseModel):
    computer_id: uuid.UUID
    computer_name: str
    bookings: int
    booking_value: Decimal


class OwnerReport(BaseModel):
    start_date: date
    end_date: date
    currency: str = "KZT"
    bookings: int
    booking_value: Decimal
    daily: list[OwnerReportDay]
    hourly: list[OwnerReportHour]
    computers: list[OwnerReportComputer]


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
    club_id: uuid.UUID = Field(validation_alias=AliasPath("computer", "club_id"))
    computer_name: str = Field(validation_alias=AliasPath("computer", "name"))
    refund_cutoff_hours: int
    start_time: datetime
    end_time: datetime
    status: BookingStatus
    source: BookingSource
    total_price: Decimal
    subtotal_price: Decimal
    discount_amount: Decimal
    membership_minutes: int
    membership_credit_amount: Decimal
    payment_status: str | None = Field(default=None, validation_alias=AliasPath("payment", "status"))
    promo_code: str | None = Field(default=None, validation_alias=AliasPath("promo_code", "code"))
    qr_token: str
    review: ReviewResponse | None = None

    model_config = ConfigDict(from_attributes=True)


class ClubPage(BaseModel):
    items: list[ClubResponse]
    page: int
    page_size: int
    total: int
