import asyncio
import os
from collections.abc import AsyncIterator

from elevenlabs import VoiceSettings
from elevenlabs.client import ElevenLabs

# Twilio Media Streams expect 160-byte ulaw frames (~20 ms @ 8 kHz).
TWILIO_MULAW_FRAME_BYTES = 160


def _client() -> ElevenLabs:
    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not key:
        raise RuntimeError("ELEVENLABS_API_KEY not set in .env")
    return ElevenLabs(api_key=key)


def _voice_id() -> str:
    vid = os.environ.get("ELEVENLABS_VOICE_ID", "").strip()
    # Antoni (ErXwobaYiN019PkySvjV) confirmed working on free tier.
    return vid if vid else "ErXwobaYiN019PkySvjV"


def _synthesize_ulaw(text: str) -> bytes:
    """Blocking: call ElevenLabs and collect ulaw_8000 bytes (no conversion needed)."""
    client = _client()
    chunks: list[bytes] = []
    stream = client.text_to_speech.stream(
        voice_id=_voice_id(),
        text=text,
        model_id="eleven_flash_v2_5",
        output_format="ulaw_8000",
        voice_settings=VoiceSettings(stability=0.6, similarity_boost=0.75),
    )
    for chunk in stream:
        if chunk:
            chunks.append(chunk)
    return b"".join(chunks)


async def text_to_speech_mulaw_frames(text: str) -> AsyncIterator[bytes]:
    """Yield ulaw_8000 bytes in 160-byte Twilio frames. Synthesis runs in a thread."""
    raw = await asyncio.to_thread(_synthesize_ulaw, text)
    for i in range(0, len(raw), TWILIO_MULAW_FRAME_BYTES):
        yield raw[i : i + TWILIO_MULAW_FRAME_BYTES]
