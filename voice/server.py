import os

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import Response

from voice.twilio_handler import handle_twilio_stream

app = FastAPI(title="Clinic Voice Agent")


def _public_host(request: Request) -> str:
    explicit = os.environ.get("PUBLIC_HOST", "").strip()
    if explicit:
        return explicit.split(":")[0]
    return (request.headers.get("host") or "").split(":")[0]


@app.post("/incoming-call")
async def incoming_call(request: Request):
    host = _public_host(request)
    if not host:
        return Response(
            content='<?xml version="1.0" encoding="UTF-8"?>'
            "<Response><Say>Server misconfiguration — missing host.</Say></Response>",
            media_type="application/xml",
            status_code=500,
        )
    stream_url = f"wss://{host}/voice-stream"
    twiml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<Response>\n"
        "    <Say>Welcome to Sunrise Health Clinic. How can I help you today?</Say>\n"
        "    <Connect>\n"
        f'        <Stream url="{stream_url}" />\n'
        "    </Connect>\n"
        "</Response>"
    )
    return Response(content=twiml, media_type="application/xml")


@app.websocket("/voice-stream")
async def voice_stream(websocket: WebSocket):
    await handle_twilio_stream(websocket)
