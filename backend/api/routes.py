from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from memory.redis_client import ping_redis
from models import Appointment, AppointmentStatus, Doctor, Patient, Slot

router = APIRouter()

_LATENCY_LOG_PATH = Path(__file__).parent.parent / "latency_logs.jsonl"

import asyncio
from typing import Any

_active_calls: dict[str, dict[str, Any]] = {}
_transcript_store: dict[str, list[dict]] = {}

def register_call(session_id: str, to_phone: str) -> None:
    _active_calls[session_id] = {"to": to_phone, "active": True, "started_at": __import__('time').time()}
    _transcript_store[session_id] = []

def add_transcript(session_id: str, speaker: str, text: str) -> None:
    if session_id in _transcript_store:
        _transcript_store[session_id].append({"speaker": speaker, "text": text})

def end_call(session_id: str) -> None:
    if session_id in _active_calls:
        _active_calls[session_id]["active"] = False



@router.get("/health")
def health():
    return {"status": "healthy"}


@router.get("/redis/health")
def redis_health() -> dict[str, bool]:
    return {"ok": ping_redis()}



@router.get("/doctors")
async def list_doctors(
    db: Annotated[AsyncSession, Depends(get_db)],
    available_only: bool = False,
) -> list[dict]:
    stmt = select(Doctor)
    if available_only:
        stmt = stmt.where(Doctor.is_available == True)
    result = await db.execute(stmt.order_by(Doctor.name))
    return [d.to_dict() for d in result.scalars().all()]



@router.get("/slots")
async def list_slots(
    db: Annotated[AsyncSession, Depends(get_db)],
    doctor_id: Optional[int] = Query(None),
    available_only: bool = True,
) -> list[dict]:
    stmt = select(Slot)
    if available_only:
        stmt = stmt.where(Slot.is_booked == False)
    if doctor_id:
        stmt = stmt.where(Slot.doctor_id == doctor_id)
    result = await db.execute(stmt.order_by(Slot.start_time).limit(50))
    return [s.to_dict() for s in result.scalars().all()]



