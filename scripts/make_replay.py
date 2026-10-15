"""Record a replay demo: an AI scammer phones the real decoy pipeline and the two actually talk to each other.

The scammer is a Gemini Flash script-writer that reads what the decoy just said and answers it, following the usual
digital-arrest playbook (hook, fear, isolation, payment demand, deadline). Its lines are spoken with Gemini TTS and
streamed to /ws/call as microphone audio, exactly like a browser would. Everything the backend emits (transcripts,
details, classification, latency) is saved next to the audio. English calls are English on both sides and Hindi calls
are Hindi on both sides.

The replay audio is then assembled turn by turn from the two real streams: each side is played in full, one after the
other, with short fixed pauses, so voices never overlap and there is no dead air while the live model connects. Event
times are remapped onto that timeline so the transcript and dashboard stay in step with the sound. The assembled
replay must land between --min-sec and --max-sec; otherwise the last exchanges are dropped or the call is re-recorded.

    python scripts/make_replay.py --lang english     # replay-en  (local backend on :8080)
    python scripts/make_replay.py --lang hindi       # replay-hi  (start the backend with LANGUAGE_CODE=hi-IN)

Needs Application Default Credentials (the same ones the backend uses). All names, numbers and IDs are fictional.
"""

import argparse
import asyncio
import hashlib
import json
import pathlib
import re
import sys
import time
import uuid
import wave

import numpy as np
import websockets

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "backend"))

from google.genai import types  # noqa: E402

import analysis  # noqa: E402
from clients import _client, flash, text_client  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
TTS_MODEL = "gemini-2.5-flash-tts"
TTS_VOICE = "Charon"
RATE = 24000
LEAD = 0.6  # silence before the first voice
GAP_AFTER_DECOY = 0.9  # pause after the decoy finishes, before the scammer speaks
GAP_AFTER_SCAMMER = 0.8  # the decoy's "thinking" pause (the real measured delay is in the latency card)
TAIL = 2.5  # room at the end for the evidence summary events
QUIET = 3.5  # seconds without decoy audio that count as "the decoy has finished speaking"
MIN_EXCHANGES = 4  # the payment details are all given by the fourth scammer turn
ENGLISH_NOTE = " The spoken Hindi is shown as an English transcript."

# The facts the scammer uses, in the form a person would say them aloud. The model only ever sees the {TOKENS}.
LANGS = {
    "english": {
        "name": "en",
        "title": "Digital-arrest call (English), recorded",
        "tts_hint": "in clear Indian English",
        "script_rule": "ENGLISH only, plain Indian English, no Hindi words at all (no 'beta', 'ji', 'arre', 'sahab').",
        "spoken": {
            "{NAME}": "Rahul Sharma",
            "{AGENCY}": "the CBI cyber crime branch",
            "{BADGE}": "four seven two one",
            "{CASE}": "two zero two five, slash, four four seven one",
            "{AMOUNT}": "fifty thousand rupees",
            "{UPI}": "rahul dot sharma at okaxis",
            "{ACCOUNT_NAME}": "R K Trading Company",
            "{ACCOUNT}": "three four seven six, two zero one five, eight nine three four",
            "{IFSC}": "S B I N, zero zero zero, four two one five",
        },
    },
    "hindi": {
        "name": "hi",
        "title": "Digital-arrest call (Hindi), recorded",
        "tts_hint": "in natural, clear Hindi",
        "script_rule": (
            "HINDI only, written in Devanagari, in everyday spoken Hindi. No English sentences and no Hinglish: keep English "
            "only for the acronyms CBI, UPI and IFSC."
        ),
        "spoken": {
            "{NAME}": "राहुल शर्मा",
            "{AGENCY}": "सीबीआई साइबर क्राइम ब्रांच",
            "{BADGE}": "चार सात दो एक",
            "{CASE}": "दो शून्य दो पाँच, चार चार सात एक",
            "{AMOUNT}": "पचास हज़ार रुपये",
            "{UPI}": "राहुल डॉट शर्मा एट ओके एक्सिस",
            "{ACCOUNT_NAME}": "आर के ट्रेडिंग कंपनी",
            "{ACCOUNT}": "तीन चार सात छह, दो शून्य एक पाँच, आठ नौ तीन चार",
            "{IFSC}": "एस बी आई एन, शून्य शून्य शून्य, चार दो एक पाँच",
        },
    },
}

