from __future__ import annotations
import logging
from typing import AsyncGenerator
import edge_tts
import audioread
import audioop
import tempfile
import os

logger = logging.getLogger(__name__)

_VOICE_MAP = {
    'en': "en-US-AriaNeural",
    'hi': "hi-IN-MadhurNeural",
    'ta': "ta-IN-PallaviNeural"
}

def _get_voice_id(language: str) -> str:
    return _VOICE_MAP.get(language, "en-US-AriaNeural")

class EdgeTTS:
    async def generate_audio_stream(self, text: str, language: str='en') -> AsyncGenerator[bytes, None]:
        voice_id = _get_voice_id(language)
        communicate = edge_tts.Communicate(text, voice_id)
        
        mp3_buffer = bytearray()
        try:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    mp3_buffer.extend(chunk["data"])
                    
            if not mp3_buffer:
                return

            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                f.write(mp3_buffer)
                temp_name = f.name
                
            try:
                pcm_data = bytearray()
                with audioread.audio_open(temp_name) as f_audio:
                    sample_rate = f_audio.samplerate
                    channels = f_audio.channels
                    for buf in f_audio:
                        pcm_data.extend(buf)
                        
                if channels == 2:
                    pcm_data = audioop.tomono(bytes(pcm_data), 2, 1, 1)

                pcm_8k, _ = audioop.ratecv(bytes(pcm_data), 2, 1, sample_rate, 8000, None)
                ulaw_bytes = audioop.lin2ulaw(pcm_8k, 2)
                
                chunk_size = 2048
                for i in range(0, len(ulaw_bytes), chunk_size):
                    yield ulaw_bytes[i:i + chunk_size]
            finally:
                if os.path.exists(temp_name):
                    os.unlink(temp_name)
                    
        except Exception as exc:
            logger.error('[edge-tts] error generating audio for %s: %s', voice_id, str(exc))

elevenlabs_tts = EdgeTTS()  # Keep variable name same so websocket.py keeps working