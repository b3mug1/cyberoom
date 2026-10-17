"""PostgreSQL races between online reservations and staff actions.

Set TEST_DATABASE_URL to a disposable database to run these integration tests.
"""

import asyncio
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import Base, Booking, BookingSource, BookingStatus, Club, Computer, ComputerStatus, Session, StaffAssignment, Tariff, User, UserRole
from app.schemas import BookingCreate, SessionExtend, WalkInCreate
from app.services.bookings import club_availability, create_booking, create_walk_in
from app.services.errors import ServiceError
from app.services.role_workflows import staff_session_action

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="Set TEST_DATABASE_URL to a disposable PostgreSQL database")


async def setup_club(sessions):
    suffix = os.urandom(6).hex()
    async with sessions() as db:
        owner = User(email=f"owner-{suffix}@example.com", username=f"owner-{suffix}", full_name="Owner", password_hash="unused", role=UserRole.OWNER)
        staff = User(email=f"staff-{suffix}@example.com", username=f"staff-{suffix}", full_name="Staff", password_hash="unused", role=UserRole.STAFF)
        player = User(email=f"player-{suffix}@example.com", username=f"player-{suffix}", full_name="Player", password_hash="unused", role=UserRole.USER)
        db.add_all([owner, staff, player])
        await db.flush()
        club = Club(owner_id=owner.id, name=f"Race {suffix}", city="Astana", address="Test", description="", phone="")
        db.add(club)
        await db.flush()
        computer = Computer(club_id=club.id, name="PC", cpu="CPU", gpu="GPU", ram_gb=32, storage="1 TB", monitor="QHD", refresh_rate=240)
        db.add_all([computer, StaffAssignment(staff_user_id=staff.id, club_id=club.id),
                    Tariff(club_id=club.id, name="All day", price_per_hour=Decimal("600"),
                           start_time=datetime.min.time(), end_time=datetime.max.time())])
        await db.commit()
        return owner.id, staff.id, player.id, club.id, computer.id


async def cleanup_club(sessions, ids):
    owner_id, staff_id, player_id, club_id, computer_id = ids
    async with sessions() as db:
        booking_ids = select(Booking.id).where(Booking.computer_id == computer_id)
        await db.execute(delete(Session).where(Session.booking_id.in_(booking_ids)))
        await db.execute(delete(Booking).where(Booking.computer_id == computer_id))
        await db.execute(delete(StaffAssignment).where(StaffAssignment.club_id == club_id))
        await db.execute(delete(Tariff).where(Tariff.club_id == club_id))
        await db.execute(delete(Computer).where(Computer.id == computer_id))
        await db.execute(delete(Club).where(Club.id == club_id))
        await db.execute(delete(User).where(User.id.in_([owner_id, staff_id, player_id])))
        await db.commit()


async def run_race(action):
    assert TEST_DATABASE_URL is not None
    engine = create_async_engine(TEST_DATABASE_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.execute(text("CREATE EXTENSION IF NOT EXISTS btree_gist"))
        await connection.run_sync(Base.metadata.create_all)
    ids = await setup_club(sessions)
    try:
        await action(sessions, ids)
    finally:
        await cleanup_club(sessions, ids)
        await engine.dispose()


def minute_after(minutes: int) -> datetime:
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes + 1)).replace(second=0, microsecond=0)


@pytest.mark.asyncio
async def test_online_and_walk_in_cannot_take_same_interval() -> None:
    async def race(sessions, ids):
        _, staff_id, player_id, _, computer_id = ids
        online_start = minute_after(20)
        online_end = minute_after(80)
        walk_in_end = minute_after(60)

        async def online():
            async with sessions() as db:
                return await create_booking(db, await db.get(User, player_id),
                                            BookingCreate(computer_id=computer_id, start_time=online_start, end_time=online_end))

        async def walk_in():
            async with sessions() as db:
                return await create_walk_in(db, await db.get(User, staff_id),
                                            WalkInCreate(computer_id=computer_id, guest_name="Guest", end_time=walk_in_end))

        results = await asyncio.gather(online(), walk_in(), return_exceptions=True)
        assert sum(isinstance(result, Booking) for result in results) == 1
        assert [result.code for result in results if isinstance(result, ServiceError)] == ["BOOKING_CONFLICT"]
        async with sessions() as db:
            assert await db.scalar(select(func.count(Booking.id)).where(Booking.computer_id == computer_id)) == 1

    await run_race(race)


@pytest.mark.asyncio
async def test_extension_races_with_next_online_booking() -> None:
    async def race(sessions, ids):
        _, staff_id, player_id, _, computer_id = ids
        async with sessions() as db:
            active = await create_walk_in(db, await db.get(User, staff_id),
                                          WalkInCreate(computer_id=computer_id, guest_name="Guest", end_time=minute_after(30)))

        async def extend():
            async with sessions() as db:
                return await staff_session_action(db, await db.get(User, staff_id), active.id, "extend",
                                                  SessionExtend(end_time=minute_after(60)))

        async def online():
            async with sessions() as db:
                return await create_booking(db, await db.get(User, player_id),
                                            BookingCreate(computer_id=computer_id,
                                                          start_time=minute_after(40), end_time=minute_after(80)))

        results = await asyncio.gather(extend(), online(), return_exceptions=True)
        assert sum(not isinstance(result, Exception) for result in results) == 1
        assert [result.code for result in results if isinstance(result, ServiceError)] == ["BOOKING_CONFLICT"]

    await run_race(race)


@pytest.mark.asyncio
async def test_overdue_session_blocks_new_booking_until_staff_ends_it() -> None:
    async def scenario(sessions, ids):
        _, staff_id, player_id, club_id, computer_id = ids
        now = datetime.now(timezone.utc)
        async with sessions() as db:
            old = Booking(user_id=player_id, source=BookingSource.ONLINE, computer_id=computer_id,
                          start_time=now - timedelta(hours=2), end_time=now - timedelta(hours=1),
                          status=BookingStatus.ACTIVE, total_price=Decimal("600"))
            db.add(old)
            await db.flush()
            db.add(Session(booking_id=old.id, started_at=old.start_time, started_by_user_id=staff_id))
            computer = await db.get(Computer, computer_id)
            computer.status = ComputerStatus.OCCUPIED
            await db.commit()
            old_id = old.id

        async with sessions() as db:
            availability = await club_availability(db, club_id, now, now + timedelta(hours=2))
            assert availability.computers[0].busy[0].end_time == now + timedelta(hours=2)
            with pytest.raises(ServiceError, match="overdue") as error:
                await create_booking(db, await db.get(User, player_id), BookingCreate(
                    computer_id=computer_id, start_time=minute_after(10), end_time=minute_after(30)))
            assert error.value.code == "SESSION_OVERDUE"

        async with sessions() as db:
            ended = await staff_session_action(db, await db.get(User, staff_id), old_id, "end")
            assert ended.status == BookingStatus.COMPLETED
            actual = await db.scalar(select(Session).where(Session.booking_id == old_id))
            assert actual.ended_at is not None

        async with sessions() as db:
            created = await create_booking(db, await db.get(User, player_id), BookingCreate(
                computer_id=computer_id, start_time=minute_after(10), end_time=minute_after(30)))
            assert created.status == BookingStatus.CONFIRMED

    await run_race(scenario)