BEATS = [
    {
        "brief": (
            "Open the call. Confirm you are speaking to Mr Ramesh Sharma. Introduce yourself as Inspector {NAME} of "
            "{AGENCY}, badge number {BADGE}. Say a parcel booked in his Aadhaar name was seized with illegal items."
        ),
        "needs": ["{NAME}", "{BADGE}"],
        "max_words": 40,
    },
    {
        "brief": (
            "Answer what he just said or asked, directly. Make it frightening but believable: the parcel held banned "
            "drugs and fake passports, so case {CASE} is registered and an arrest warrant is ready. He must stay on the "
            "line and tell nobody, not even family, because the investigation is confidential."
        ),
        "needs": ["{CASE}"],
        "max_words": 38,
    },
    {
        "brief": (
            "Answer him directly. Offer a way out: to prove he is not involved, send a refundable security deposit of "
            "{AMOUNT} right now to the verification UPI ID {UPI}. Tell him to write the UPI ID down."
        ),
        "needs": ["{AMOUNT}", "{UPI}"],
        "max_words": 34,
    },
    {
        "brief": (
            "Deal firmly with his hesitation or questions and say the deposit is refundable within 24 hours. Give the "
            "bank transfer details too: account name {ACCOUNT_NAME}, account number {ACCOUNT}, IFSC {IFSC}. Ask him to "
            "repeat them back."
        ),
        "needs": ["{ACCOUNT}", "{IFSC}"],
        "max_words": 52,
    },
    {
        "brief": (
            "He is still hesitating. Press him calmly: the transfer must be done within thirty minutes or officers will "
            "come to his house, he must not hang up, and he must send the payment screenshot."
        ),
        "needs": [],
        "max_words": 30,
    },
]

SCAMMER_SYSTEM = """You write one side of a FICTIONAL phone call for a fraud-awareness product demo. The other side is an
AI decoy playing a frightened retired schoolteacher. You play the scammer, who poses as a police officer in the
well-known 'digital arrest' scam. Nothing here is real: every name, number and ID is invented.

Sound like a real Indian call-centre scammer: brisk, confident, intimidating but polite, using 'sir' (or the natural
Hindi equivalent), citing numbers, pressing with deadlines. React to the exact words the victim just used before moving
the script on, the way a real person on a call would. Never repeat a sentence you already said.

RULES:
- Language: @@RULE@@
- Output only the spoken words of ONE turn, SHORT: one to three brisk sentences and at most @@WORDS@@ words once every
  token is spoken aloud (a token counts as many words as listed here: @@COUNTS@@). No quotes, stage directions, labels
  or markdown.
- Whenever you need one of these facts write the token exactly as shown and nothing else for it: {NAME} {AGENCY}
  {BADGE} {CASE} {AMOUNT} {UPI} {ACCOUNT_NAME} {ACCOUNT} {IFSC}. {NAME} is only the name, so add any title yourself
  ('Inspector {NAME}'). Never write real numbers, phone numbers, links, bank names or any other identifier yourself.
"""


def build_prompt(history: list[tuple[str, str]], beat: dict, cfg: dict) -> str:
    talk = "\n".join(f"{who}: {text}" for who, text in history)
    counts = ", ".join(f"{token} {len(spoken.split())}" for token, spoken in cfg["spoken"].items())
    system = SCAMMER_SYSTEM.replace("@@RULE@@", cfg["script_rule"]).replace("@@WORDS@@", str(beat["max_words"]))
    system = system.replace("@@COUNTS@@", counts)
    return f"{system}\nCALL SO FAR:\n{talk}\n\nYOUR NEXT TURN: {beat['brief']}"


ALLOWED_LATIN = {"CBI", "UPI", "IFSC", "OTP", "SBI", "ATM", "FIR", "RBI", "SMS", "KYC", "PIN", "OK"}
HINDI_WORDS = re.compile(r"\b(beta|arre|arey|achha|accha|haan|sahab|ji|bhai|nahi|kya|hai)\b", re.IGNORECASE)


def language_problems(text: str, lang: str) -> list[str]:
    """Reasons a line is not pure English / pure Hindi (acronyms and UPI IDs are allowed in Hindi)."""
    if lang == "english":
        bad = ["Devanagari"] if re.search(r"[\u0900-\u097F]", text) else []
        return bad + [m.group(0) for m in HINDI_WORDS.finditer(text) if m.group(0).lower() not in {"hai"}]
    stripped = re.sub(r"\S*@\S*", " ", text)
    words = [w for w in re.findall(r"[A-Za-z]{2,}", stripped) if w.upper() not in ALLOWED_LATIN]
    return words


