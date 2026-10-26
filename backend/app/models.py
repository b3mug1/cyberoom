import enum
import uuid
from datetime import datetime, time, timezone
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum, ForeignKey, Index, Integer, Numeric, String, Time, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import ARRAY, ExcludeConstraint, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import expression
from sqlalchemy import func as sql_func


class Base(DeclarativeBase):
    pass


class UserRole(str, enum.Enum):
    USER = "USER"
    STAFF = "STAFF"
    OWNER = "OWNER"
    ADMIN = "ADMIN"


class ComputerStatus(str, enum.Enum):
    AVAILABLE = "AVAILABLE"
    OCCUPIED = "OCCUPIED"
    MAINTENANCE = "MAINTENANCE"
    DISABLED = "DISABLED"


class BookingStatus(str, enum.Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class BookingSource(str, enum.Enum):
    ONLINE = "ONLINE"
    WALK_IN = "WALK_IN"


def enum_values(enum_type: type[enum.Enum]) -> list[str]:
    return [value.value for value in enum_type]


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    username: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole, name="user_role", values_callable=enum_values), default=UserRole.USER)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    bookings: Mapped[list["Booking"]] = relationship(back_populates="user")
    clubs: Mapped[list["Club"]] = relationship(back_populates="owner")


class Club(Base):
    __tablename__ = "clubs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    address: Mapped[str] = mapped_column(String(240))
    city: Mapped[str] = mapped_column(String(100), index=True)
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Almaty", server_default="Asia/Almaty")
    price_menu: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    latitude: Mapped[float | None]
    longitude: Mapped[float | None]
    phone: Mapped[str] = mapped_column(String(32), default="")
    opening_time: Mapped[time] = mapped_column(Time, default=time(0, 0))
    closing_time: Mapped[time] = mapped_column(Time, default=time(23, 59))
    refund_cutoff_hours: Mapped[int] = mapped_column(Integer, default=24, server_default="24")
    rating: Mapped[Decimal] = mapped_column(Numeric(3, 2), default=Decimal("0"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    owner: Mapped[User] = relationship(back_populates="clubs")
    computers: Mapped[list["Computer"]] = relationship(back_populates="club", cascade="all, delete-orphan")
    tariffs: Mapped[list["Tariff"]] = relationship(back_populates="club", cascade="all, delete-orphan")
    membership_plans: Mapped[list["MembershipPlan"]] = relationship(back_populates="club", cascade="all, delete-orphan")


class Computer(Base):
    __tablename__ = "computers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    club_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clubs.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    cpu: Mapped[str] = mapped_column(String(120))
    gpu: Mapped[str] = mapped_column(String(120), index=True)
    ram_gb: Mapped[int] = mapped_column(Integer)
    storage: Mapped[str] = mapped_column(String(80))
    monitor: Mapped[str] = mapped_column(String(120), default="")
    refresh_rate: Mapped[int] = mapped_column(Integer, default=60)
    status: Mapped[ComputerStatus] = mapped_column(
        Enum(ComputerStatus, name="computer_status", values_callable=enum_values), default=ComputerStatus.AVAILABLE
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    club: Mapped[Club] = relationship(back_populates="computers")
    bookings: Mapped[list["Booking"]] = relationship(back_populates="computer")


class Tariff(Base):
    __tablename__ = "tariffs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    club_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clubs.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(String(240), default="")
    price_per_hour: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    start_time: Mapped[time] = mapped_column(Time, default=time(0, 0))
    end_time: Mapped[time] = mapped_column(Time, default=time(23, 59, 59))
    days_of_week: Mapped[list[int]] = mapped_column(ARRAY(Integer), default=lambda: list(range(7)), server_default=text("ARRAY[0,1,2,3,4,5,6]"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    club: Mapped[Club] = relationship(back_populates="tariffs")


class Booking(Base):
    __tablename__ = "bookings"
    __table_args__ = (
        CheckConstraint("(source = 'ONLINE' AND user_id IS NOT NULL AND guest_name IS NULL) OR (source = 'WALK_IN' AND user_id IS NULL AND guest_name IS NOT NULL)", name="booking_customer_matches_source"),
        ExcludeConstraint(
            ("computer_id", "="),
            (sql_func.tstzrange(text("start_time"), text("end_time"), "[)"), "&&"),
            where=text("status IN ('PENDING', 'CONFIRMED', 'ACTIVE')"),
            using="gist",
            name="booking_no_overlapping_active_ranges",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=True)
    guest_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source: Mapped[BookingSource] = mapped_column(Enum(BookingSource, name="booking_source", values_callable=enum_values), default=BookingSource.ONLINE)
    computer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("computers.id", ondelete="RESTRICT"), index=True)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[BookingStatus] = mapped_column(
        Enum(BookingStatus, name="booking_status", values_callable=enum_values), default=BookingStatus.CONFIRMED, index=True
    )
    total_price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    refund_cutoff_hours: Mapped[int] = mapped_column(Integer, default=24, server_default="24")
    subtotal_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"), server_default="0")
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"), server_default="0")
    promo_code_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("promo_codes.id", ondelete="SET NULL"), nullable=True, index=True)
    membership_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("memberships.id", ondelete="SET NULL"), nullable=True, index=True)
    membership_minutes: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    membership_credit_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"), server_default="0")
    qr_token: Mapped[str] = mapped_column(String(64), unique=True, index=True, default=lambda: uuid.uuid4().hex)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    user: Mapped[User | None] = relationship(back_populates="bookings")
    computer: Mapped[Computer] = relationship(back_populates="bookings")
    session: Mapped["Session | None"] = relationship(back_populates="booking", uselist=False)
    review: Mapped["Review | None"] = relationship(back_populates="booking", uselist=False)
    promo_code: Mapped["PromoCode | None"] = relationship(back_populates="bookings")
    membership: Mapped["Membership | None"] = relationship(back_populates="bookings", foreign_keys=[membership_id])
    payment: Mapped["Payment | None"] = relationship(back_populates="booking", uselist=False, foreign_keys="Payment.booking_id")


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (
        CheckConstraint("club_rating BETWEEN 1 AND 5", name="review_club_rating_range"),
        CheckConstraint("computer_rating BETWEEN 1 AND 5", name="review_computer_rating_range"),
        UniqueConstraint("booking_id", name="uq_review_booking"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    booking_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bookings.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    club_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clubs.id", ondelete="CASCADE"), index=True)
    computer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("computers.id", ondelete="CASCADE"), index=True)
    club_rating: Mapped[int] = mapped_column(Integer)
    computer_rating: Mapped[int] = mapped_column(Integer)
    comment: Mapped[str] = mapped_column(String(2000), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    booking: Mapped[Booking] = relationship(back_populates="review")
    computer: Mapped[Computer] = relationship()


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    booking_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bookings.id", ondelete="CASCADE"), unique=True, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    ended_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    booking: Mapped[Booking] = relationship(back_populates="session")


class RefreshSession(Base):
    __tablename__ = "refresh_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class StaffAssignment(Base):
    __tablename__ = "staff_assignments"
    __table_args__ = (UniqueConstraint("staff_user_id", "club_id", name="uq_staff_assignment_user_club"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    staff_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    club_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clubs.id", ondelete="CASCADE"), index=True)
    assigned_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    booking_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("bookings.id", ondelete="SET NULL"), index=True, nullable=True)
    kind: Mapped[str] = mapped_column(String(48), index=True)
    title: Mapped[str] = mapped_column(String(120))
    message: Mapped[str] = mapped_column(String(500))
    payload: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WaitlistEntry(Base):
    __tablename__ = "waitlist_entries"
    __table_args__ = (
        CheckConstraint("start_time < end_time", name="waitlist_valid_interval"),
        CheckConstraint("status IN ('WAITING', 'NOTIFIED', 'CANCELLED')", name="waitlist_valid_status"),
        UniqueConstraint("user_id", "club_id", "computer_id", "start_time", "end_time", name="uq_waitlist_request"),
        Index("uq_waitlist_all_computers_request", "user_id", "club_id", "start_time", "end_time", unique=True, postgresql_where=text("computer_id IS NULL")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    club_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clubs.id", ondelete="CASCADE"), index=True)
    computer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("computers.id", ondelete="SET NULL"), index=True, nullable=True)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(24), default="WAITING", server_default="WAITING", index=True)
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True)
    club_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("clubs.id", ondelete="SET NULL"), index=True, nullable=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str] = mapped_column(String(64))
    details: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class StaffShift(Base):
    __tablename__ = "staff_shifts"
    __table_args__ = (
        CheckConstraint("start_time < end_time", name="staff_shift_valid_interval"),
        ExcludeConstraint(
            ("staff_user_id", "="),
            (sql_func.tstzrange(text("start_time"), text("end_time"), "[)"), "&&"),
            using="gist",
            name="staff_shift_no_overlap",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    club_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clubs.id", ondelete="CASCADE"), index=True)
    staff_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    club: Mapped[Club] = relationship()
    staff_user: Mapped[User] = relationship(foreign_keys=[staff_user_id])


class PromoCode(Base):
    __tablename__ = "promo_codes"
    __table_args__ = (
        UniqueConstraint("club_id", "code", name="uq_promo_code_club_code"),
        CheckConstraint("discount_type IN ('PERCENT', 'FIXED')", name="promo_discount_type_valid"),
        CheckConstraint("discount_value > 0", name="promo_discount_value_positive"),
        CheckConstraint("discount_type != 'PERCENT' OR discount_value <= 100", name="promo_percent_max"),
        CheckConstraint("used_count >= 0", name="promo_used_count_nonnegative"),
        CheckConstraint("usage_limit IS NULL OR usage_limit >= 1", name="promo_usage_limit_positive"),
        CheckConstraint("per_user_limit >= 1", name="promo_user_limit_positive"),
        CheckConstraint("starts_at < ends_at", name="promo_valid_interval"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    club_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clubs.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(32), index=True)
    discount_type: Mapped[str] = mapped_column(String(16))
    discount_value: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    usage_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    used_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    per_user_limit: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    bookings: Mapped[list[Booking]] = relationship(back_populates="promo_code")


class MembershipPlan(Base):
    __tablename__ = "membership_plans"
    __table_args__ = (
        CheckConstraint("hours > 0", name="membership_plan_hours_positive"),
        CheckConstraint("price > 0", name="membership_plan_price_positive"),
        CheckConstraint("validity_days >= 1", name="membership_plan_validity_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    club_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clubs.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(String(500), default="")
    hours: Mapped[int] = mapped_column(Integer)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    validity_days: Mapped[int] = mapped_column(Integer, default=30, server_default="30")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    club: Mapped[Club] = relationship(back_populates="membership_plans")


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("(booking_id IS NOT NULL) <> (membership_plan_id IS NOT NULL)", name="payment_exactly_one_target"),
        CheckConstraint("amount >= 0", name="payment_amount_nonnegative"),
        CheckConstraint("status IN ('PENDING', 'CHECKOUT_CREATED', 'PAID', 'FAILED', 'REFUND_PENDING', 'REFUNDED')", name="payment_status_valid"),
        UniqueConstraint("booking_id", name="uq_payment_booking"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    booking_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("bookings.id", ondelete="CASCADE"), nullable=True, index=True)
    membership_plan_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("membership_plans.id", ondelete="RESTRICT"), nullable=True, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    currency: Mapped[str] = mapped_column(String(3), default="KZT", server_default="KZT")
    status: Mapped[str] = mapped_column(String(24), default="PENDING", server_default="PENDING", index=True)
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider_reference: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    checkout_url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    refund_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"), server_default="0")
    refund_reference: Mapped[str | None] = mapped_column(String(160), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True, default=lambda: uuid.uuid4().hex)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    booking: Mapped[Booking | None] = relationship(back_populates="payment", foreign_keys=[booking_id])


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (
        CheckConstraint("total_minutes > 0", name="membership_total_minutes_positive"),
        CheckConstraint("remaining_minutes >= 0 AND remaining_minutes <= total_minutes", name="membership_remaining_minutes_valid"),
        UniqueConstraint("payment_id", name="uq_membership_payment"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    club_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clubs.id", ondelete="CASCADE"), index=True)
    plan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("membership_plans.id", ondelete="RESTRICT"), index=True)
    payment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("payments.id", ondelete="CASCADE"), index=True)
    total_minutes: Mapped[int] = mapped_column(Integer)
    remaining_minutes: Mapped[int] = mapped_column(Integer)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    plan: Mapped[MembershipPlan] = relationship()
    club: Mapped[Club] = relationship()
    bookings: Mapped[list[Booking]] = relationship(back_populates="membership", foreign_keys="Booking.membership_id")
