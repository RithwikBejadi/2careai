from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models import Appointment, AppointmentStatus, Doctor, Patient, Slot


class ConflictError(Exception):
    def __init__(self, reason: str, alternatives: list[dict]) -> None:
        super().__init__(reason)
        self.reason = reason
        self.alternatives = alternatives


class SlotService:

    async def get_available_slots(
        self,
        db: AsyncSession,
        *,
        doctor_name: str = "",
        specialty: str = "",
        date_str: str = "",
        limit: int = 10,
    ) -> list[dict]:
        now = datetime.now(tz=timezone.utc)
        stmt = (
            select(Slot)
            .join(Slot.doctor)
            .where(
                Slot.is_booked == False,
                Slot.start_time > now,
                Doctor.is_available == True,
            )
            .options(selectinload(Slot.doctor))
            .order_by(Slot.start_time)
            .limit(limit)
        )
        if doctor_name:
            stmt = stmt.where(Doctor.name.ilike(f"%{doctor_name}%"))
        if specialty:
            stmt = stmt.where(Doctor.specialty.ilike(f"%{specialty}%"))
        if date_str:
            try:
                day = datetime.strptime(date_str, "%Y-%m-%d").replace(
                    hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc
                )
                stmt = stmt.where(
                    Slot.start_time >= day,
                    Slot.start_time < day + timedelta(days=1),
                )
            except ValueError:
                pass
        result = await db.execute(stmt)
        return [s.to_dict() for s in result.scalars().all()]

    async def get_patient_by_phone(
        self, db: AsyncSession, phone: str
    ) -> Optional[Patient]:
        result = await db.execute(
            select(Patient).where(Patient.phone == phone)
        )
        return result.scalar_one_or_none()

    async def get_patient_appointments(
        self,
        db: AsyncSession,
        patient_id: int,
        limit: int = 5,
    ) -> list[dict]:
        result = await db.execute(
            select(Appointment)
            .where(Appointment.patient_id == patient_id)
            .options(
                selectinload(Appointment.slot).selectinload(Slot.doctor)
            )
            .order_by(Appointment.created_at.desc())
            .limit(limit)
        )
        return [a.to_dict() for a in result.scalars().all()]

    async def book_appointment(
        self,
        db: AsyncSession,
        *,
        slot_id: int,
        patient_id: int,
        notes: Optional[str] = None,
    ) -> Appointment:
        
        result = await db.execute(
            select(Slot)
            .where(Slot.id == slot_id)
            .options(selectinload(Slot.doctor))
            .with_for_update()
        )
        slot: Optional[Slot] = result.scalar_one_or_none()

        if slot is None:
            raise ConflictError("Slot not found.", alternatives=[])

        now = datetime.now(tz=timezone.utc)
        slot_start = slot.start_time if slot.start_time.tzinfo else slot.start_time.replace(tzinfo=timezone.utc)
        slot_end = slot.end_time if slot.end_time.tzinfo else slot.end_time.replace(tzinfo=timezone.utc)

        if slot_start <= now:
            alts = await self._next_available(db, doctor_id=slot.doctor_id)
            raise ConflictError("That slot has already passed. Here are upcoming options.", alternatives=alts)

        if slot.doctor and not slot.doctor.is_available:
            alts = await self._same_specialty_slots(db, specialty=slot.doctor.specialty)
            raise ConflictError(
                f"Dr. {slot.doctor.name} is currently not accepting appointments.",
                alternatives=alts,
            )

        if slot.is_booked:
            alts = await self._nearest_open_slots(db, near_time=slot_start)
            raise ConflictError("That slot is already taken. Here are nearby available slots.", alternatives=alts)

        
        overlap_result = await db.execute(
            select(Appointment)
            .join(Appointment.slot)
            .where(
                Appointment.patient_id == patient_id,
                Appointment.status == AppointmentStatus.SCHEDULED,
                Slot.start_time < slot_end,
                Slot.end_time > slot_start,
            )
        )
        overlap = overlap_result.scalar_one_or_none()
        if overlap is not None:
            raise ConflictError(
                f"You already have an appointment at this time (ID {overlap.id}). Would you like to reschedule it?",
                alternatives=[overlap.to_dict()],
            )

        slot.is_booked = True
        appointment = Appointment(
            patient_id=patient_id,
            slot_id=slot_id,
            status=AppointmentStatus.SCHEDULED,
            notes=notes,
        )
        db.add(appointment)
        await db.commit()
        await db.refresh(appointment)
        return appointment

    async def cancel_appointment(
        self,
        db: AsyncSession,
        *,
        appointment_id: int,
        patient_id: int,
    ) -> Appointment:
        result = await db.execute(
            select(Appointment)
            .where(
                Appointment.id == appointment_id,
                Appointment.patient_id == patient_id,
            )
            .options(selectinload(Appointment.slot))
            .with_for_update()
        )
        appointment: Optional[Appointment] = result.scalar_one_or_none()
        if appointment is None:
            raise ConflictError(f"Appointment {appointment_id} not found for this patient.", alternatives=[])
        if appointment.status == AppointmentStatus.CANCELLED:
            raise ConflictError(f"Appointment {appointment_id} is already cancelled.", alternatives=[])

        appointment.status = AppointmentStatus.CANCELLED
        if appointment.slot:
            appointment.slot.is_booked = False
        await db.commit()
        await db.refresh(appointment)
        return appointment

    async def reschedule_appointment(
        self,
        db: AsyncSession,
        *,
        appointment_id: int,
        new_slot_id: int,
        patient_id: int,
    ) -> Appointment:
        
        old = await self.cancel_appointment(
            db, appointment_id=appointment_id, patient_id=patient_id
        )
        old.status = AppointmentStatus.RESCHEDULED
        await db.flush()

        
        new_appt = await self.book_appointment(
            db,
            slot_id=new_slot_id,
            patient_id=patient_id,
            notes=f"Rescheduled from appointment {appointment_id}",
        )
        await db.commit()
        return new_appt

    

    async def _next_available(self, db: AsyncSession, doctor_id: int, limit: int = 3) -> list[dict]:
        now = datetime.now(tz=timezone.utc)
        result = await db.execute(
            select(Slot)
            .where(
                Slot.doctor_id == doctor_id,
                Slot.is_booked == False,
                Slot.start_time > now,
            )
            .options(selectinload(Slot.doctor))
            .order_by(Slot.start_time)
            .limit(limit)
        )
        return [s.to_dict() for s in result.scalars().all()]

    async def _same_specialty_slots(self, db: AsyncSession, specialty: str, limit: int = 3) -> list[dict]:
        now = datetime.now(tz=timezone.utc)
        result = await db.execute(
            select(Slot)
            .join(Slot.doctor)
            .where(
                Doctor.specialty == specialty,
                Doctor.is_available == True,
                Slot.is_booked == False,
                Slot.start_time > now,
            )
            .options(selectinload(Slot.doctor))
            .order_by(Slot.start_time)
            .limit(limit)
        )
        return [s.to_dict() for s in result.scalars().all()]

    async def _nearest_open_slots(self, db: AsyncSession, near_time: datetime, limit: int = 3) -> list[dict]:
        now = datetime.now(tz=timezone.utc)
        result = await db.execute(
            select(Slot)
            .join(Slot.doctor)
            .where(
                Slot.is_booked == False,
                Slot.start_time > now,
                Doctor.is_available == True,
            )
            .options(selectinload(Slot.doctor))
            .order_by(func.abs(func.extract("epoch", Slot.start_time) - func.extract("epoch", near_time)))
            .limit(limit)
        )
        return [s.to_dict() for s in result.scalars().all()]


from sqlalchemy import func  

slot_service = SlotService()
