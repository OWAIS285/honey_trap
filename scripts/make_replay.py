"""Record the replay demo: a synthetic scammer (Gemini TTS) phones the real decoy pipeline.

The scammer's lines are spoken with Gemini TTS and streamed to /ws/call as microphone audio, exactly like a browser
would. Everything the backend emits (transcripts, details, classification, latency) is saved with timestamps next to
the stereo recording the backend made, so the website can replay the call with no microphone and no live backend.

    python scripts/make_replay.py --url ws://localhost:8080 --lang hinglish

Needs Application Default Credentials (the same ones the backend uses). All names, numbers and IDs are fictional.
"""

import argparse
import asyncio
import json
import pathlib
import sys
import time
import urllib.request
import uuid

import numpy as np
import websockets

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "backend"))

from google.genai import types  # noqa: E402

from clients import _client  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
TTS_MODEL = "gemini-2.5-flash-tts"
TTS_VOICE = "Charon"
STYLE = (
    "Speak like a stern, fast-talking Indian man in his thirties who is pretending to be a police officer on a phone "
    "call. Pressuring, impatient, slightly raised voice. Read the text exactly as written:"
)

LINES = {
    "hinglish": [
        "हेलो अंकल, मैं सीबीआई साइबर क्राइम डिपार्टमेंट से इंस्पेक्टर राहुल शर्मा बोल रहा हूँ। आपके आधार कार्ड से एक पार्सल पकड़ा गया है, जिसमें गैरकानूनी सामान है।",
        "आपके नाम पर अरेस्ट वारंट निकल चुका है। यह बात किसी को मत बताइएगा, नहीं तो आपको अभी गिरफ्तार कर लिया जाएगा। केस से बचने के लिए आपको अभी पचास हज़ार रुपये सिक्योरिटी डिपॉज़िट जमा करना होगा।",
        "यूपीआई आईडी लिख लीजिए। राहुल डॉट शर्मा एट ओके एक्सिस। मैं दोबारा बोलता हूँ, राहुल डॉट शर्मा एट ओके एक्सिस।",
        "हाँ, बिल्कुल सही। अगर यूपीआई नहीं चलता, तो खाता नंबर लिखिए। एक, दो, तीन, चार, पाँच, छह, सात, आठ, नौ, शून्य, एक, दो। आईएफएससी कोड, एस बी आई एन, शून्य शून्य शून्य, एक दो तीन चार।",
    ],
    "english": [
        "Hello sir, this is Inspector Rahul Sharma from the CBI cyber crime department. A parcel in your Aadhaar name has been caught with illegal items.",
        "There is an arrest warrant in your name. Do not tell anyone, or you will be arrested immediately. To clear your name you must deposit fifty thousand rupees as a security deposit right now.",
        "Write down the UPI ID. rahul dot sharma at okaxis. I repeat, rahul dot sharma at okaxis.",
        "Yes, that is correct. If UPI does not work, write the account number: one two three four five six seven eight nine zero one two. IFSC code S B I N zero zero zero one two three four.",
    ],
}


async def synthesize(text: str, cache: pathlib.Path) -> bytes:
    if cache.exists():
        return cache.read_bytes()
    client = _client("us-central1")
    response = await client.aio.models.generate_content(
        model=TTS_MODEL,
        contents=f"{STYLE}\n\n{text}",
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=TTS_VOICE))
            ),
        ),
    )
    pcm = response.candidates[0].content.parts[0].inline_data.data
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(pcm)
    return pcm


