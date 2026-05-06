import math
import os


def _ulaw_to_linear(sample: int) -> int:
    """Decode one G.711 mu-law byte to a signed 16-bit-ish PCM sample."""
    value = (~sample) & 0xFF
    sign = value & 0x80
    exponent = (value >> 4) & 0x07
    mantissa = value & 0x0F
    magnitude = ((mantissa << 3) + 0x84) << exponent
    magnitude -= 0x84
    return -magnitude if sign else magnitude


def mulaw_rms(frame: bytes) -> float:
    if not frame:
        return 0.0
    total = sum(_ulaw_to_linear(byte) ** 2 for byte in frame)
    return math.sqrt(total / len(frame))


class BargeInDetector:
    """Small VAD for Twilio inbound mulaw frames."""

    def __init__(
        self,
        *,
        threshold: float | None = None,
        speech_frames: int | None = None,
        silence_frames: int | None = None,
    ) -> None:
        self.threshold = threshold if threshold is not None else float(
            os.environ.get("BARGE_IN_RMS_THRESHOLD", "900")
        )
        self.speech_frames_required = speech_frames if speech_frames is not None else int(
            os.environ.get("BARGE_IN_SPEECH_FRAMES", "4")
        )
        self.silence_frames_required = silence_frames if silence_frames is not None else int(
            os.environ.get("BARGE_IN_SILENCE_FRAMES", "2")
        )
        self._speech_frames = 0
        self._silence_frames = 0

    def reset(self) -> None:
        self._speech_frames = 0
        self._silence_frames = 0

    def is_speech(self, frame: bytes) -> bool:
        if mulaw_rms(frame) >= self.threshold:
            self._speech_frames += 1
            self._silence_frames = 0
        else:
            self._silence_frames += 1
            if self._silence_frames >= self.silence_frames_required:
                self._speech_frames = 0

        return self._speech_frames >= self.speech_frames_required
