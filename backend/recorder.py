"""Two-track call recorder: caller on the left channel, persona on the right, rendered as a 24 kHz stereo WAV."""

import io
import time
import wave

import numpy as np

OUT_RATE = 24000


def _resample(samples: np.ndarray, src: int, dst: int) -> np.ndarray:
    if src == dst or len(samples) == 0:
        return samples
    n_out = int(len(samples) * dst / src)
    x_new = np.linspace(0, len(samples) - 1, n_out)
    return np.interp(x_new, np.arange(len(samples)), samples.astype(np.float32)).astype(np.int16)


class CallRecorder:
    def __init__(self) -> None:
        self._t0 = time.monotonic()
        self._caller: list[tuple[int, np.ndarray]] = []
        self._persona: list[tuple[int, np.ndarray]] = []
        self._caller_cursor = 0
        self._persona_cursor = 0

    def _now(self) -> int:
        return int((time.monotonic() - self._t0) * OUT_RATE)

    def add_caller(self, pcm16: bytes, rate: int = 16000) -> None:
        samples = _resample(np.frombuffer(pcm16, dtype="<i2"), rate, OUT_RATE)
        start = max(self._caller_cursor, self._now() - len(samples))
        self._caller.append((start, samples))
        self._caller_cursor = start + len(samples)

    def add_persona(self, pcm16: bytes) -> None:
        samples = np.frombuffer(pcm16, dtype="<i2")
        start = max(self._persona_cursor, self._now())
        self._persona.append((start, samples))
        self._persona_cursor = start + len(samples)

    def interrupted(self) -> None:
        """The player drops queued speech on barge-in, so later speech starts from 'now'."""
        self._persona_cursor = min(self._persona_cursor, self._now())

    def has_audio(self) -> bool:
        return bool(self._persona or self._caller)

    def duration_sec(self) -> float:
        return max(self._caller_cursor, self._persona_cursor) / OUT_RATE

    @staticmethod
    def _render(chunks: list[tuple[int, np.ndarray]], total: int) -> np.ndarray:
        track = np.zeros(total, dtype=np.int16)
        for start, samples in chunks:
            track[start : start + len(samples)] = samples[: max(0, total - start)]
        return track

    def to_wav(self) -> bytes:
        total = max(self._caller_cursor, self._persona_cursor, 1)
        stereo = np.stack([self._render(self._caller, total), self._render(self._persona, total)], axis=1)
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav:
            wav.setnchannels(2)
            wav.setsampwidth(2)
            wav.setframerate(OUT_RATE)
            wav.writeframes(stereo.astype("<i2").tobytes())
        return buffer.getvalue()
