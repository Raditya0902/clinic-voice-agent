# full_pipeline.py — Twilio ↔ Deepgram STT ↔ stub agent ↔ ElevenLabs TTS → Twilio
#
#   cd day4 && pip install -r requirements.txt
#   Set day4/.env: DEEPGRAM_API_KEY, ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID (often required on free tier).
#   Do NOT set BARGE_IN=1 unless you know why — inbound audio is continuous and would cancel all TTS.
#   Twilio Voice webhook POST → https://<ngrok>/incoming-call  (same as Day 3 path)
#
#   python full_pipeline.py
#
import asyncio
import base64
import contextlib
import json
import os

import uvicorn
from elevenlabs.core.api_error import ApiError
from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import Response

from deepgram_feed import run_deepgram_finals
from elevenlabs_stream import text_to_speech_mulaw_frames

app = FastAPI()


def _barge_in_on_media_enabled() -> bool:
    return os.environ.get("BARGE_IN", "").strip().lower() in ("1", "true", "yes")


def _stream_host(request: Request) -> str:
    explicit = os.environ.get("PUBLIC_HOST", "").strip()
    if explicit:
        return explicit.split(":")[0]
    host = request.headers.get("host") or ""
    return host.split(":")[0]


async def agent_reply(user_text: str) -> str:
    """Minimal demo brain — swap for LangGraph / OpenAI later."""
    t = user_text.lower()
    if "your name" in t or ("what" in t and "name" in t):
        return "I'm your demo voice assistant. You can call me Rachel."
    if "hello" in t or "hi" in t:
        return "Hello! Ask me anything, or ask what my name is."
    return "Thanks — I heard you. Try asking what my name is."


def _twilio_media_json(stream_sid: str, payload_b64: str) -> str:
    return json.dumps(
        {
            "event": "media",
            "streamSid": stream_sid,
            "media": {"payload": payload_b64},
        }
    )


async def send_mulaw_to_caller(websocket: WebSocket, stream_sid: str, mulaw: bytes) -> None:
    """Send one base64 μ-law frame (or chunk) to Twilio."""
    payload = base64.b64encode(mulaw).decode("utf-8")
    await websocket.send_text(_twilio_media_json(stream_sid, payload))


@app.post("/incoming-call")
async def incoming_call(request: Request):
    host = _stream_host(request)
    if not host:
        return Response(
            content='<?xml version="1.0" encoding="UTF-8"?>'
            "<Response><Say>Server misconfiguration.</Say></Response>",
            media_type="application/xml",
            status_code=500,
        )
    stream_url = f"wss://{host}/twilio-stream"
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say>Connecting you to the demo agent.</Say>
    <Connect>
        <Stream url="{stream_url}" />
    </Connect>
</Response>"""
    return Response(content=twiml, media_type="application/xml")


@app.websocket("/twilio-stream")
async def twilio_stream(websocket: WebSocket):
    await websocket.accept()
    print("Twilio connected")

    stream_sid: str | None = None
    audio_queue: asyncio.Queue = asyncio.Queue()
    finals_queue: asyncio.Queue = asyncio.Queue()
    deepgram_task = asyncio.create_task(run_deepgram_finals(audio_queue, finals_queue))

    speaking = False
    speak_task: asyncio.Task | None = None

    async def speak_text(reply: str) -> None:
        nonlocal speaking
        if not stream_sid:
            return
        speaking = True
        try:
            try:
                async for frame in text_to_speech_mulaw_frames(reply):
                    await send_mulaw_to_caller(websocket, stream_sid, frame)
            except ApiError as exc:
                if exc.status_code == 402:
                    print(
                        "ElevenLabs 402: free tier cannot use that voice over the API. "
                        "In day4/.env set ELEVENLABS_VOICE_ID to a voice from your account "
                        "(elevenlabs.io → Voices → copy voice id)."
                    )
                else:
                    print(f"ElevenLabs error ({exc.status_code}): {exc.body}")
        except asyncio.CancelledError:
            print("TTS cancelled (barge-in)")
            raise
        finally:
            speaking = False

    async def handle_finals() -> None:
        nonlocal speak_task
        while True:
            phrase = await finals_queue.get()
            if phrase is None:
                break
            if not phrase.strip():
                continue
            print(f"User (final): {phrase}")
            if speak_task and not speak_task.done():
                speak_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await speak_task
            reply = await agent_reply(phrase)
            print(f"Agent: {reply}")
            speak_task = asyncio.create_task(speak_text(reply))
            try:
                await speak_task
            except asyncio.CancelledError:
                pass

    responder = asyncio.create_task(handle_finals())

    try:
        async for message in websocket.iter_text():
            data = json.loads(message)
            event_type = data.get("event")

            if event_type == "start":
                stream_sid = data.get("start", {}).get("streamSid")
                print(f"Call started streamSid={stream_sid}")

            elif event_type == "media":
                payload = data["media"]["payload"]
                audio_bytes = base64.b64decode(payload)
                await audio_queue.put(audio_bytes)
                # Twilio sends ~20ms audio forever; canceling TTS on every packet mutes the agent.
                if _barge_in_on_media_enabled() and speaking and speak_task and not speak_task.done():
                    speak_task.cancel()

            elif event_type == "stop":
                print("Call ended (stop event)")
                break
    except Exception as exc:
        print(f"Stream error: {exc}")
    finally:
        await audio_queue.put(None)
        try:
            await deepgram_task
        except Exception as exc:
            print(f"Deepgram: {exc}")
        await finals_queue.put(None)
        responder.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await responder
        if speak_task and not speak_task.done():
            speak_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await speak_task

    print("Session closed")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
