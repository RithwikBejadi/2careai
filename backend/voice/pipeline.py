from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from pathlib import Path
from typing import AsyncGenerator, Optional

from langchain_core.messages import HumanMessage
from sqlalchemy.ext.asyncio import AsyncSession

from agent.graph import agent
from agent.tools import set_tool_context
from memory.longterm import build_system_prompt, get_patient_context
from memory.session import session_memory
from voice.tts import elevenlabs_tts

logger = logging.getLogger(__name__)

_LATENCY_LOG_PATH = Path("/app/latency_logs.jsonl")
_SENTENCE_END_RE = re.compile(r"(?<=[.!?।])\s+")


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences on punctuation boundaries for sentence-by-sentence TTS."""
    parts = _SENTENCE_END_RE.split(text.strip())
    return [p.strip() for p in parts if p.strip()]


def _log_latency(entry: dict) -> None:
    """Append a latency entry to the JSONL log file."""
    try:
        _LATENCY_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _LATENCY_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as exc:
        logger.warning("[latency] could not write log: %s", exc)


def get_recent_latency(n: int = 10) -> list[dict]:
    """Return the last n latency log entries."""
    if not _LATENCY_LOG_PATH.exists():
        return []
    lines = _LATENCY_LOG_PATH.read_text(encoding="utf-8").splitlines()
    recent = lines[-n:] if len(lines) >= n else lines
    entries = []
    for line in recent:
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return entries


class VoicePipeline:

    async def handle_turn(
        self,
        *,
        pcm_audio: bytes,
        session_id: str,
        lang: str,
        db: AsyncSession,
        patient_id: Optional[int],
        stt_func,
    ) -> AsyncGenerator[bytes, None]:
        """
        Full pipeline: PCM → STT → (memory + LLM) → TTS stream → mulaw audio chunks.
        Yields mulaw bytes as they stream from ElevenLabs.
        Logs per-turn latency to /app/latency_logs.jsonl.
        """
        t_vad_end = time.monotonic()

        # ── STT ──────────────────────────────────────────────────────────────
        transcript = await stt_func(pcm_audio)
        t_stt_done = time.monotonic()

        if not transcript.strip():
            return

        logger.info("[pipeline] STT=%r", transcript)

        # ── Session memory: log patient turn ─────────────────────────────────
        await session_memory.add_turn(session_id, "patient", transcript)

        # ── Build context-aware system prompt ────────────────────────────────
        patient_ctx: dict = {}
        if patient_id:
            try:
                patient_ctx = await get_patient_context(db, patient_id)
            except Exception as exc:
                logger.warning("[pipeline] could not fetch patient context: %s", exc)

        recent_turns = await session_memory.get_turns(session_id)
        system_prompt = build_system_prompt(patient_ctx, recent_turns, lang=lang)

        # ── Wire tool context & run agent ────────────────────────────────────
        set_tool_context(db, session_id, patient_id)

        try:
            result = await agent.ainvoke({
                "messages": [HumanMessage(content=transcript)],
                "system_prompt": system_prompt,
            })
            response_text: str = result["messages"][-1].content
        except Exception as exc:
            logger.error("[pipeline] agent error: %s", exc)
            response_text = "I'm sorry, I had trouble with that. Could you repeat?"

        t_llm_done = time.monotonic()
        logger.info("[pipeline] LLM=%r", response_text)

        # ── Session memory: log agent turn ────────────────────────────────────
        await session_memory.add_turn(session_id, "agent", response_text)

        # ── TTS: sentence-by-sentence streaming ──────────────────────────────
        sentences = _split_sentences(response_text)
        if not sentences:
            sentences = [response_text]

        t_tts_first: Optional[float] = None
        for i, sentence in enumerate(sentences):
            async for chunk in elevenlabs_tts.generate_audio_stream(sentence, lang):
                if t_tts_first is None:
                    t_tts_first = time.monotonic()
                yield chunk

        t_done = time.monotonic()

        # ── Latency logging ───────────────────────────────────────────────────
        entry = {
            "session_id": session_id,
            "transcript": transcript[:80],
            "stt_ms": round((t_stt_done - t_vad_end) * 1000),
            "llm_ms": round((t_llm_done - t_stt_done) * 1000),
            "tts_first_chunk_ms": round(((t_tts_first or t_done) - t_llm_done) * 1000),
            "total_ms": round((t_done - t_vad_end) * 1000),
        }
        _log_latency(entry)
        logger.info("[latency] %s", json.dumps(entry))


voice_pipeline = VoicePipeline()