def to_mic_chunks(pcm24k: bytes) -> list[bytes]:
    """24 kHz PCM16 -> 16 kHz PCM16 in 40 ms chunks, the format the browser sends."""
    samples = np.frombuffer(pcm24k, dtype="<i2").astype(np.float32)
    out_len = int(len(samples) * 16000 / 24000)
    resampled = np.interp(np.linspace(0, len(samples) - 1, out_len), np.arange(len(samples)), samples).astype("<i2")
    data = resampled.tobytes()
    return [data[i : i + 1280] for i in range(0, len(data), 1280)]


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="ws://localhost:8080")
    parser.add_argument("--lang", choices=list(LINES), default="hinglish")
    parser.add_argument("--origin", default="http://localhost:5000")
    parser.add_argument("--out", default=str(ROOT / "frontend" / "public" / "replay"))
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    lines = LINES[args.lang]
    cache_dir = ROOT / "out" / "replay_tts" / args.lang
    clips = []
    for i, line in enumerate(lines):
        pcm = await synthesize(line, cache_dir / f"line{i}.pcm")
        clips.append(to_mic_chunks(pcm))
        print(f"line {i + 1}: {len(pcm) / 48000:.1f}s of scammer audio")

    events: list[dict] = []
    ready: dict = {}
    mic: asyncio.Queue[bytes] = asyncio.Queue()
    silence = b"\x00" * 1280
    persona_finals = 0
    awaiting_latency_since = None
    persona_audio_bytes = 0
    done = asyncio.Event()
    start = time.monotonic()

    async with websockets.connect(
        f"{args.url}/ws/call", additional_headers={"Origin": args.origin}, max_size=None
    ) as ws:
        await ws.send(json.dumps({"type": "start", "clientId": uuid.uuid4().hex}))

        async def mic_loop() -> None:
            while True:
                try:
                    chunk = mic.get_nowait()
                except asyncio.QueueEmpty:
                    chunk = silence
                await ws.send(chunk)
                await asyncio.sleep(0.04)

        async def reader() -> None:
            nonlocal persona_finals, awaiting_latency_since, persona_audio_bytes
            async for message in ws:
                if isinstance(message, bytes):
                    persona_audio_bytes += len(message)
                    if awaiting_latency_since is not None:
                        ms = round((time.monotonic() - awaiting_latency_since) * 1000)
                        awaiting_latency_since = None
                        await ws.send(json.dumps({"type": "latency", "ms": ms}))
                        print(f"  voice-to-voice latency {ms} ms")
                    continue
                event = json.loads(message)
                event = {"t": round(time.monotonic() - start, 2), **event}
                if event["type"] == "ready":
                    ready.update(event)
                events.append(event)
                kind = event["type"]
                if kind == "transcript" and event.get("final"):
                    print(f"[{event['t']:6.1f}s {event['speaker']:7}] {event['text'][:110]}")
                    if event["speaker"] == "persona":
                        persona_finals += 1
                elif kind == "detail":
                    d = event["detail"]
                    print(f"  DETAIL {d['type']:20} {d['normalizedValue']:30} confirmed={d['confirmed']}")
                elif kind == "classification":
                    print(f"  CLASS  {event['scamType']} {event['confidence']}")
                elif kind in ("error", "ended"):
                    print(f"  {kind.upper()} {json.dumps({k: v for k, v in event.items() if k != 'strain'}, ensure_ascii=False)[:300]}")
                    done.set()
                    return

        async def wait_for_persona(count: int, timeout: float) -> None:
            deadline = time.monotonic() + timeout
            while persona_finals < count and time.monotonic() < deadline and not done.is_set():
                await asyncio.sleep(0.2)

        mic_task = asyncio.create_task(mic_loop())
        reader_task = asyncio.create_task(reader())
        try:
            await wait_for_persona(1, 40)  # the decoy's greeting
            for index, chunks in enumerate(clips):
                await asyncio.sleep(1.0)
                for chunk in chunks:
                    await mic.put(chunk)
                await asyncio.sleep(len(chunks) * 0.04 + 0.3)
                awaiting_latency_since = time.monotonic() - 0.3
                await wait_for_persona(index + 2, 60)
                if done.is_set():
                    break
            await asyncio.sleep(4)
            await ws.send(json.dumps({"type": "end"}))
            await asyncio.wait_for(done.wait(), 120)
        finally:
            mic_task.cancel()
            reader_task.cancel()

    if not ready:
        raise SystemExit("no ready event; nothing recorded")
    http_base = args.url.replace("ws://", "http://").replace("wss://", "https://")
    url = f"{http_base}/api/calls/{ready['callId']}/recording?t={ready['playToken']}"
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=60) as response:
        (out / "replay.wav").write_bytes(response.read())

    for event in events:
        event.pop("playToken", None)
    ended = next((e for e in events if e["type"] == "ended"), {})
    payload = {
        "version": 1,
        "title": "Digital-arrest call, recorded" if args.lang == "hinglish" else "Digital-arrest call (English), recorded",
        "description": (
            "A synthetic scammer (Gemini text-to-speech reading a fictional script) phones the live decoy. "
            "Everything on the right, from the transcript to the confirmed UPI ID and bank account, was produced "
            "by the real pipeline while this call happened."
        ),
        "language": args.lang,
        "durationSec": ended.get("durationSec"),
        "audio": "replay/replay.wav",
        "events": events,
    }
    (out / "replay.json").write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"saved {out / 'replay.json'} ({len(events)} events) and replay.wav; persona audio {persona_audio_bytes} bytes")
    try:
        import compress_replay  # sits next to this script

        compress_replay.main()
    except ImportError:
        print("lameenc is not installed, leaving the large replay.wav in place (pip install lameenc to shrink it)")


if __name__ == "__main__":
    asyncio.run(main())