async def scammer_line(cfg: dict, lang: str, history: list[tuple[str, str]], beat: dict) -> str:
    """One scammer turn from Flash, retried until it is the right length, language and carries the needed facts."""
    last = ""
    best: tuple[int, str] | None = None  # the shortest line that is right in every way but a little too long
    for _ in range(4):
        prompt = build_prompt(history, beat, cfg)
        response = await flash(
            text_client(), contents=prompt,
            cfg=types.GenerateContentConfig(temperature=0.9, thinking_config=analysis._thinking()), attempts=4,
        )
        text = " ".join((response.text or "").replace("*", "").replace('"', "").split())
        last = text
        missing = [t for t in beat["needs"] if t not in text]
        stray = [t for t in re.findall(r"\{[A-Z_]+\}", text) if t not in cfg["spoken"]]
        filled = text
        for token, spoken in cfg["spoken"].items():
            filled = filled.replace(token, spoken)
        spoken_words = len(filled.split())
        clean = not missing and not stray and not language_problems(filled, lang)
        if clean and 10 <= spoken_words <= beat["max_words"] + 4:
            return filled
        if clean and spoken_words > beat["max_words"] + 4 and (best is None or spoken_words < best[0]):
            best = (spoken_words, filled)
        print(f"  (scammer line rejected: words={spoken_words} missing={missing} stray={stray} lang={language_problems(filled, lang)[:3]})")
    if best and best[0] <= beat["max_words"] + 18:
        return best[1]
    raise SystemExit(f"could not get a usable scammer line; last attempt: {last}")


async def synthesize(text: str, cfg: dict, cache_dir: pathlib.Path) -> bytes:
    cache = cache_dir / f"{hashlib.sha1(text.encode('utf-8')).hexdigest()[:16]}.pcm"
    if cache.exists():
        return cache.read_bytes()
    style = (
        "Speak like a brisk, fast-talking Indian man in his thirties who is a police officer on a phone call: confident, "
        f"controlled, pressuring. Speak {cfg['tts_hint']}. Read digits and IDs clearly in small groups at a steady pace, "
        "without long pauses. Read the text exactly as written:"
    )
    client = _client("us-central1")
    response = await client.aio.models.generate_content(
        model=TTS_MODEL,
        contents=f"{style}\n\n{text}",
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=TTS_VOICE))
            ),
        ),
    )
    pcm = response.candidates[0].content.parts[0].inline_data.data
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(pcm)
    return pcm


def to_mic_chunks(pcm24k: bytes) -> list[bytes]:
    """24 kHz PCM16 -> 16 kHz PCM16 in 40 ms chunks, the format the browser sends."""
    samples = np.frombuffer(pcm24k, dtype="<i2").astype(np.float32)
    out_len = int(len(samples) * 16000 / 24000)
    resampled = np.interp(np.linspace(0, len(samples) - 1, out_len), np.arange(len(samples)), samples).astype("<i2")
    data = resampled.tobytes()
    return [data[i : i + 1280] for i in range(0, len(data), 1280)]


def leveled(pcm: bytes, target_rms: float = 0.11) -> np.ndarray:
    """Even out loudness between the two voices without letting anything clip."""
    samples = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
    voiced = samples[np.abs(samples) > 0.02]
    rms = float(np.sqrt(np.mean(voiced**2))) if len(voiced) else 0.0
    gain = min(target_rms / rms, 0.95 / max(float(np.max(np.abs(samples))), 1e-6)) if rms else 1.0
    return samples * gain


def squeeze(samples: np.ndarray, longest: float = 0.7, keep: float = 0.45) -> np.ndarray:
    """Shorten pauses longer than `longest` seconds inside a voice clip to `keep` seconds (TTS and the live model both leave some)."""
    frame = int(RATE * 0.02)
    count = len(samples) // frame
    if count < 4:
        return samples
    rms = np.sqrt((samples[: count * frame].reshape(count, frame) ** 2).mean(axis=1))
    quiet = rms < 0.012
    parts: list[np.ndarray] = []
    i = 0
    while i < count:
        j = i
        while j < count and quiet[j] == quiet[i]:
            j += 1
        run = samples[i * frame : j * frame]
        if quiet[i] and (j - i) * 0.02 > longest and 0 < i and j < count:
            run = run[: int(keep * RATE)]
        parts.append(run)
        i = j
    parts.append(samples[count * frame :])
    return np.concatenate(parts)


def persona_texts(events: list[dict], lo: float, hi: float) -> list[dict]:
    return [e for e in events if e["type"] == "transcript" and e["speaker"] == "persona" and lo <= e["t"] < hi]


