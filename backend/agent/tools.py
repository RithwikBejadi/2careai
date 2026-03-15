from __future__ import annotations

import contextvars
import json
from typing import Optional

from langchain_core.tools import tool
from sqlalchemy.ext.asyncio import AsyncSession

from memory.longterm import update_language_preference
from memory.session import session_memory
from scheduling.slots import ConflictError, slot_service

# ── Per-request context vars ─────────────────────────────────────────────────
_db_ctx: contextvars.ContextVar[Optional[AsyncSession]] = contextvars.ContextVar(
    "db", default=None
)
_session_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar(
    "session_id", default=""
)
_patient_id_ctx: contextvars.ContextVar[Optional[int]] = contextvars.ContextVar(
    "patient_id", default=None
)


def set_tool_context(
    db: Optional[AsyncSession], session_id: str, patient_id: Optional[int]
) -> None:
    """Must be called before each agent.ainvoke() to wire DB + session into tools."""
    _db_ctx.set(db)
    _session_id_ctx.set(session_id)
    _patient_id_ctx.set(patient_id)


def _detect_language(text: str) -> str:
    """Detect language from Unicode character ranges (per-character scan)."""
    for ch in text:
        cp = ord(ch)
        if 0x0B80 <= cp <= 0x0BFF:
            return "ta"   # Tamil
        if 0x0900 <= cp <= 0x097F:
            return "hi"   # Devanagari (Hindi)
    return "en"            # English fallback


# ── Tools ────────────────────────────────────────────────────────────────────

@tool
async def check_availability(
    doctor_name: str = "",
    specialty: str = "",
    date: str = "",
) -> str:
    """Check available appointment slots. Filter by doctor_name, specialty, or date (YYYY-MM-DD)."""
    db = _db_ctx.get()
    if db is None:
        return "Database unavailable. Cannot check slots."

    slots = await slot_service.get_available_slots(
        db, doctor_name=doctor_name, specialty=specialty, date_str=date, limit=8
    )
    if not slots:
        return "No available slots found for the given criteria."

    lines = [f"Slot {s['id']}: {s['doctor_name']} ({s['specialty']}) — {s['start_time'][:16]}" for s in slots]
    return "Available slots:\n" + "\n".join(lines) + "\nPlease tell me the slot ID you prefer."


@tool
async def book_appointment(slot_id: int, notes: str = "") -> str:
    """Book an appointment for the current patient using a slot_id from check_availability."""
    db = _db_ctx.get()
    patient_id = _patient_id_ctx.get()
    session_id = _session_id_ctx.get()

    if db is None:
        return "Database unavailable. Cannot book appointment."
    if patient_id is None:
        return "Patient not identified. Please provide your phone number first."

    try:
        appt = await slot_service.book_appointment(
            db, slot_id=slot_id, patient_id=patient_id, notes=notes or None
        )
        msg = (
            f"Appointment booked! ID: {appt.id}. "
            f"Doctor: {appt.to_dict().get('doctor_name','?')}. "
            f"Time: {appt.to_dict().get('start_time','?')[:16] if appt.to_dict().get('start_time') else '?'}. "
            "Is there anything else I can help you with?"
        )
        if session_id:
            await session_memory.add_turn(session_id, "tool", f"Booked appointment {appt.id}")
        return msg
    except ConflictError as e:
        alts = ""
        if e.alternatives:
            alts = " Alternatives: " + ", ".join(
                f"Slot {a['id']} ({a.get('start_time','?')[:16]})" for a in e.alternatives
            )
        return f"{e.reason}{alts}"


@tool
async def cancel_appointment(appointment_id: int) -> str:
    """Cancel an existing appointment by its ID."""
    db = _db_ctx.get()
    patient_id = _patient_id_ctx.get()
    session_id = _session_id_ctx.get()

    if db is None:
        return "Database unavailable. Cannot cancel appointment."
    if patient_id is None:
        return "Patient not identified."

    try:
        appt = await slot_service.cancel_appointment(
            db, appointment_id=appointment_id, patient_id=patient_id
        )
        msg = f"Appointment {appt.id} has been cancelled. Would you like to reschedule?"
        if session_id:
            await session_memory.add_turn(session_id, "tool", f"Cancelled appointment {appt.id}")
        return msg
    except ConflictError as e:
        return e.reason


@tool
async def reschedule_appointment(appointment_id: int, new_slot_id: int) -> str:
    """Reschedule an existing appointment to a new slot."""
    db = _db_ctx.get()
    patient_id = _patient_id_ctx.get()
    session_id = _session_id_ctx.get()

    if db is None:
        return "Database unavailable. Cannot reschedule."
    if patient_id is None:
        return "Patient not identified."

    try:
        new_appt = await slot_service.reschedule_appointment(
            db,
            appointment_id=appointment_id,
            new_slot_id=new_slot_id,
            patient_id=patient_id,
        )
        info = new_appt.to_dict()
        msg = (
            f"Rescheduled! New appointment ID: {new_appt.id}. "
            f"Doctor: {info.get('doctor_name','?')}. "
            f"Time: {info.get('start_time','?')[:16] if info.get('start_time') else '?'}. "
            "Is there anything else?"
        )
        if session_id:
            await session_memory.add_turn(session_id, "tool", f"Rescheduled to appointment {new_appt.id}")
        return msg
    except ConflictError as e:
        alts = ""
        if e.alternatives:
            alts = " Alternatives: " + ", ".join(
                f"Slot {a['id']} ({a.get('start_time','?')[:16]})" for a in e.alternatives
            )
        return f"{e.reason}{alts}"


@tool
async def get_patient_context() -> str:
    """Get the current patient's profile and recent appointment history."""
    db = _db_ctx.get()
    patient_id = _patient_id_ctx.get()

    if db is None or patient_id is None:
        return "No patient record found. This may be a new patient."

    from memory.longterm import get_patient_context as _get_ctx
    ctx = await _get_ctx(db, patient_id)
    if not ctx:
        return "No patient record found. This appears to be a new patient."

    patient = ctx.get("patient", {})
    appointments = ctx.get("recent_appointments", [])

    lines = [f"Patient: {patient.get('name')} | Language: {patient.get('language_preference','en').upper()}"]
    if appointments:
        lines.append("Recent appointments:")
        for a in appointments:
            lines.append(f"  - {a.get('status','').upper()} | {a.get('doctor_name','?')} | {a.get('start_time','?')[:16] if a.get('start_time') else '?'}")
    else:
        lines.append("No prior appointments.")
    return "\n".join(lines)


@tool
async def detect_and_set_language(transcript: str) -> str:
    """Detect the patient's language from their speech and update session + DB preference."""
    lang = _detect_language(transcript)
    session_id = _session_id_ctx.get()
    db = _db_ctx.get()
    patient_id = _patient_id_ctx.get()

    if session_id:
        await session_memory.set_language(session_id, lang)
    if db and patient_id:
        await update_language_preference(db, patient_id, lang)

    lang_names = {"en": "English", "hi": "Hindi", "ta": "Tamil"}
    return f"Language set to {lang_names.get(lang, 'English')}."


ALL_TOOLS = [
    check_availability,
    book_appointment,
    cancel_appointment,
    reschedule_appointment,
    get_patient_context,
    detect_and_set_language,
]
