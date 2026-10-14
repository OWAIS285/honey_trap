"""Simulated scammer: drives /ws/call or /ws/text with typed lines and prints what the backend emits."""

import argparse
import asyncio
import json
import os
import sys
import time
import uuid

import websockets

LINES = {
    "english": [
        "Hello sir, I am calling from the CBI cyber crime department. A parcel in your name was caught with illegal items.",
        "There is an arrest warrant. Do not tell anyone. To clear your name you must transfer 50,000 rupees right now.",
        "The UPI ID is rahul dot sharma at okaxis. Please confirm the ID back to me.",
        "Yes that is correct, rahul dot sharma at okaxis. If you cannot use UPI, the bank account is "
        "one two three four five six seven eight nine zero one two, IFSC S B I N zero zero zero one two three four.",
    ],
    "hinglish": [
        "Hello uncle, main CBI officer bol raha hoon. Aapke Aadhaar se ek parcel pakda gaya hai.",
        "Arrest warrant ready hai. Kisi ko mat batana. Abhi pachaas hazaar rupaye bhejne honge.",
        "UPI ID hai rahul dot sharma at okaxis. Dobara bataiye jo maine bola.",
        "Haan sahi hai. Account number hai nau aath saat chhe paanch char teen do ek shunya, IFSC SBIN0001234.",
    ],
}


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="ws://localhost:8080")
    parser.add_argument("--mode", choices=["call", "text"], default="text")
    parser.add_argument("--lang", choices=list(LINES), default="english")
    parser.add_argument("--origin", default="http://localhost:5000")
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    lines = LINES[args.lang]
    client_id = uuid.uuid4().hex
    events: list[dict] = []
    audio_bytes = 0
    persona_finals = 0
    sent = 0
    started = time.monotonic()

    async with websockets.connect(f"{args.url}/ws/{args.mode}", additional_headers={"Origin": args.origin},
                                  max_size=None) as ws:
        await ws.send(json.dumps({"type": "start", "clientId": client_id}))

        async def silence() -> None:
            while True:
                await ws.send(b"\x00" * 1280)
                await asyncio.sleep(0.04)

        silence_task = asyncio.create_task(silence()) if args.mode == "call" else None
        last_final = time.monotonic()
        try:
            while True:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
                except asyncio.TimeoutError:
                    msg = None
                if msg is None:
                    if sent >= len(lines) and time.monotonic() - last_final > 9:
                        await ws.send(json.dumps({"type": "end"}))
                        sent += 1
                    elif persona_finals > sent and sent < len(lines) and time.monotonic() - last_final > 1.5:
                        await ws.send(json.dumps({"type": "text", "text": lines[sent]}))
                        print(f"  >> caller typed line {sent + 1}")
                        sent += 1
                    elif time.monotonic() - started > 120:
                        break
                    continue
                if isinstance(msg, bytes):
                    audio_bytes += len(msg)
                    continue
                event = json.loads(msg)
                events.append({"t": round(time.monotonic() - started, 1), **event})
                kind = event.get("type")
                if kind == "transcript" and event.get("final"):
                    print(f"[{event['speaker']:7}] {event['text']}")
                    last_final = time.monotonic()
                    if event["speaker"] == "persona":
                        persona_finals += 1
                elif kind == "detail":
                    d = event["detail"]
                    print(f"  DETAIL {d['type']:20} {d['normalizedValue']:30} valid={d['valid']} confirmed={d['confirmed']} via={d['sources']}")
                elif kind == "classification":
                    print(f"  CLASS  {event['scamType']} {event['confidence']} stage={event['stage']} triggers={event['triggerPhrases']}")
                elif kind in ("ready", "error", "ended", "stage", "time_limit"):
                    brief = {k: v for k, v in event.items() if k not in ("strain", "playToken")}
                    print(f"  {kind.upper()} {json.dumps(brief, ensure_ascii=False)[:300]}")
                    if kind == "ended":
                        strain = event.get("strain")
                        if strain:
                            print(f"  STRAIN {json.dumps(strain, ensure_ascii=False)[:600]}")
                        break
                    if kind == "error":
                        break
        except websockets.ConnectionClosed:
            pass
        finally:
            if silence_task:
                silence_task.cancel()
    print(f"audio bytes received: {audio_bytes}")
    if args.out:
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump({"clientId": client_id, "events": events, "audioBytes": audio_bytes}, f, ensure_ascii=False, indent=1)
        print(f"saved {args.out}")


if __name__ == "__main__":
    asyncio.run(main())
