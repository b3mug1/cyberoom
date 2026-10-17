import asyncio
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import Base, Booking, BookingStatus, Club, Computer, Tariff, User, UserRole
from app.schemas import BookingCreate
from app.services.bookings import create_booking
from app.services.errors import ServiceError

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="Set TEST_DATABASE_URL to run PostgreSQL concurrency integration test")


@pytest.mark.asyncio
async def test_simultaneous_overlapping_bookings_only_allow_one() -> None:
    assert TEST_DATABASE_URL is not None
    engine = create_async_engine(TEST_DATABASE_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.execute(text("CREATE EXTENSION IF NOT EXISTS btree_gist"))
        await connection.run_sync(Base.metadata.create_all)

    suffix = os.urandom(6).hex()
    async with sessions() as session:
        owner = User(email=f"owner-{suffix}@test.invalid", username=f"owner-{suffix}", full_name="Test Owner", password_hash="unused", role=UserRole.OWNER)
        players = [User(email=f"player-{suffix}-{index}@test.invalid", username=f"player-{suffix}-{index}", full_name="Test Player", password_hash="unused") for index in range(2)]
        session.add_all([owner, *players])
        await session.flush()
        club = Club(owner_id=owner.id, name=f"Concurrency {suffix}", city="Astana", address="Test address", description="", phone="")
        session.add(club)
        await session.flush()
        computer = Computer(club_id=club.id, name="PC-01", cpu="Test CPU", gpu="Test GPU", ram_gb=32, storage="1 TB", monitor="QHD", refresh_rate=240)
        session.add_all([computer, Tariff(club_id=club.id, name="All day", price_per_hour=Decimal("800"), start_time=datetime.min.time(), end_time=datetime.max.time())])
        await session.commit()
        computer_id = computer.id
        user_ids = [player.id for player in players]

    start = (datetime.now(timezone.utc) + timedelta(hours=1)).replace(second=0, microsecond=0)
    payload = BookingCreate(computer_id=computer_id, start_time=start, end_time=start + timedelta(hours=1))

    async def attempt(user_id) -> str:
        async with sessions() as session:
            user = await session.get(User, user_id)
            try:
                await create_booking(session, user, payload)
                return "created"
            except ServiceError as error:
                assert error.code == "BOOKING_CONFLICT"
                return "conflict"

    results = await asyncio.gather(*(attempt(user_id) for user_id in user_ids))
    assert sorted(results) == ["conflict", "created"]

    async with sessions() as session:
        count = await session.scalar(select_booking_count(computer_id, start))
        assert count == 1
        await session.execute(delete(Booking).where(Booking.computer_id == computer_id))
        await session.execute(delete(Computer).where(Computer.id == computer_id))
        await session.execute(delete(Tariff).where(Tariff.club_id == club.id))
        await session.execute(delete(Club).where(Club.id == club.id))
        await session.execute(delete(User).where(User.id.in_([owner.id, *user_ids])))
        await session.commit()
    await engine.dispose()


def select_booking_count(computer_id, start):
    from sqlalchemy import func, select

    return select(func.count(Booking.id)).where(Booking.computer_id == computer_id, Booking.start_time == start, Booking.status == BookingStatus.CONFIRMED)