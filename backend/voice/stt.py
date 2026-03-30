from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, Optional

from deepgram import DeepgramClient, DeepgramClientOptions, PrerecordedOptions

from config import settings

logger = logging.getLogger(__name__)


class DeepgramSTT:

    def __init__(self) -> None:
        opts = DeepgramClientOptions(
            verbose=logging.WARNING,
        )
        self._client = DeepgramClient(settings.DEEPGRAM_API_KEY, config=opts)

    async def transcribe_pcm(self, pcm_bytes: bytes) -> str:
        try:
            payload: dict = {"buffer": pcm_bytes}
            options = PrerecordedOptions(
                model="nova-2",
                language="multi",
                smart_format=True,
                encoding="linear16",
                sample_rate=8000,
                channels=1,
            )
            response = await self._client.listen.asyncprerecorded.v("1").transcribe_file(payload, options)
            
            if isinstance(response, dict):
                text = response.get("results", {}).get("channels", [{}])[0].get("alternatives", [{}])[0].get("transcript", "")
            else:
                text = response.results.channels[0].alternatives[0].transcript
                
            return text.strip()
        except Exception as e:
            logger.error("[deepgram] transcription failed: %s", e)
            return ""

    async def transcribe_mulaw(self, mulaw_bytes: bytes) -> str:
        import audioop
        pcm_bytes = audioop.ulaw2lin(mulaw_bytes, 2)
        return await self.transcribe_pcm(pcm_bytes)


deepgram_stt = DeepgramSTT()
