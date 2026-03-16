from __future__ import annotations
import audioop
from typing import Callable, Optional
import webrtcvad

SAMPLE_RATE = 8000
FRAME_MS = 20
FRAME_SAMPLES = SAMPLE_RATE * FRAME_MS // 1000
FRAME_BYTES_PCM = FRAME_SAMPLES * 2  # 16-bit PCM
FRAME_BYTES_MULAW = FRAME_SAMPLES    # 8-bit mulaw
SILENCE_FRAMES_THRESHOLD = 25
MIN_SPEECH_FRAMES = 10


class VAD:

    def __init__(self, aggressiveness: int = 2, on_speech_end: Optional[Callable[[bytes], None]] = None) -> None:
        assert 0 <= aggressiveness <= 3, 'aggressiveness must be 0-3'
        self._vad = webrtcvad.Vad(aggressiveness)
        self._on_speech_end = on_speech_end
        self._pcm_buffer: bytes = b''
        self._speech_buffer: bytes = b''
        self._is_speaking: bool = False
        self._speech_frames: int = 0
        self._silence_frames: int = 0

    def reset(self) -> None:
        self._pcm_buffer = b''
        self._speech_buffer = b''
        self._is_speaking = False
        self._speech_frames = 0
        self._silence_frames = 0

    def process_chunk(self, mulaw_data: bytes) -> bool:
        """Convert mulaw chunk to PCM and run through VAD frame-by-frame."""
        pcm_data = audioop.ulaw2lin(mulaw_data, 2)
        self._pcm_buffer += pcm_data
        spoke = False
        while len(self._pcm_buffer) >= FRAME_BYTES_PCM:
            frame = self._pcm_buffer[:FRAME_BYTES_PCM]
            self._pcm_buffer = self._pcm_buffer[FRAME_BYTES_PCM:]
            if self._process_frame(frame):
                spoke = True
        return spoke

    def _process_frame(self, frame: bytes) -> bool:
        is_speech = self._vad.is_speech(frame, SAMPLE_RATE)
        if is_speech:
            self._speech_frames += 1
            self._silence_frames = 0
            self._is_speaking = True
            self._speech_buffer += frame
        elif self._is_speaking:
            self._silence_frames += 1
            self._speech_buffer += frame
            if self._silence_frames >= SILENCE_FRAMES_THRESHOLD and self._speech_frames >= MIN_SPEECH_FRAMES:
                speech_pcm = self._speech_buffer
                self.reset()
                if self._on_speech_end:
                    self._on_speech_end(speech_pcm)
                return True
        return False