@router.get("/patients")
async def list_patients(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[dict]:
    result = await db.execute(select(Patient).order_by(Patient.name))
    return [p.to_dict() for p in result.scalars().all()]


@router.get("/patients/{patient_id}")
async def get_patient(
    patient_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    result = await db.execute(select(Patient).where(Patient.id == patient_id))
    patient = result.scalar_one_or_none()
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    return patient.to_dict()



@router.get("/appointments")
async def list_appointments(
    db: Annotated[AsyncSession, Depends(get_db)],
    status: Optional[str] = Query(None),
    limit: int = Query(20, le=100),
) -> list[dict]:
    stmt = select(Appointment).order_by(Appointment.created_at.desc()).limit(limit)
    if status:
        try:
            stmt = stmt.where(Appointment.status == AppointmentStatus(status))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
    result = await db.execute(stmt)
    return [a.to_dict() for a in result.scalars().all()]



@router.get("/latency")
def latency(n: int = Query(1, ge=1, le=100)):
    if not _LATENCY_LOG_PATH.exists():
        return {"latency_ms": 0, "history": []}
    lines = _LATENCY_LOG_PATH.read_text(encoding="utf-8").splitlines()
    if not lines:
        return {"latency_ms": 0, "history": []}
    entries = []
    for line in reversed(lines[-n:]):
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    latest_ms = entries[0].get("total_ms", 0) if entries else 0
    return {"latency_ms": latest_ms, "history": entries}



@router.post("/twilio/voice")
async def twilio_voice(request: Request):
    """Return TwiML connecting Twilio call to the WebSocket media stream."""
    host = (
        request.headers.get("X-Forwarded-Host")
        or request.headers.get("Host", "localhost:8000")
    )
    proto = request.headers.get("X-Forwarded-Proto", "http")
    ws_scheme = "wss" if proto == "https" else "ws"
    ws_url = f"{ws_scheme}://{host}/ws/call"
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="{ws_url}"/>
    </Connect>
</Response>"""
    return Response(content=twiml, media_type="text/xml")



@router.post("/campaigns/trigger")
async def trigger_campaign(
    db: Annotated[AsyncSession, Depends(get_db)],
    patient_id: int,
    appointment_id: int,
):
    """Manually trigger a reminder call for a specific appointment."""
    from campaigns.tasks import send_reminder
    send_reminder.delay(patient_id, appointment_id)
    return {"status": "queued", "patient_id": patient_id, "appointment_id": appointment_id}


@router.api_route("/call", methods=["GET", "POST"])
async def call_number(to: str):
    """
    Trigger an outbound call to any E.164 phone number (e.g. +919876543210).
    Twilio will call the number and connect it to the AI voice agent.
    """
    from campaigns.outbound import outbound_call_service
    try:
        call_sid = await outbound_call_service.make_call(
            to_phone=to,
            patient_id=0,
            appointment_id=0,
        )
        if call_sid:
            register_call(call_sid, to)
            return {"status": "calling", "to": to, "call_sid": call_sid}
        return {"status": "failed", "to": to, "detail": "Twilio did not return a SID"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}



@router.get("/bookings")
async def list_bookings(
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(20, le=100),
) -> list[dict]:
    stmt = select(Appointment).order_by(Appointment.created_at.desc()).limit(limit)
    result = await db.execute(stmt)
    return [a.to_dict() for a in result.scalars().all()]



@router.get("/call-status")
def get_call_status() -> dict:
    import time
    active = [
        {"session_id": sid, "to": info["to"], "elapsed_s": round(time.time() - info["started_at"])}
        for sid, info in _active_calls.items()
        if info.get("active")
    ]
    most_recent = max(
        _active_calls.items(),
        key=lambda kv: kv[1]["started_at"],
        default=(None, {})
    )
    return {
        "is_active": len(active) > 0,
        "active_calls": active,
        "latest_session_id": most_recent[0],
    }



@router.get("/transcript")
def get_transcript(session_id: Optional[str] = Query(None)) -> dict:
    if not session_id:
        latest = max(
            _active_calls.items(),
            key=lambda kv: kv[1]["started_at"],
            default=(None, {})
        )
        session_id = latest[0]

    if not session_id or session_id not in _transcript_store:
        return {"session_id": session_id, "turns": []}

    return {
        "session_id": session_id,
        "is_active": _active_calls.get(session_id, {}).get("active", False),
        "turns": _transcript_store[session_id]
    }



@router.get("/langsmith/runs")
async def get_langsmith_runs(limit: int = Query(20, le=100)):
    """Fetch exact conversation history (Human vs AI) directly from LangSmith traces."""
    try:
        from langsmith import Client
        from config import settings
        
        client = Client()
        runs_iter = client.list_runs(
            project_name=settings.LANGCHAIN_PROJECT,
            is_root=True,
            limit=limit,
            execution_order=1
        )
        
        history = []
        for run in runs_iter:
            messages = []
            try:
                inputs = run.inputs or {}
                outputs = run.outputs or {}
                
                def extract_text(m):
                    if isinstance(m, dict):
                        return m.get("content") or m.get("text") or str(m)
                    elif hasattr(m, "content"):
                        return m.content
                    return str(m)
                
                user_msg = inputs.get("messages", [])
                if isinstance(user_msg, list) and len(user_msg) > 0:
                    user_text = extract_text(user_msg[-1])
                    messages.append({"role": "user", "text": user_text})
                
                ai_msg = outputs.get("messages", [])
                if isinstance(ai_msg, list) and len(ai_msg) > 0:
                    ai_text = extract_text(ai_msg[-1])
                    if hasattr(ai_msg[-1], "response_metadata") and ai_msg[-1].response_metadata:
                          # Sometimes the AI message has metadata, but we just want content
                          pass
                    messages.append({"role": "ai", "text": ai_text})
                    
            except Exception:
                pass

            history.append({
                "id": str(run.id),
                "name": run.name,
                "start_time": run.start_time.isoformat() if run.start_time else None,
                "status": run.status,
                "messages": messages,
                "latency_ms": getattr(run, "latency", 0) * 1000 if hasattr(run, "latency") and run.latency else 0
            })
            
        return {"runs": history}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": str(e)}
