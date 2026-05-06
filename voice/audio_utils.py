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


def _twilio_mark_json(stream_sid: str, name: str) -> str:
    return json.dumps(
        {
            "event": "mark",
            "streamSid": stream_sid,
            "mark": {"name": name},
        }
    )


def _twilio_clear_json(stream_sid: str) -> str:
    return json.dumps(
        {
            "event": "clear",
            "streamSid": stream_sid,
        }
    )


async def send_mulaw_to_caller(websocket: WebSocket, stream_sid: str, mulaw: bytes) -> None:
    """Send one ulaw_8000 frame to Twilio via the active WebSocket."""
    payload = base64.b64encode(mulaw).decode("utf-8")
    await websocket.send_text(_twilio_media_json(stream_sid, payload))


async def send_mark_to_caller(websocket: WebSocket, stream_sid: str, name: str) -> None:
    """Ask Twilio to report when buffered outbound audio has finished playing."""
    await websocket.send_text(_twilio_mark_json(stream_sid, name))


async def send_clear_to_caller(websocket: WebSocket, stream_sid: str) -> None:
    """Clear Twilio's buffered outbound audio during barge-in."""
    await websocket.send_text(_twilio_clear_json(stream_sid))
