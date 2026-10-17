import enum
import uuid
from datetime import datetime, time, timezone
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum, ForeignKey, Integer, Numeric, String, Time, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import ExcludeConstraint, UUID
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
    latitude: Mapped[float | None]
    longitude: Mapped[float | None]
    phone: Mapped[str] = mapped_column(String(32), default="")
    opening_time: Mapped[time] = mapped_column(Time, default=time(0, 0))
    closing_time: Mapped[time] = mapped_column(Time, default=time(23, 59))
    rating: Mapped[Decimal] = mapped_column(Numeric(3, 2), default=Decimal("0"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    owner: Mapped[User] = relationship(back_populates="clubs")
    computers: Mapped[list["Computer"]] = relationship(back_populates="club", cascade="all, delete-orphan")
    tariffs: Mapped[list["Tariff"]] = relationship(back_populates="club", cascade="all, delete-orphan")


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
    qr_token: Mapped[str] = mapped_column(String(64), unique=True, index=True, default=lambda: uuid.uuid4().hex)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    user: Mapped[User | None] = relationship(back_populates="bookings")
    computer: Mapped[Computer] = relationship(back_populates="bookings")
    session: Mapped["Session | None"] = relationship(back_populates="booking", uselist=False)


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
