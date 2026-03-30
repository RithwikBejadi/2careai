from __future__ import annotations
import logging
from typing import AsyncGenerator
import edge_tts
import audioread
import audioop
import tempfile
import os
import imageio_ffmpeg

os.environ["PATH"] += os.pathsep + os.path.dirname(imageio_ffmpeg.get_ffmpeg_exe())

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

            import io
            from pydub import AudioSegment
            
            audio = AudioSegment.from_file(io.BytesIO(mp3_buffer), format="mp3")
            
            audio = audio.set_frame_rate(8000).set_channels(1)
            pcm_8k = audio.raw_data
            ulaw_bytes = audioop.lin2ulaw(pcm_8k, 2)
            
            chunk_size = 2048
            for i in range(0, len(ulaw_bytes), chunk_size):
                yield ulaw_bytes[i:i + chunk_size]
                    
        except Exception as exc:
            logger.error('[edge-tts] error generating audio for %s: %s', voice_id, str(exc))

elevenlabs_tts = EdgeTTS()