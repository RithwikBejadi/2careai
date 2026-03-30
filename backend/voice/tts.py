from __future__ import annotations

import logging
from typing import AsyncGenerator

import httpx

from config import settings

logger = logging.getLogger(__name__)

_VOICE_MAP = {
    "en": settings.VOICE_EN,
    "hi": settings.VOICE_HI,
    "ta": settings.VOICE_TA,
}

_ELEVENLABS_API_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream?output_format=ulaw_8000"


def _get_voice_id(language: str) -> str:
    return _VOICE_MAP.get(language, settings.VOICE_EN)


class ElevenLabsTTS:
    """
    Streams mulaw-8k audio chunks from ElevenLabs TTS.
    Requests  ulaw_8000 directly so no local audio conversion is needed.
    """

    async def generate_audio_stream(
        self, text: str, language: str = "en"
    ) -> AsyncGenerator[bytes, None]:
        voice_id = _get_voice_id(language)
        url = _ELEVENLABS_API_URL.format(voice_id=voice_id)

        headers = {
            "xi-api-key": settings.ELEVENLABS_API_KEY,
            "Content-Type": "application/json",
        }

        payload = {
            "text": text,
            "model_id": "eleven_turbo_v2",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                async with client.stream(
                    "POST",
                    url,
                    headers=headers,
                    json=payload,
                ) as response:
                    if response.status_code != 200:
                        body = await response.aread()
                        logger.error(
                            "[elevenlabs] HTTP %d: %s",
                            response.status_code,
                            body[:200],
                        )
                        return

                    chunk_size = 2048
                    async for chunk in response.aiter_bytes(chunk_size):
                        if chunk:
                            yield chunk

        except Exception as exc:
            logger.error("[elevenlabs] TTS error for voice=%s: %s", voice_id, exc)


elevenlabs_tts = ElevenLabsTTS()