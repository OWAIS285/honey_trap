"""Drive the family drill: create it with consent, then play the elder who either stays safe or shares an OTP."""

import argparse
import asyncio
import json
import sys
import time
import uuid

import requests
import websockets

SAFE = ["Haan ji, kaun bol raha hai?", "Arre baap re, mujhe toh kuch samajh nahi aa raha.", "Main apne bete se pooch kar batata hoon."]
SHARE = ["Haan ji kaun?", "Achha achha. Mera OTP hai 4 5 6 7 8 9."]


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://localhost:8080")
    parser.add_argument("--scenario", choices=["safe", "share"], default="safe")
    parser.add_argument("--origin", default="http://localhost:5000")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    cid = uuid.uuid4().hex
    no_consent = requests.post(args.api + "/api/drills", headers={"X-Client-Id": cid}, json={
        "strainId": "demo_digital_arrest", "parentName": "Asha", "parentTitle": "mother", "familyName": "Ravi",
        "consent": False})
    print("without consent ->", no_consent.status_code)
    drill = requests.post(args.api + "/api/drills", headers={"X-Client-Id": cid}, json={
        "strainId": "demo_digital_arrest", "parentName": "Asha", "parentTitle": "mother", "familyName": "Ravi",
        "consent": True}).json()
    print("drill created:", drill["drillId"])
    lines = SAFE if args.scenario == "safe" else SHARE
    ws_url = args.api.replace("http", "ws") + "/ws/drill"
    async with websockets.connect(ws_url, additional_headers={"Origin": args.origin}, max_size=None) as ws:
        await ws.send(json.dumps({"type": "start", "drillId": drill["drillId"], "key": drill["shareKey"]}))
        sent, actor_final, last = 0, 0, time.monotonic()
        started = time.monotonic()
        while time.monotonic() - started < 150:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
            except asyncio.TimeoutError:
                if actor_final > sent and sent < len(lines) and time.monotonic() - last > 1.5:
                    await ws.send(json.dumps({"type": "text", "text": lines[sent]}))
                    print(f"  >> elder: {lines[sent]}")
                    sent += 1
                continue
            except websockets.ConnectionClosed:
                break
            if isinstance(msg, bytes):
                continue
            ev = json.loads(msg)
            kind = ev.get("type")
            if kind == "transcript" and ev.get("final") is False and ev["speaker"] == "actor":
                continue
            if kind in ("step", "coach", "ended", "error", "ready"):
                print(" ", kind.upper(), json.dumps({k: v for k, v in ev.items() if k != "type"}, ensure_ascii=False)[:400])
                if kind == "step":
                    actor_final = max(actor_final, ev["step"])
                    last = time.monotonic()
                if kind in ("ended", "error"):
                    break
    report = requests.get(f"{args.api}/api/drills/{drill['drillId']}", headers={"X-Client-Id": cid}).json()["drill"]
    print("REPORT:", {k: report.get(k) for k in ("status", "outcome", "stopReason", "stoppedAtStep", "stepsTotal")})


if __name__ == "__main__":
    asyncio.run(main())
