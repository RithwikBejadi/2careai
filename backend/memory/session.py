from __future__ import annotations

import json
from typing import Optional

import redis.asyncio as aioredis

from config import settings

_SESSION_TTL = 60 * 30   # 30 minutes
_MAX_TURNS = 10


def _key(session_id: str, field: str) -> str:
    return f"session:{session_id}:{field}"


class SessionMemory:

    def __init__(self) -> None:
        self._client: Optional[aioredis.Redis] = None

    def _get_client(self) -> aioredis.Redis:
        if self._client is None:
            self._client = aioredis.from_url(
                settings.REDIS_URL, decode_responses=True, ssl_cert_reqs=None
            )
        return self._client

    # ── Conversation turns ─────────────────────────────────────────────────

    async def add_turn(self, session_id: str, role: str, content: str) -> None:
        """Append a conversation turn; keep only the last _MAX_TURNS entries."""
        client = self._get_client()
        k = _key(session_id, "turns")
        turn = json.dumps({"role": role, "content": content})
        pipe = client.pipeline()
        pipe.rpush(k, turn)
        pipe.ltrim(k, -_MAX_TURNS, -1)
        pipe.expire(k, _SESSION_TTL)
        await pipe.execute()

    async def get_turns(self, session_id: str) -> list[dict]:
        """Return all stored turns for this session."""
        client = self._get_client()
        raw_turns = await client.lrange(_key(session_id, "turns"), 0, -1)
        result = []
        for t in raw_turns:
            try:
                result.append(json.loads(t))
            except json.JSONDecodeError:
                pass
        return result

    # ── Pending confirmation ────────────────────────────────────────────────

    async def set_pending(self, session_id: str, data: dict) -> None:
        """Store a pending confirmation (e.g. awaiting patient yes/no)."""
        client = self._get_client()
        await client.set(_key(session_id, "pending"), json.dumps(data), ex=_SESSION_TTL)

    async def get_pending(self, session_id: str) -> Optional[dict]:
        client = self._get_client()
        raw = await client.get(_key(session_id, "pending"))
        return json.loads(raw) if raw else None

    async def clear_pending(self, session_id: str) -> None:
        client = self._get_client()
        await client.delete(_key(session_id, "pending"))

    # ── Language ────────────────────────────────────────────────────────────

    async def set_language(self, session_id: str, lang: str) -> None:
        client = self._get_client()
        await client.set(_key(session_id, "language"), lang, ex=_SESSION_TTL)

    async def get_language(self, session_id: str) -> str:
        client = self._get_client()
        val = await client.get(_key(session_id, "language"))
        return val or "en"

    # ── Patient ID ─────────────────────────────────────────────────────────

    async def set_patient_id(self, session_id: str, patient_id: int) -> None:
        client = self._get_client()
        await client.set(_key(session_id, "patient_id"), str(patient_id), ex=_SESSION_TTL)

    async def get_patient_id(self, session_id: str) -> Optional[int]:
        client = self._get_client()
        val = await client.get(_key(session_id, "patient_id"))
        return int(val) if val is not None else None

    # ── Agent state ─────────────────────────────────────────────────────────

    async def set_agent_state(self, session_id: str, state: dict) -> None:
        client = self._get_client()
        await client.set(_key(session_id, "agent_state"), json.dumps(state), ex=_SESSION_TTL)

    async def get_agent_state(self, session_id: str) -> Optional[dict]:
        client = self._get_client()
        raw = await client.get(_key(session_id, "agent_state"))
        return json.loads(raw) if raw else None

    # ── Session cleanup ─────────────────────────────────────────────────────

    async def delete_session(self, session_id: str) -> None:
        client = self._get_client()
        fields = ["turns", "language", "pending", "patient_id", "agent_state"]
        pipe = client.pipeline()
        for f in fields:
            pipe.delete(_key(session_id, f))
        await pipe.execute()


session_memory = SessionMemory()
