from __future__ import annotations

import asyncio
import base64
import json
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from database import _SessionFactory
from memory.session import session_memory
from models import Patient
from voice.pipeline import voice_pipeline
from voice.stt import deepgram_stt
from voice.tts import elevenlabs_tts
from voice.vad import VAD

logger = logging.getLogger(__name__)

router = APIRouter()

_GREETINGS: dict[str, str] = {
    "en": "Hello! I'm your clinical appointment assistant. I can help you book, cancel, or reschedule appointments. How can I help you today?",
    "hi": "नमस्ते! मैं आपका क्लिनिकल अपॉइंटमेंट सहायक हूं। मैं आपकी अपॉइंटमेंट बुक करने, रद्द करने या बदलने में मदद कर सकता हूं। आज मैं आपकी कैसे मदद कर सकता हूं?",
    "ta": "வணக்கம்! நான் உங்கள் மருத்துவமனை அப்பாயிண்ட்மென்ட் உதவியாளர். இன்று நான் உங்களுக்கு எப்படி உதவலாம்?",
}


async def _send_audio(ws: WebSocket, stream_sid: str, mulaw_bytes: bytes) -> None:
    payload = base64.b64encode(mulaw_bytes).decode("utf-8")
    await ws.send_text(json.dumps({
        "event": "media",
        "streamSid": stream_sid,
        "media": {"payload": payload},
    }))


async def _clear_audio(ws: WebSocket, stream_sid: str) -> None:
    await ws.send_text(json.dumps({"event": "clear", "streamSid": stream_sid}))


async def _resolve_patient(db, caller_phone: str) -> Optional[int]:
    """Look up patient by phone; return patient_id or None if unknown."""
    if not caller_phone:
        return None
    result = await db.execute(select(Patient).where(Patient.phone == caller_phone))
    patient = result.scalar_one_or_none()
    return patient.id if patient else None


@router.websocket("/call")
async def twilio_ws(websocket: WebSocket) -> None:
    await websocket.accept()

    stream_sid: Optional[str] = None
    caller_phone: str = ""
    session_id = str(uuid.uuid4())
    lang = "en"
    patient_id: Optional[int] = None

    speech_queue: asyncio.Queue[bytes] = asyncio.Queue()
    interrupt_event = asyncio.Event()
    active_tts_task: Optional[asyncio.Task] = None

    def _on_speech_end(pcm: bytes) -> None:
        speech_queue.put_nowait(pcm)

    vad = VAD(aggressiveness=2, on_speech_end=_on_speech_end)

    # ── TTS helpers ──────────────────────────────────────────────────────────

    async def _stream_tts(text: str, sid: str) -> None:
        interrupt_event.clear()
        try:
            async for chunk in elevenlabs_tts.generate_audio_stream(text, lang):
                if interrupt_event.is_set():
                    await _clear_audio(websocket, sid)
                    return
                await _send_audio(websocket, sid, chunk)
        except Exception as exc:
            logger.error("[tts] %s", exc)

    # ── Per-turn processing via full VoicePipeline ───────────────────────────

    async def _process_speech(pcm: bytes) -> None:
        nonlocal active_tts_task, lang, patient_id

        # Barge-in: cancel active TTS
        if active_tts_task and not active_tts_task.done():
            interrupt_event.set()
            active_tts_task.cancel()
            try:
                await active_tts_task
            except asyncio.CancelledError:
                pass

        # Open a fresh DB session for this turn
        async with _SessionFactory() as db:
            lang = await session_memory.get_language(session_id) or lang

            # Lazy patient ID resolution (from phone number on first real turn)
            if patient_id is None and caller_phone:
                patient_id = await _resolve_patient(db, caller_phone)
                if patient_id:
                    await session_memory.set_patient_id(session_id, patient_id)

            audio_chunks: list[bytes] = []
            async for chunk in voice_pipeline.handle_turn(
                pcm_audio=pcm,
                session_id=session_id,
                lang=lang,
                db=db,
                patient_id=patient_id,
                stt_func=deepgram_stt.transcribe_pcm,
            ):
                audio_chunks.append(chunk)

        # Stream audio outside the DB session
        if audio_chunks and stream_sid:
            active_tts_task = asyncio.create_task(
                _play_chunks(audio_chunks, stream_sid)
            )
            await active_tts_task

    async def _play_chunks(chunks: list[bytes], sid: str) -> None:
        interrupt_event.clear()
        for chunk in chunks:
            if interrupt_event.is_set():
                await _clear_audio(websocket, sid)
                return
            await _send_audio(websocket, sid, chunk)

    async def _speech_processor() -> None:
        while True:
            pcm = await speech_queue.get()
            try:
                await _process_speech(pcm)
            except Exception as exc:
                logger.error("[speech_processor] %s", exc)

    processor = asyncio.create_task(_speech_processor())

    # ── Main Twilio Media Streams event loop ─────────────────────────────────

    try:
        async for message in websocket.iter_text():
            data = json.loads(message)
            event = data.get("event")

            if event == "start":
                start_data = data.get("start", {})
                stream_sid = start_data.get("streamSid")
                # Extract caller phone from custom parameters or Twilio start payload
                caller_phone = (
                    start_data.get("customParameters", {}).get("from", "")
                    or start_data.get("from", "")
                )
                logger.info("[WS] call started stream=%s caller=%s", stream_sid, caller_phone)

                # Determine greeting language from stored preference
                if caller_phone:
                    async with _SessionFactory() as db:
                        pid = await _resolve_patient(db, caller_phone)
                        if pid:
                            patient_id = pid
                            await session_memory.set_patient_id(session_id, pid)
                            from models import Patient as P
                            result = await db.execute(select(P).where(P.id == pid))
                            p = result.scalar_one_or_none()
                            if p and p.language_preference:
                                lang = p.language_preference.value
                                await session_memory.set_language(session_id, lang)

                greeting = _GREETINGS.get(lang, _GREETINGS["en"])
                asyncio.create_task(_stream_tts(greeting, stream_sid))

            elif event == "media":
                mulaw = base64.b64decode(data["media"]["payload"])
                vad.process_chunk(mulaw)

            elif event == "stop":
                logger.info("[WS] call ended stream=%s", stream_sid)
                break

    except WebSocketDisconnect:
        logger.info("[WS] client disconnected session=%s", session_id)
    except Exception as exc:
        logger.error("[WS] error session=%s: %s", session_id, exc)
    finally:
        processor.cancel()
        try:
            await session_memory.delete_session(session_id)
        except Exception:
            pass
