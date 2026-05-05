# elevenlabs_stream.py — ElevenLabs TTS as μ-law 8 kHz chunks for Twilio Media Streams.
import asyncio
import os
from collections.abc import AsyncIterator
from pathlib import Path

from elevenlabs import VoiceSettings
from elevenlabs.client import ElevenLabs

TWILIO_MULAW_FRAME_BYTES = 160  # ~20 ms @ 8 kHz μ-law

_env_path = Path(__file__).resolve().parent / ".env"
if _env_path.is_file():
    for raw in _env_path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip().strip('"\''))
        else:
            os.environ.setdefault("ELEVENLABS_API_KEY", line)


def _client() -> ElevenLabs:
    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not key:
        raise RuntimeError("Set ELEVENLABS_API_KEY in day4/.env")
    return ElevenLabs(api_key=key)


def _voice_id() -> str:
    """
    Free-tier API keys often cannot use built-in "library" voices; set
    ELEVENLABS_VOICE_ID in day4/.env to a voice_id from your ElevenLabs
    account (Voices page or /v1/voices).
    """
    vid = os.environ.get("ELEVENLABS_VOICE_ID", "").strip()
    if vid:
        return vid
    return "21m00Tcm4TlvDq8ikWAM"  # Rachel — may 402 on free API; set ELEVENLABS_VOICE_ID


def _synthesize_ulaw(text: str) -> bytes:
    """Blocking: stream TTS from ElevenLabs in μ-law 8 kHz (Twilio-compatible)."""
    client = _client()
    chunks: list[bytes] = []
    stream = client.text_to_speech.stream(
        voice_id=_voice_id(),
        text=text,
        model_id="eleven_flash_v2_5",
        output_format="ulaw_8000",
        voice_settings=VoiceSettings(
            stability=0.5,
            similarity_boost=0.75,
        ),
    )
    for chunk in stream:
        if chunk:
            chunks.append(chunk)
    return b"".join(chunks)


async def text_to_speech_mulaw_frames(text: str) -> AsyncIterator[bytes]:
    """
    Yield μ-law octets in Twilio-sized frames (~160 bytes).
    Full synthesis runs in a worker thread so the event loop stays responsive.
    """
    raw = await asyncio.to_thread(_synthesize_ulaw, text)
    for i in range(0, len(raw), TWILIO_MULAW_FRAME_BYTES):
        yield raw[i : i + TWILIO_MULAW_FRAME_BYTES]
