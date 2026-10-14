import io
import wave

import numpy as np

from limits import Limiter
from recorder import OUT_RATE, CallRecorder


def pcm(seconds: float, rate: int, value: int = 1000) -> bytes:
    return (np.ones(int(seconds * rate), dtype="<i2") * value).tobytes()


def test_wav_is_stereo_with_caller_left_and_persona_right():
    rec = CallRecorder()
    rec.add_caller(pcm(0.5, 16000, 500))
    rec.add_persona(pcm(0.5, OUT_RATE, 900))
    wav = rec.to_wav()
    with wave.open(io.BytesIO(wav)) as w:
        assert w.getnchannels() == 2 and w.getframerate() == OUT_RATE
        frames = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").reshape(-1, 2)
    assert frames[:, 0].max() == 500
    assert frames[:, 1].max() == 900
    assert rec.has_audio()


def test_persona_chunks_play_back_to_back():
    rec = CallRecorder()
    rec.add_persona(pcm(1.0, OUT_RATE))
    rec.add_persona(pcm(1.0, OUT_RATE))
    assert 1.99 < rec.duration_sec() < 2.2


def test_empty_recorder_still_renders_valid_wav():
    rec = CallRecorder()
    assert not rec.has_audio()
    with wave.open(io.BytesIO(rec.to_wav())) as w:
        assert w.getnchannels() == 2


def test_limiter_blocks_after_per_hour_limit_and_when_busy():
    limiter = Limiter(per_hour=2, max_concurrent=1)
    assert limiter.check("1.1.1.1") is None
    limiter.enter("1.1.1.1")
    assert "busy" in limiter.check("2.2.2.2")
    limiter.leave()
    limiter.enter("1.1.1.1")
    limiter.leave()
    assert "Too many" in limiter.check("1.1.1.1")
    assert limiter.check("3.3.3.3") is None
