import asyncio
from decimal import Decimal
from datetime import time

from sqlalchemy import select

from app.core.security import hash_password
from app.db import SessionFactory
from app.models import Club, Computer, ComputerStatus, Tariff, User, UserRole

CLUBS = [
    ("Nexus Station", "Astana", "Qabanbay Batyr Ave 21", "Next-generation gaming in the capital."),
    ("Pixel Forge", "Almaty", "Abay Ave 150", "A focused arena for competitive play."),
    ("Checkpoint 01", "Shymkent", "Tauke Khan Ave 88", "A friendly local club with high-refresh setups."),
    ("Frame Perfect", "Karaganda", "Bukhar-Zhyrau Ave 56", "Tournament-ready PCs and private team rooms."),
    ("Northstar Gaming", "Pavlodar", "Lermontov St 12", "Premium hardware, relaxed late-night sessions."),
]


async def seed() -> None:
    async with SessionFactory() as session:
        demo_users = [
            ("owner@example.com", "clubowner", "CyberBook Owner", UserRole.OWNER),
            ("admin@example.com", "platformadmin", "Platform Admin", UserRole.ADMIN),
            ("player@example.com", "playerone", "Test Player", UserRole.USER),
            ("staff@example.com", "clubstaff", "CyberBook Staff", UserRole.STAFF),
        ]
        users = {}
        for email, username, full_name, role in demo_users:
            account = await session.scalar(select(User).where(User.email == email))
            if account is None:
                account = User(email=email, username=username, full_name=full_name, password_hash=hash_password("CyberBook!2026"), role=role)
                session.add(account)
            users[role] = account
        await session.flush()
        if await session.scalar(select(Club.id).limit(1)) is not None:
            await session.commit()
            return

        owner = users[UserRole.OWNER]
        await session.flush()
        gpus = ["GeForce RTX 4070", "GeForce RTX 4060 Ti", "GeForce RTX 4080", "Radeon RX 7800 XT", "GeForce RTX 4070 SUPER"]
        cpus = ["Ryzen 7 7800X3D", "Intel Core i7-14700K", "Ryzen 5 7600X", "Intel Core i5-14600KF"]
        for club_index, (name, city, address, description) in enumerate(CLUBS):
            club = Club(owner=owner, name=name, city=city, address=address, description=description, phone="+7 700 000 00 00")
            club.tariffs = [
                Tariff(name="Night", price_per_hour=Decimal("700"), start_time=time(0), end_time=time(6)),
                Tariff(name="Standard", price_per_hour=Decimal("800"), start_time=time(6), end_time=time(18)),
                Tariff(name="Prime", price_per_hour=Decimal("1200"), start_time=time(18), end_time=time(0)),
            ]
            club.computers = [
                Computer(
                    name=f"PC-{number + 1:02d}",
                    cpu=cpus[(number + club_index) % len(cpus)],
                    gpu=gpus[(number + club_index) % len(gpus)],
                    ram_gb=(32 if number % 3 else 64),
                    storage="1 TB NVMe SSD",
                    monitor="27-inch QHD",
                    refresh_rate=(240 if number % 2 else 360),
                    status=ComputerStatus.AVAILABLE,
                )
                for number in range(10)
            ]
            session.add(club)
        await session.commit()


if __name__ == "__main__":
    asyncio.run(seed())