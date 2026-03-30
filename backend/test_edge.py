import asyncio
import edge_tts
import audioread
import audioop
import tempfile
import os

async def test():
    print("Testing edge_tts with audioread...")
    c = edge_tts.Communicate("Hello there, how can I help you?", "en-US-AriaNeural")
    mp3_data = bytearray()
    async for chunk in c.stream():
        if chunk["type"] == "audio":
            mp3_data.extend(chunk["data"])
            
    print(f"Got {len(mp3_data)} bytes of mp3")
    
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        f.write(mp3_data)
        temp_name = f.name
        
    try:
        pcm_data = bytearray()
        with audioread.audio_open(temp_name) as f:
            sample_rate = f.samplerate
            channels = f.channels
            for buf in f:
                pcm_data.extend(buf)
                
        print(f"Decoded {len(pcm_data)} bytes of PCM at {sample_rate} Hz with {channels} channels")
        
        if channels == 2:
            pcm_data = audioop.tomono(bytes(pcm_data), 2, 1, 1)
            
        pcm_8k, _ = audioop.ratecv(bytes(pcm_data), 2, 1, sample_rate, 8000, None)
        ulaw_bytes = audioop.lin2ulaw(pcm_8k, 2)
        print(f"Encoded {len(ulaw_bytes)} bytes of ulaw at 8000 Hz")
    finally:
        os.unlink(temp_name)

if __name__ == "__main__":
    asyncio.run(test())
