"""Shrink the recorded replay: stereo WAV -> MP3 (64 kbps), and point replay.json at the MP3.

    python scripts/compress_replay.py            # uses frontend/public/replay/replay.wav
"""

import json
import pathlib
import wave

import lameenc

REPLAY = pathlib.Path(__file__).resolve().parent.parent / "frontend" / "public" / "replay"


def wav_to_mp3(wav_path: pathlib.Path, mp3_path: pathlib.Path, kbps: int = 64) -> None:
    with wave.open(str(wav_path), "rb") as wav:
        channels, rate, frames = wav.getnchannels(), wav.getframerate(), wav.readframes(wav.getnframes())
    encoder = lameenc.Encoder()
    encoder.set_bit_rate(kbps)
    encoder.set_in_sample_rate(rate)
    encoder.set_channels(channels)
    encoder.set_quality(2)
    mp3_path.write_bytes(encoder.encode(frames) + encoder.flush())


def main() -> None:
    wav_path = REPLAY / "replay.wav"
    mp3_path = REPLAY / "replay.mp3"
    wav_to_mp3(wav_path, mp3_path)
    meta_path = REPLAY / "replay.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["audio"] = "replay/replay.mp3"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{wav_path.stat().st_size / 1e6:.1f} MB wav -> {mp3_path.stat().st_size / 1e6:.2f} MB mp3")
    wav_path.unlink()


if __name__ == "__main__":
    main()
