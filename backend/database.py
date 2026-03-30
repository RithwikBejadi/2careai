from __future__ import annotations

import logging
import re
import ssl
from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config import settings
from models import (
    Appointment,
    AppointmentStatus,
    Base,
    CampaignLog,
    Doctor,
    Language,
    Patient,
    Slot,
)

logger = logging.getLogger(__name__)

def _make_asyncpg_url(url: str) -> str:
    url = url.replace("postgresql://", "postgresql+asyncpg://")
    url = url.replace("postgres://", "postgresql+asyncpg://")
    url = re.sub(r"[?&]sslmode=[^&]*", "", url)
    url = re.sub(r"[?&]channel_binding=[^&]*", "", url)
    url = re.sub(r"\?$", "", url)
    return url

_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE

_engine = create_async_engine(
    _make_asyncpg_url(settings.DATABASE_URL),
    connect_args={
        "ssl": _ssl_ctx,
        "command_timeout": 10,
        "server_settings": {
            "tcp_keepalives_idle": "30",
            "tcp_keepalives_interval": "10",
            "tcp_keepalives_count": "5",
        }
    },
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
    pool_recycle=300,
    echo=False,
)

_SessionFactory = async_sessionmaker(_engine, expire_on_commit=False, class_=AsyncSession)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with _SessionFactory() as session:
        yield session


class Seeder:
    async def seed(self, db: AsyncSession) -> None:
        await self._seed_doctors(db)
        await self._seed_patients(db)
        await self._seed_slots(db)

    async def _seed_doctors(self, db: AsyncSession) -> None:
        result = await db.execute(select(Doctor))
        if result.scalars().first():
            return
        doctors = [
            Doctor(name="Dr. Arjun Kumar",  specialty="General Practitioner", is_available=True),
            Doctor(name="Dr. Priya Sharma", specialty="Cardiology",           is_available=True),
            Doctor(name="Dr. Rajan Iyer",   specialty="Orthopedic",           is_available=True),
            Doctor(name="Dr. Sunita Rao",   specialty="Gynecology",           is_available=False),
        ]
        db.add_all(doctors)
        await db.flush()
        logger.info("[seeder] seeded %d doctors", len(doctors))

    async def _seed_patients(self, db: AsyncSession) -> None:
        result = await db.execute(select(Patient))
        if result.scalars().first():
            return
        patients = [
            Patient(name="Amit Verma",   phone="+919876543210", language_preference=Language.HI),
            Patient(name="Tamil Arasan", phone="+919876543211", language_preference=Language.TA),
            Patient(name="John Mathew",  phone="+919876543212", language_preference=Language.EN),
        ]
        db.add_all(patients)
        await db.flush()
        logger.info("[seeder] seeded %d patients", len(patients))

    async def _seed_slots(self, db: AsyncSession) -> None:
        result = await db.execute(select(Slot))
        if result.scalars().first():
            return
        result = await db.execute(select(Doctor).where(Doctor.is_available == True))
        available_doctors = result.scalars().all()

        slot_times = [
            (3, 30),   
            (5, 30),   
            (7, 30),
        ]
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        slots = []
        for day_offset in range(7):
            day = today + timedelta(days=day_offset)
            for doctor in available_doctors:
                for hour, minute in slot_times:
                    start = day.replace(hour=hour, minute=minute)
                    end = start + timedelta(minutes=30)
                    slots.append(Slot(doctor_id=doctor.id, start_time=start, end_time=end, is_booked=False))

        db.add_all(slots)
        await db.flush()
        logger.info("[seeder] seeded %d slots", len(slots))


async def init_db() -> None:
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with _SessionFactory() as db:
        async with db.begin():
            await Seeder().seed(db)
    logger.info("[db] initialized")
