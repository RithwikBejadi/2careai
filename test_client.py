import asyncio
import base64
import json
import websockets
import sys

async def main():
    uri = "ws://127.0.0.1:8001/ws/call"
    async with websockets.connect(uri) as websocket:
        print("Connected!")
        # Send start
        await websocket.send(json.dumps({
            "event": "start",
            "start": {
                "streamSid": "test-stream-123",
                "customParameters": {"from": "+1234567890"}
            }
        }))
        print("Sent start")
        
        # Wait a bit
        await asyncio.sleep(2)
        
        # Send media (say 2s of silence in mulaw 8000hz)
        # mulaw silence is usually 0xFF. 8000 bytes per second
        mulaw_bytes = b'\xff' * 16000
        await websocket.send(json.dumps({
            "event": "media",
            "media": {
                "payload": base64.b64encode(mulaw_bytes).decode('ascii')
            }
        }))
        print("Sent media")
        
        # Keep listening for TTS response
        for _ in range(5):
            try:
                resp = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                resp_data = json.loads(resp)
                print("Received event:", resp_data.get("event"))
            except asyncio.TimeoutError:
                print("No more response")
                break
        
        # Stop
        await websocket.send(json.dumps({"event": "stop"}))
        print("Done")

asyncio.run(main())