from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models import Appointment, AppointmentStatus, Language, Patient, Slot


async def get_patient_context(db: AsyncSession, patient_id: int) -> dict:
    """Fetch patient profile + last 3 appointments from Postgres."""
    result = await db.execute(select(Patient).where(Patient.id == patient_id))
    patient: Optional[Patient] = result.scalar_one_or_none()
    if patient is None:
        return {}

    appt_result = await db.execute(
        select(Appointment)
        .where(
            Appointment.patient_id == patient_id,
            Appointment.status.in_([AppointmentStatus.SCHEDULED, AppointmentStatus.COMPLETED]),
        )
        .options(selectinload(Appointment.slot).selectinload(Slot.doctor))
        .order_by(Appointment.created_at.desc())
        .limit(3)
    )
    appointments = [a.to_dict() for a in appt_result.scalars().all()]

    return {
        "patient": patient.to_dict(),
        "recent_appointments": appointments,
    }


async def update_language_preference(
    db: AsyncSession, patient_id: int, lang: str
) -> None:
    """Persist detected language back to the patient record."""
    try:
        lang_enum = Language(lang.lower())
    except ValueError:
        lang_enum = Language.EN

    result = await db.execute(select(Patient).where(Patient.id == patient_id))
    patient: Optional[Patient] = result.scalar_one_or_none()
    if patient and patient.language_preference != lang_enum:
        patient.language_preference = lang_enum
        await db.commit()


_ROLE_PROMPT = """\
You are a friendly and professional AI receptionist for a multi-specialty clinic.
Your job is to help patients book, cancel, or reschedule medical appointments via a voice call.

Core rules:
- Always be polite, concise, and empathetic.
- Keep responses short (1-3 sentences) — this is a voice call.
- Confirm every booking action before executing it.
- If a conflict occurs, immediately offer alternatives.
- Never reveal patient information belonging to a different patient.
- Always respond in the language the patient is speaking."""


def build_system_prompt(
    patient_ctx: dict,
    recent_turns: list[dict],
    lang: str = "en",
) -> str:
    """Assemble the system prompt including patient history and recent session turns."""
    parts = [_ROLE_PROMPT]

    if patient_ctx:
        patient = patient_ctx.get("patient", {})
        appointments = patient_ctx.get("recent_appointments", [])

        parts.append(f"\n## Patient Profile\nName: {patient.get('name', 'Unknown')}")
        parts.append(f"Language preference: {lang.upper()}")

        if appointments:
            appt_lines = []
            for a in appointments:
                appt_lines.append(
                    f"  - {a.get('status','').upper()} | {a.get('doctor_name','?')} | {a.get('start_time','?')[:16] if a.get('start_time') else '?'}"
                )
            parts.append("Recent appointments:\n" + "\n".join(appt_lines))
        else:
            parts.append("No previous appointments on record.")

    # Inject last 6 turns for context continuity
    if recent_turns:
        turns_to_inject = recent_turns[-6:]
        turn_text = "\n".join(
            f"  {t['role'].capitalize()}: {t['content']}" for t in turns_to_inject
        )
        parts.append(f"\n## Recent Conversation\n{turn_text}")

    return "\n".join(parts)