async def record(args, cfg: dict) -> dict:
    events: list[dict] = []
    ready: dict = {}
    mic: asyncio.Queue[bytes] = asyncio.Queue()
    silence = b"\x00" * 1280
    state = {"finals": 0, "phase": 0, "await_latency": None, "pending": False, "backup": None}
    turn_events: list[dict] = []  # decoy transcript events of the reply in progress
    last_turn: list[dict] = []  # ... and of the reply that just finished
    slots = len(BEATS) + 1
    audio: list[bytearray] = [bytearray() for _ in range(slots)]  # decoy audio per phase
    last_audio = [0.0]
    audio_first: list[float | None] = [None] * slots
    audio_last: list[float | None] = [None] * slots
    done = asyncio.Event()
    start = time.monotonic()
    history: list[tuple[str, str]] = []
    lines: list[tuple[float, float]] = []  # real start and end of each scammer line
    spoken_lines: list[str] = []
    caller_pcm: list[bytes] = []
    cache_dir = ROOT / "out" / "replay_tts" / args.lang

    async with websockets.connect(
        f"{args.url}/ws/call", additional_headers={"Origin": args.origin}, max_size=None, ping_interval=None
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
            async for message in ws:
                now = time.monotonic()
                if isinstance(message, bytes):
                    phase = state["phase"]
                    state["backup"] = None  # a new reply is coming, the cut-off one is not needed
                    audio[phase] += message
                    last_audio[0] = now
                    audio_first[phase] = audio_first[phase] or now - start
                    audio_last[phase] = now - start
                    if state["await_latency"] is not None and now > state["await_latency"]:
                        ms = round((now - state["await_latency"]) * 1000)
                        state["await_latency"] = None
                        await ws.send(json.dumps({"type": "latency", "ms": ms}))
                        print(f"  voice-to-voice latency {ms} ms")
                    continue
                event = {"t": round(now - start, 3), **json.loads(message)}
                if event["type"] == "ready":
                    ready.update(event)
                events.append(event)
                kind = event["type"]
                if kind == "transcript" and event["speaker"] == "persona":
                    turn_events.append(event)
                if kind == "transcript" and event.get("final"):
                    print(f"[{event['t']:6.1f}s {event['speaker']:7}] {event['text'][:150]}")
                    if event["speaker"] == "persona":
                        state["finals"] += 1
                        state["pending"] = False
                        last_turn[:] = turn_events
                        turn_events.clear()
                elif kind == "interrupted":
                    # The browser would flush this reply's queued audio and its words never finished: set it aside and
                    # wait for the reply the decoy gives to what it just heard (it is put back if none comes).
                    print(f"  INTERRUPTED at {event['t']:.1f}s (cut-off reply set aside)")
                    prev = events[-2] if len(events) > 1 else {}
                    flushed = prev.get("type") == "transcript" and prev.get("speaker") == "persona" and prev.get("final")
                    removed = [e for e in (last_turn if flushed else []) + turn_events if e in events]
                    state["backup"] = {
                        "events": removed, "audio": bytes(audio[state["phase"]]), "first": audio_first[state["phase"]],
                        "finals": 1 if flushed else 0, "at": now,
                    }
                    for e in removed:
                        events.remove(e)
                    if flushed:
                        state["finals"] -= 1
                    last_turn.clear()
                    turn_events.clear()
                    audio[state["phase"]].clear()
                    audio_first[state["phase"]] = None
                    state["pending"] = True
                elif kind == "detail":
                    d = event["detail"]
                    print(f"  DETAIL {d['type']:20} {d['normalizedValue']:30} confirmed={d['confirmed']}")
                elif kind == "classification":
                    print(f"  CLASS  {event['scamType']} {event['confidence']}")
                elif kind == "stage":
                    print(f"  STAGE at {event['t']:.1f}s")
                elif kind in ("error", "ended"):
                    print(f"  {kind.upper()} {json.dumps({k: v for k, v in event.items() if k != 'strain'}, ensure_ascii=False)[:300]}")
                    done.set()
                    return

        async def decoy_finished(finals_needed: int, timeout: float) -> None:
            """Wait for the decoy's turn to complete and for its audio to stop arriving."""
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline and not done.is_set():
                backup = state["backup"]
                if state["pending"] and backup and time.monotonic() - backup["at"] > 15:
                    print("  no new reply followed the interruption: the cut-off reply is the reply")
                    phase = state["phase"]
                    audio[phase] += backup["audio"]
                    audio_first[phase] = backup["first"]
                    events.extend(backup["events"])
                    events.sort(key=lambda e: e["t"])
                    state["finals"] += backup["finals"]
                    state["pending"] = False
                    state["backup"] = None
                    last_audio[0] = time.monotonic() - QUIET - 1
                if (
                    state["finals"] >= finals_needed
                    and not state["pending"]
                    and audio[state["phase"]]
                    and last_audio[0]
                    and time.monotonic() - last_audio[0] > QUIET
                ):
                    return
                await asyncio.sleep(0.2)

        mic_task = asyncio.create_task(mic_loop())
        reader_task = asyncio.create_task(reader())
        try:
            await decoy_finished(1, 60)  # the decoy's greeting
            greeting = " ".join(e["text"] for e in persona_texts(events, 0, 1e9) if e.get("final")) or "Hello?"
            history.append(("Victim", greeting))
            for index, beat in enumerate(BEATS):
                line = await scammer_line(cfg, args.lang, history, beat)
                print(f"  >> scammer: {line}")
                pcm = await synthesize(line, cfg, cache_dir)
                chunks = to_mic_chunks(pcm)
                spoken_lines.append(line)
                caller_pcm.append(pcm)
                state["phase"] = index + 1
                state["backup"] = None
                state["pending"] = False
                begin = time.monotonic()
                for chunk in chunks:
                    await mic.put(chunk)
                finish = begin + len(chunks) * 0.04
                lines.append((begin - start, finish - start))
                await asyncio.sleep(max(0.0, finish - time.monotonic()))
                state["await_latency"] = finish
                await decoy_finished(index + 2, 75)
                if done.is_set():
                    break
                reply = " ".join(e["text"] for e in persona_texts(events, begin - start, 1e9) if e.get("final"))
                history.append(("Scammer", line))
                history.append(("Victim", reply or "(says nothing)"))
            await asyncio.sleep(3)
            await ws.send(json.dumps({"type": "end"}))
            try:
                await asyncio.wait_for(done.wait(), 90)
            except asyncio.TimeoutError:
                print("  (no end-of-call summary arrived on the socket; it is rebuilt from the stored call)")
        finally:
            mic_task.cancel()
            reader_task.cancel()

    if not ready:
        raise SystemExit("no ready event; nothing recorded")
    return {
        "events": events, "audio": audio, "first": audio_first, "last": audio_last, "lines": lines,
        "scammer": spoken_lines, "caller_pcm": caller_pcm, "ready": ready,
    }


async def devanagari(texts: list[str]) -> list[str]:
    """Spoken Hindi that the speech recogniser wrote in Roman letters, rewritten in Devanagari (display only)."""
    prompt = (
        "Each line below is spoken Hindi written in Roman letters. Rewrite every line in Devanagari script, keeping the "
        "words exactly as spoken: do not translate, correct or shorten anything. Keep CBI, UPI and IFSC as they are. "
        "Return a JSON array of strings in the same order.\n" + json.dumps(texts, ensure_ascii=False)
    )
    response = await flash(
        text_client(), contents=prompt,
        cfg=types.GenerateContentConfig(response_mime_type="application/json", thinking_config=analysis._thinking()), attempts=4,
    )
    converted = json.loads(response.text)
    if not isinstance(converted, list) or len(converted) != len(texts):
        raise SystemExit("Devanagari conversion returned the wrong number of lines")
    return [" ".join(str(t).split()) for t in converted]


async def normalise_hindi(rec: dict) -> None:
    """The speech recogniser sometimes writes Hindi in Roman letters; show it in Devanagari like the audio sounds."""
    events = rec["events"]
    targets = [
        e for e in events
        if e["type"] == "transcript" and e.get("final") and e["speaker"] in ("persona", "caller")
        and language_problems(e["text"], "hindi")
    ]
    if not targets:
        return
    print(f"  converting {len(targets)} Roman-script transcripts to Devanagari")
    for event, text in zip(targets, await devanagari([e["text"] for e in targets])):
        event["text"] = text
        event["reveal"] = True
    drop: set[int] = set()
    pending: list[dict] = []
    for event in events:
        if event["type"] == "transcript" and event["speaker"] == "persona":
            if event.get("final"):
                if event.get("reveal"):
                    drop.update(id(p) for p in pending)
                pending.clear()
            else:
                pending.append(event)
    events[:] = [e for e in events if id(e) not in drop]


async def english_display(events: list[dict]) -> int:
    """Show Hindi transcript lines in English (the original stays in textOriginal); streamed partials are rebuilt from it."""
    groups: list[tuple[list[dict], dict]] = []
    open_partials: dict[str, list[dict]] = {}
    for event in sorted(events, key=lambda e: e["t"]):
        if event["type"] != "transcript":
            continue
        if event.get("final"):
            groups.append((open_partials.pop(event["speaker"], []), event))
        else:
            open_partials.setdefault(event["speaker"], []).append(event)
    changed = 0
    for partials, final in groups:
        original = final.get("textOriginal") or final["text"]
        if not analysis.needs_translation(original):
            continue
        english = await analysis.to_english(text_client(), original)
        if not english:
            raise SystemExit(f"could not translate: {original[:60]}")
        words = english.split()
        for i, partial in enumerate(partials, 1):
            partial["text"] = " ".join(words[: max(1, round(len(words) * i / len(partials)))])
        final["textOriginal"], final["text"] = original, english
        changed += 1
    return changed


async def recover_ended(rec: dict) -> None:
    """If the call's final websocket message never arrived, rebuild it from what the backend stored for the call."""
    if any(e["type"] == "ended" and e.get("strain") for e in rec["events"]):
        return
    from store import clean, store  # backend module: Firestore through the same Application Default Credentials

    call = await store.get(f"calls/{rec['ready']['callId']}")
    if not call or not call.get("strainId"):
        print("  could not recover the end-of-call summary")
        return
    strain = clean(await store.get(f"strains/{call['strainId']}"))
    rec["events"].append({
        "t": round(max(e["t"] for e in rec["events"]) + 1, 3), "type": "ended", "reason": call.get("endReason"),
        "durationSec": call.get("durationSec"), "recording": bool(call.get("recording")), "strainId": call["strainId"],
        "strain": strain, "scamType": call.get("scamType"), "counts": call.get("counts"),
        "latency": {"p50": call.get("latencyMsP50"), "p90": call.get("latencyMsP90")}, "estCostUsd": call.get("estCostUsd"),
    })
    print("  rebuilt the end-of-call summary from the stored call")


def save_raw(rec: dict, folder: pathlib.Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob("*.pcm"):
        old.unlink()
    meta = {k: v for k, v in rec.items() if k not in ("audio", "caller_pcm")}
    (folder / "rec.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    for k, pcm in enumerate(rec["audio"]):
        (folder / f"phase{k}.pcm").write_bytes(bytes(pcm))
    for k, pcm in enumerate(rec["caller_pcm"]):
        (folder / f"caller{k}.pcm").write_bytes(pcm)


def load_raw(folder: pathlib.Path) -> dict:
    rec = json.loads((folder / "rec.json").read_text(encoding="utf-8"))
    order = lambda p: int(re.sub(r"\D", "", p.stem))  # noqa: E731
    rec["audio"] = [bytearray(p.read_bytes()) for p in sorted(folder.glob("phase*.pcm"), key=order)]
    rec["caller_pcm"] = [p.read_bytes() for p in sorted(folder.glob("caller*.pcm"), key=order)]
    return rec


def layout(rec: dict, n: int, gap_decoy: float = GAP_AFTER_DECOY, gap_scammer: float = GAP_AFTER_SCAMMER) -> dict | None:
    """Place the first n exchanges one after another; None if a turn has no audio."""
    lines, events = rec["lines"][: n], rec["events"]
    if n < 1 or len(rec["audio"]) < n + 1 or len(rec["caller_pcm"]) < n:
        return None
    if any(len(rec["audio"][k]) < RATE for k in range(n + 1)):
        return None
    decoy = [squeeze(leveled(bytes(rec["audio"][k]))) for k in range(n + 1)]
    caller = [squeeze(leveled(rec["caller_pcm"][k])) for k in range(n)]
    segments: list[tuple[float, float, float, float]] = []
    placed_decoy: list[tuple[float, float]] = []
    placed_caller: list[tuple[float, float]] = []
    cursor = LEAD
    for k in range(n + 1):
        if k:
            begin, end = cursor, cursor + len(caller[k - 1]) / RATE
            placed_caller.append((begin, end))
            segments.append((lines[k - 1][0], lines[k - 1][1], begin, end))
            cursor = end + gap_scammer
        begin, end = cursor, cursor + len(decoy[k]) / RATE
        placed_decoy.append((begin, end))
        phase_lo = lines[k - 1][0] if k else 0.0
        phase_hi = rec["lines"][k][0] if k < len(rec["lines"]) else float("inf")
        spoken = persona_texts(events, phase_lo, phase_hi)
        real_start = min([rec["first"][k] or 1e9] + [e["t"] for e in spoken])
        real_end = max([rec["last"][k] or 0.0] + [e["t"] for e in spoken])
        segments.append((real_start, max(real_end, real_start + 0.5), begin, end))
        cursor = end + gap_decoy
    replay_end = placed_decoy[-1][1]
    return {
        "n": n, "decoy": decoy, "caller": caller, "placed_decoy": placed_decoy, "placed_caller": placed_caller,
        "segments": segments, "replay_end": replay_end, "duration": replay_end + TAIL,
    }


def spurious(detail: dict, cfg: dict) -> bool:
    """A detail the script never contained, i.e. the speech recogniser inventing digits from audio noise."""
    if detail["type"] in ("phone_number", "url", "app_name"):
        return True
    if detail["type"] == "case_or_badge_id":
        digits = re.sub(r"\D", "", str(detail.get("normalizedValue", "")))
        known = ["4721", "20254471"]
        return len(digits) < 3 or not any(k.startswith(digits) or digits in k for k in known)
    return False


def remap_events(rec: dict, lay: dict, cfg: dict) -> list[dict]:
    """Every backend event, placed on the replay timeline; the caller's words are spread across the spoken line."""
    n, events, lines = lay["n"], rec["events"], rec["lines"]
    anchors: list[tuple[float, float]] = []
    for real_start, real_end, begin, end in sorted(lay["segments"]):
        for real, replay in ((real_start, begin), (real_end, end)):
            if anchors and real <= anchors[-1][0]:
                real = anchors[-1][0] + 1e-3
            if anchors and replay < anchors[-1][1]:
                replay = anchors[-1][1]
            anchors.append((real, replay))
    real_xs = [a[0] for a in anchors]
    replay_ys = [a[1] for a in anchors]
    last_real = real_xs[-1]
    cut = lines[n][0] if n < len(lines) else float("inf")
    duration, replay_end = lay["duration"], lay["replay_end"]

    def remap(t: float, late_rank: int) -> float:
        if t <= last_real:
            return round(float(np.interp(t, real_xs, replay_ys)), 2)
        return round(min(replay_end + 0.4 + 0.3 * late_rank, duration - 0.2), 2)

    out: list[dict] = []
    late = 0
    spread: dict[tuple[str, int], list[dict]] = {}  # lines whose words are revealed across the spoken audio
    for event in sorted(events, key=lambda e: e["t"]):
        if event["type"] == "ready":
            continue
        if event["type"] == "transcript":
            if event["t"] >= cut:
                continue
            k = sum(1 for begin, _ in lines[:n] if begin <= event["t"])
            if event["speaker"] == "caller":
                if k and event.get("final"):
                    spread.setdefault(("caller", k), []).append(event)
                continue
            if event.get("reveal"):
                spread.setdefault(("persona", k), []).append(event)
                continue
        if event["type"] == "detail" and spurious(event["detail"], cfg):
            print(f"  left out a detail the script never contained: {event['detail']['type']} {event['detail']['normalizedValue']}")
            continue
        rank = 0
        if event["t"] > last_real:
            rank, late = late, late + 1
        new = {**event, "t": remap(event["t"], rank)}
        if new["type"] == "transcript" and new.get("final"):
            new["tSec"] = new["t"]
        if new["type"] == "ended":
            new["durationSec"] = round(duration, 1)
        out.append(new)

    for (speaker, k), finals in spread.items():
        text = " ".join(" ".join(f["text"].split()) for f in finals)
        begin, end = lay["placed_caller"][k - 1] if speaker == "caller" else lay["placed_decoy"][k]
        words = text.split()
        steps = max(1, min(len(words), 16))
        for i in range(1, steps + 1):
            share = i / steps
            out.append({
                "type": "transcript", "speaker": speaker, "text": " ".join(words[: max(1, round(len(words) * share))]),
                "turn": finals[0].get("turn"), "final": False, "t": round(begin + 0.3 + (end - begin - 0.3) * share, 2),
            })
        out.append({
            "type": "transcript", "speaker": speaker, "text": text, "turn": finals[0].get("turn"), "final": True,
            "tSec": round(end, 2), "t": round(end + 0.05, 2),
        })
    out.sort(key=lambda e: e["t"])
    return out


def check_languages(rec: dict, lang: str, n: int) -> list[str]:
    problems = []
    for k, line in enumerate(rec["scammer"][:n], 1):
        problems += [f"scammer {k}: {p}" for p in language_problems(line, lang)]
    cut = rec["lines"][n][0] if n < len(rec["lines"]) else float("inf")
    for e in persona_texts(rec["events"], 0, cut):
        if e.get("final"):
            bad = language_problems(e["text"], lang)
            if lang == "hindi":
                bad = bad[2:]  # tolerate a couple of loanwords from the speech recogniser
            problems += [f"decoy: {p} in '{e['text'][:50]}'" for p in bad]
    return problems


def write_wav(path: pathlib.Path, lay: dict) -> None:
    total = int(lay["duration"] * RATE)
    stereo = np.zeros((total, 2), dtype=np.float32)
    for samples, (begin, _) in zip(lay["caller"], lay["placed_caller"]):
        stereo[int(begin * RATE) : int(begin * RATE) + len(samples), 0] = samples
    for samples, (begin, _) in zip(lay["decoy"], lay["placed_decoy"]):
        stereo[int(begin * RATE) : int(begin * RATE) + len(samples), 1] = samples
    pcm = (np.clip(stereo, -1, 1) * 32767).astype("<i2")
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(RATE)
        wav.writeframes(pcm.tobytes())


def fit(rec: dict, n: int, args) -> dict | None:
    """Lay out n exchanges, stretching or tightening the pauses between turns (within reason) to hit the time window."""
    base = layout(rec, n)
    if base is None:
        return None
    print(f"  {n} exchanges = {base['duration']:.0f}s with the default pauses")
    if args.min_sec <= base["duration"] <= args.max_sec:
        return base
    delta = ((args.min_sec + args.max_sec) / 2 - base["duration"]) / (2 * n)
    gap_decoy = min(2.0, max(0.4, GAP_AFTER_DECOY + delta))
    gap_scammer = min(2.0, max(0.4, GAP_AFTER_SCAMMER + delta))
    lay = layout(rec, n, gap_decoy, gap_scammer)
    if lay and args.min_sec <= lay["duration"] <= args.max_sec:
        print(f"  pauses set to {gap_decoy:.2f}s and {gap_scammer:.2f}s -> {lay['duration']:.0f}s")
        return lay
    return None


def choose(rec: dict, args) -> dict | None:
    """The longest prefix of the call that fits the time window, or None if this recording does not."""
    if not any(e["type"] == "ended" and e.get("strain") for e in rec["events"]):
        print("  the call has no end-of-call summary")
        return None
    for n in range(len(rec["lines"]), MIN_EXCHANGES - 1, -1):
        lay = fit(rec, n, args)
        if lay is None:
            continue
        problems = check_languages(rec, args.lang, n)
        if problems:
            print("  language problems:", problems[:6])
            return None
        return lay
    return None


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="ws://localhost:8080")
    parser.add_argument("--lang", choices=list(LANGS), default="english")
    parser.add_argument("--origin", default="http://localhost:5000")
    parser.add_argument("--out", default=str(ROOT / "frontend" / "public" / "replay"))
    parser.add_argument("--min-sec", type=float, default=105.0)
    parser.add_argument("--max-sec", type=float, default=120.0)
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--from-raw", action="store_true", help="re-assemble the last capture instead of recording again")
    parser.add_argument("--english-only", action="store_true", help="only add English transcripts to the existing replay file")
    parser.add_argument("--raw-dir", default="", help="folder of the capture to re-assemble (default out/replay_raw/<lang>)")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    cfg = LANGS[args.lang]
    if args.english_only:
        path = pathlib.Path(args.out) / f"replay-{cfg['name']}.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        count = await english_display(payload["events"])
        if count and ENGLISH_NOTE not in payload["description"]:
            payload["description"] = payload["description"].replace(" Transcripts are shown in Devanagari.", "") + ENGLISH_NOTE
        path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"translated {count} transcript lines in {path.name}")
        return
    raw_dir = pathlib.Path(args.raw_dir) if args.raw_dir else ROOT / "out" / "replay_raw" / args.lang
    lay = rec = None
    for attempt in range(1, args.attempts + 1):
        print(f"--- attempt {attempt} ---")
        if args.from_raw:
            rec = load_raw(raw_dir)
        else:
            rec = await record(args, cfg)
            save_raw(rec, raw_dir)
        await recover_ended(rec)
        if args.lang == "hindi":
            await normalise_hindi(rec)
        lay = choose(rec, args)
        if lay or args.from_raw:
            break
    if not lay:
        raise SystemExit("no recording landed in the time window with clean language; the last capture is in out/replay_raw")

    out = pathlib.Path(args.out)
    name = f"replay-{cfg['name']}"
    events = remap_events(rec, lay, cfg)
    if args.lang == "hindi":
        await english_display(events)
    for event in events:
        event.pop("playToken", None)
    write_wav(out / f"{name}.wav", lay)
    left_out = sum(1 for e in rec["events"] if e["type"] == "detail" and spurious(e["detail"], cfg))
    note = (
        f" {left_out} detail(s) the speech recogniser invented from audio noise (nothing like them was said) are left out."
        if left_out
        else ""
    )
    if args.lang == "hindi":
        note += ENGLISH_NOTE
    payload = {
        "version": 3,
        "title": cfg["title"],
        "description": (
            "An AI scammer (a Gemini script-writer reacting to the decoy's actual words, voiced by Gemini text-to-speech, "
            "all fictional) phones the live decoy. Everything on the right, from the transcript to the confirmed UPI ID "
            "and bank account, was produced by the real pipeline during this call. Both voices are exactly what each "
            "side produced; the pauses between turns are shortened, and the measured reply delay is in the stats." + note
        ),
        "language": args.lang,
        "durationSec": round(lay["duration"], 1),
        "audio": f"replay/{name}.wav",
        "events": events,
    }
    (out / f"{name}.json").write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    ended = next((e for e in events if e["type"] == "ended"), {})
    print(f"saved {name}.json: {lay['n']} exchanges, {lay['duration']:.0f}s, {len(events)} events, strain={'strain' in ended}")
    try:
        import compress_replay  # sits next to this script

        compress_replay.main(name)
    except ImportError:
        print("lameenc is not installed, leaving the large wav in place (pip install lameenc to shrink it)")


if __name__ == "__main__":
    asyncio.run(main())
