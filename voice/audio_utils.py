import base64
import json

from fastapi import WebSocket


def _twilio_media_json(stream_sid: str, payload_b64: str) -> str:
    return json.dumps(
        {
            "event": "media",
            "streamSid": stream_sid,
            "media": {"payload": payload_b64},
        }
    )


async def send_mulaw_to_caller(websocket: WebSocket, stream_sid: str, mulaw: bytes) -> None:
    """Send one ulaw_8000 frame to Twilio via the active WebSocket."""
    payload = base64.b64encode(mulaw).decode("utf-8")
    await websocket.send_text(_twilio_media_json(stream_sid, payload))
