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

BRO_PRICE_MENU = {
    "currency": "KZT",
    "holiday_note": "В праздничные выходные действует цена выходного дня.",
    "tiers": [
        {
            "name": "STANDARD",
            "weekdays": {
                "day_hours": "11:00–18:00", "day_price": 1800, "hourly": 1100,
                "deals": [{"label": "2+1", "price": 2200}, {"label": "3+2", "price": 3300}],
                "night_hours": "22:00–08:00", "night_price": 3600,
                "turbo_hours": "00:00–08:00", "turbo_price": 2400,
            },
            "weekends": {
                "day_hours": "11:00–18:00", "day_price": 2000, "hourly": 1300,
                "deals": [{"label": "2+1", "price": 2600}, {"label": "3+2", "price": 3900}],
                "night_hours": "22:00–08:00", "night_price": 3900,
                "turbo_hours": "00:00–08:00", "turbo_price": 3000,
            },
        },
        {
            "name": "BOOTCAMP",
            "weekdays": {
                "day_hours": "11:00–18:00", "day_price": 2400, "hourly": 1500,
                "deals": [{"label": "2+1", "price": 3000}, {"label": "3+2", "price": 4500}],
                "night_hours": "22:00–08:00", "night_price": 4800,
                "turbo_hours": "00:00–08:00", "turbo_price": 3200,
            },
            "weekends": {
                "day_hours": "11:00–18:00", "day_price": 2700, "hourly": 1900,
                "deals": [{"label": "2+1", "price": 3800}, {"label": "3+2", "price": 5700}],
                "night_hours": "22:00–08:00", "night_price": 5300,
                "turbo_hours": "00:00–08:00", "turbo_price": 3900,
            },
        },
    ],
}


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
        owner = users[UserRole.OWNER]
        await session.flush()
        has_clubs = await session.scalar(select(Club.id).limit(1)) is not None
        if not has_clubs:
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

        bro = await session.scalar(select(Club).where(Club.name == "BRO", Club.city == "Astana"))
        if bro is None:
            session.add(Club(
                owner=owner,
                name="BRO",
                city="Astana",
                address="Адрес уточняется",
                description="Компьютерный клуб BRO. Актуальный прайс на Standard и Bootcamp.",
                timezone="Asia/Almaty",
                phone="Телефон уточняется",
                price_menu=BRO_PRICE_MENU,
            ))
        else:
            bro.price_menu = BRO_PRICE_MENU
            bro.address = "Адрес уточняется"
            bro.phone = "Телефон уточняется"
        await session.commit()


if __name__ == "__main__":
    asyncio.run(seed())
