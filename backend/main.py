import asyncio
import json
import re
import secrets
from typing import Literal

from fastapi import FastAPI, HTTPException, Request, Response, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import analysis
import bank_registry
import bank_reports
import config
from call_handler import CallHandler, jlog
from drill import DRILL_OPENING_CUE, DRILL_TOOLS, DrillHandler, build_drill_prompt, new_drill_doc
from limits import limiter
from live_session import LiveSession
from persona import OPENING_CUE, PERSONA_TOOLS, CallProfile, build_persona
from store import clean, owner_hash, store
from text_session import TextSession

ALLOWED_ORIGINS = config.ALLOWED_ORIGINS
KILL_SWITCH = config.KILL_SWITCH

app = FastAPI(title="stallwart-api")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS or ["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


def origin_allowed(origin: str | None) -> bool:
    return not ALLOWED_ORIGINS or origin in ALLOWED_ORIGINS


def client_ip(conn) -> str:
    forwarded = conn.headers.get("x-forwarded-for", "")
    return forwarded.split(",")[0].strip() or (conn.client.host if conn.client else "unknown")


def require_client_id(value: str | None) -> str:
    if not value or not re.fullmatch(r"[A-Za-z0-9_-]{16,64}", value):
        raise HTTPException(400, "Missing or invalid X-Client-Id header.")
    return value


async def owned_call(call_id: str, client_id: str | None) -> dict:
    doc = await store.get(f"calls/{call_id}")
    if not doc or doc.get("ownerHash") != owner_hash(require_client_id(client_id)):
        raise HTTPException(404, "Call not found.")
    return doc


async def find_strain(strain_id: str, owner: str | None = None) -> dict | None:
    for demo in analysis.DEMO_STRAINS:
        if demo["strainId"] == strain_id:
            return demo
    doc = await store.get(f"strains/{strain_id}")
    if doc and (owner is None or doc.get("ownerHash") == owner):
        return doc
    return None


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "killSwitch": KILL_SWITCH}


@app.get("/api/config")
def api_config() -> dict:
    return {
        "persona": {"name": "Ramesh Sharma", "age": 68, "voice": config.PERSONA_VOICE},
        "maxCallSeconds": config.MAX_CALL_SECONDS,
        "maxDrillSeconds": config.MAX_DRILL_SECONDS,
        "killSwitch": KILL_SWITCH,
        "languages": ["English", "Hindi", "Hinglish"],
    }


# ---------- calls, evidence, recordings ----------


@app.get("/api/calls")
async def list_calls(request: Request) -> dict:
    owner = owner_hash(require_client_id(request.headers.get("x-client-id")))
    docs = await store.list_owned("calls", owner)
    calls = [clean({k: v for k, v in d.items() if k != "playToken"}) for d in docs]
    calls.sort(key=lambda c: c.get("startedAt", ""), reverse=True)
    return {"calls": calls}


@app.get("/api/calls/{call_id}")
async def get_call(call_id: str, request: Request) -> dict:
    call = await owned_call(call_id, request.headers.get("x-client-id"))
    turns = await store.list_sub(f"calls/{call_id}/turns", order="n")
    details = await store.list_sub(f"calls/{call_id}/details")
    strain = await find_strain(call["strainId"]) if call.get("strainId") else None
    play = f"/api/calls/{call_id}/recording?t={call.get('playToken')}" if call.get("recording") else None
    return {
        "call": clean(call),
        "turns": turns,
        "details": sorted(details, key=lambda d: (not d.get("confirmed"), d.get("firstSeenSec", 0))),
        "strain": clean(strain),
        "recordingUrl": play,
    }


@app.get("/api/calls/{call_id}/evidence")
async def get_evidence(call_id: str, request: Request) -> Response:
    call = await owned_call(call_id, request.headers.get("x-client-id"))
    turns = await store.list_sub(f"calls/{call_id}/turns", order="n")
    details = await store.list_sub(f"calls/{call_id}/details")
    strain = await find_strain(call["strainId"]) if call.get("strainId") else None
    pack = analysis.build_evidence(clean(call), turns, details, clean(strain))
    return Response(
        json.dumps(pack, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="evidence-{call_id}.json"'},
    )


@app.get("/api/calls/{call_id}/recording")
async def get_recording(call_id: str, request: Request, t: str, download: int = 0) -> Response:
    doc = await store.get(f"calls/{call_id}")
    if not doc or not doc.get("recording") or not secrets.compare_digest(str(doc.get("playToken", "")), t):
        raise HTTPException(404, "Recording not found.")
    data = await store.get_recording(doc["recording"]["path"])
    if not data:
        raise HTTPException(404, "Recording not found.")
    total = len(data)
    headers = {"Accept-Ranges": "bytes", "Cache-Control": "private, max-age=3600"}
    if download:
        headers["Content-Disposition"] = f'attachment; filename="call-{call_id}.wav"'
    match = re.match(r"bytes=(\d*)-(\d*)", request.headers.get("range", ""))
    if match:
        start = int(match.group(1) or 0)
        end = min(int(match.group(2)) if match.group(2) else total - 1, total - 1)
        if start > end:
            raise HTTPException(416, "Bad range.")
        headers["Content-Range"] = f"bytes {start}-{end}/{total}"
        return Response(data[start : end + 1], 206, headers=headers, media_type="audio/wav")
    return Response(data, media_type="audio/wav", headers=headers)


@app.get("/api/strains")
async def list_strains(request: Request) -> dict:
    owner = owner_hash(require_client_id(request.headers.get("x-client-id")))
    docs = await store.list_owned("strains", owner)
    docs.sort(key=lambda d: d.get("createdAt", ""), reverse=True)
    return {"strains": [clean(d) for d in docs] + analysis.DEMO_STRAINS}


# ---------- bank reports ----------


class DecisionIn(BaseModel):
    decision: Literal["monitoring", "frozen", "dismissed"]
    note: str = Field(default="", max_length=300)


def _known_bank(code: str) -> str:
    if code not in bank_registry.BANKS and code != bank_registry.UNRESOLVED:
        raise HTTPException(404, "Unknown bank.")
    return code


async def _with_aggregates(reports: list[dict]) -> list[dict]:
    out = []
    for report in reports:
        mule = await store.get(f"mule_accounts/{report.get('muleKey')}") or {}
        row = clean({k: v for k, v in report.items() if k != "payload"})
        row["sightings"] = mule.get("sightings", 1)
        row["currentConfidence"] = mule.get("confidence", report.get("confidence"))
        row["bankStatus"] = mule.get("status", "reported")
        row["linkedDetails"] = (report.get("payload") or {}).get("linkedDetails", [])
        row["routingReason"] = (report.get("payload") or {}).get("subject", {}).get("routingReason", "")
        out.append(row)
    return out


@app.get("/api/banks")
async def list_banks(request: Request) -> dict:
    """Every proxy bank inbox, with how many reports this browser's calls sent to each."""
    owner = owner_hash(require_client_id(request.headers.get("x-client-id")))
    counts: dict[str, int] = {}
    for report in await store.list_owned("bank_reports", owner, limit=300):
        counts[report.get("bankCode", "")] = counts.get(report.get("bankCode", ""), 0) + 1
    return {"banks": [{**b, "reports": counts.get(b["code"], 0)} for b in bank_registry.directory()],
            "apiEnabled": bool(config.BANK_SIGNING_SECRET)}


@app.get("/api/banks/{code}/reports")
async def bank_inbox_demo(code: str, request: Request) -> dict:
    """A proxy bank's inbox, limited to reports that came from this browser's own calls."""
    owner = owner_hash(require_client_id(request.headers.get("x-client-id")))
    _known_bank(code)
    reports = [r for r in await store.list_owned("bank_reports", owner, limit=300) if r.get("bankCode") == code]
    reports.sort(key=lambda r: r.get("sentAt", ""), reverse=True)
    return {"bank": {"code": code, "name": bank_registry.bank_name(code)}, "reports": await _with_aggregates(reports)}


@app.get("/api/watchlist")
async def watchlist(request: Request) -> dict:
    """UPI IDs and accounts from this browser's scam calls, with their current confidence across every call."""
    owner = owner_hash(require_client_id(request.headers.get("x-client-id")))
    rows: dict[str, dict] = {}
    for seen in await store.list_owned("watch_sightings", owner, limit=300):
        row = rows.setdefault(seen["muleKey"], {"muleKey": seen["muleKey"], "type": seen.get("type"),
                                                "value": seen.get("value"), "yourCalls": 0, "lastSeenAt": ""})
        row["yourCalls"] += 1
        row["lastSeenAt"] = max(row["lastSeenAt"], seen.get("seenAt", ""))
    out = []
    for row in rows.values():
        mule = await store.get(f"mule_accounts/{row['muleKey']}") or {}
        out.append({**row, "confidence": mule.get("confidence", 0.0), "sightings": mule.get("sightings", 0),
                    "stage": mule.get("stage", "watching"), "bankCode": mule.get("bankCode"),
                    "bankName": mule.get("bankName"), "routedBy": mule.get("routedBy")})
    out.sort(key=lambda r: r["lastSeenAt"], reverse=True)
    out.sort(key=lambda r: r["stage"] != "watching")
    return {"items": out, "reportAt": config.BANK_REPORT_CONFIDENCE, "watchAt": config.BANK_WATCH_CONFIDENCE}


@app.post("/api/banks/{code}/reports/{report_id}/decision")
async def bank_decision_demo(code: str, report_id: str, body: DecisionIn, request: Request) -> dict:
    """Play the bank in the demo: record a decision on one of your own reports (never touches the shared record)."""
    owner = owner_hash(require_client_id(request.headers.get("x-client-id")))
    report = await store.get(f"bank_reports/{report_id}")
    if not report or report.get("ownerHash") != owner or report.get("bankCode") != _known_bank(code):
        raise HTTPException(404, "Report not found.")
    await store.update(f"bank_reports/{report_id}", {"simulatedDecision": body.decision, "decisionNote": body.note,
                                                     "decidedAt": analysis.now_iso()})
    return {"reportId": report_id, "simulatedDecision": body.decision}


@app.post("/proxy-banks/{code}/webhook")
async def proxy_bank_webhook(code: str, request: Request) -> Response:
    """Where a bank's real webhook would be: verifies the signature and files the report (BANK_DELIVERY=http)."""
    status, result = await bank_reports.receive(code, dict(request.headers), await request.body())
    return Response(json.dumps(result), status_code=status, media_type="application/json")


def _bank_auth(code: str, request: Request) -> str:
    _known_bank(code)
    if not config.BANK_SIGNING_SECRET:
        raise HTTPException(503, "The bank API is not configured on this server.")
    if not bank_reports.check_bank_key(code, request.headers.get("x-bank-key")):
        raise HTTPException(401, "Missing or invalid X-Bank-Key for this bank.")
    return code


@app.get("/bank-api/v1/{code}/reports")
async def bank_api_reports(code: str, request: Request, limit: int = 100) -> dict:
    """Full signed-report payloads for one bank, newest first."""
    _bank_auth(code, request)
    reports = await store.list_where("bank_reports", "bankCode", code, limit=min(max(limit, 1), 500))
    reports.sort(key=lambda r: r.get("sentAt", ""), reverse=True)
    return {"bank": {"code": code, "name": bank_registry.bank_name(code)},
            "reports": [r.get("payload") for r in reports if r.get("payload")]}


@app.get("/bank-api/v1/{code}/mule-accounts")
async def bank_api_mules(code: str, request: Request) -> dict:
    """Every payee detail reported to this bank, de-duplicated across calls, with how many calls gave it."""
    _bank_auth(code, request)
    # A bank only ever sees identifiers that crossed the report threshold, never the watchlist.
    hidden = ("calls", "reportedCalls", "callIds", "route")
    mules = [clean({k: v for k, v in m.items() if k not in hidden}) | {"callCount": len(m.get("calls") or m.get("callIds") or [])}
             for m in await store.list_where("mule_accounts", "bankCode", code, limit=500)
             if m.get("stage", "reported") == "reported"]
    mules.sort(key=lambda m: (m.get("sightings", 0), m.get("lastSeenAt", "")), reverse=True)
    return {"bank": {"code": code, "name": bank_registry.bank_name(code)}, "muleAccounts": mules}


@app.post("/bank-api/v1/{code}/mule-accounts/{mule_key}/status")
async def bank_api_status(code: str, mule_key: str, body: DecisionIn, request: Request) -> dict:
    """The bank's decision on a reported account, visible on every later report of it."""
    _bank_auth(code, request)
    mule = await store.get(f"mule_accounts/{mule_key}")
    if not mule or mule.get("bankCode") != code or mule.get("stage", "reported") != "reported":
        raise HTTPException(404, "Mule account not found for this bank.")
    await store.update(f"mule_accounts/{mule_key}", {"status": body.decision, "statusNote": body.note,
                                                     "statusAt": analysis.now_iso()})
    return {"muleKey": mule_key, "status": body.decision}


# ---------- family drills ----------

PARENT_TITLES = {"mother": "Amma", "father": "Papa", "elder": "Ji"}


class DrillIn(BaseModel):
    strainId: str
    parentName: str = Field(min_length=1, max_length=60)
    parentTitle: Literal["mother", "father", "elder"] = "elder"
    familyName: str = Field(min_length=1, max_length=60)
    consent: bool


@app.post("/api/drills")
async def create_drill(body: DrillIn, request: Request) -> dict:
    owner = owner_hash(require_client_id(request.headers.get("x-client-id")))
    if not body.consent:
        raise HTTPException(400, "Consent is required before any drill can be created.")
    strain = await find_strain(body.strainId, owner)
    if not strain:
        raise HTTPException(404, "Strain not found.")
    doc = new_drill_doc(owner=owner, strain_id=body.strainId, parent_name=body.parentName.strip(),
                        parent_title=PARENT_TITLES[body.parentTitle], family_name=body.familyName.strip())
    await store.put(f"drills/{doc['drillId']}", doc)
    return {"drillId": doc["drillId"], "shareKey": doc["shareKey"]}


@app.get("/api/drills")
async def list_drills(request: Request) -> dict:
    owner = owner_hash(require_client_id(request.headers.get("x-client-id")))
    docs = await store.list_owned("drills", owner)
    docs.sort(key=lambda d: d.get("createdAt", ""), reverse=True)
    return {"drills": [{**clean(d), "shareKey": d.get("shareKey")} for d in docs]}


@app.get("/api/drills/{drill_id}")
async def get_drill(drill_id: str, request: Request) -> dict:
    owner = owner_hash(require_client_id(request.headers.get("x-client-id")))
    doc = await store.get(f"drills/{drill_id}")
    if not doc or doc.get("ownerHash") != owner:
        raise HTTPException(404, "Drill not found.")
    strain = await find_strain(doc["strainId"])
    return {"drill": {**clean(doc), "shareKey": doc.get("shareKey")}, "strain": clean(strain)}


@app.get("/api/drills/{drill_id}/invite")
async def drill_invite(drill_id: str, k: str) -> dict:
    doc = await store.get(f"drills/{drill_id}")
    if not doc or not secrets.compare_digest(str(doc.get("shareKey", "")), k):
        raise HTTPException(404, "Invitation not found.")
    return {"parentName": doc["parentName"], "parentTitle": doc["parentTitle"], "familyName": doc["familyName"],
            "maxSeconds": config.MAX_DRILL_SECONDS}


# ---------- websockets ----------


@app.websocket("/ws/echo")
async def ws_echo(ws: WebSocket) -> None:
    if not origin_allowed(ws.headers.get("origin")):
        await ws.close(code=1008)
        return
    await ws.accept()
    try:
        while True:
            await ws.send_text(await ws.receive_text())
    except Exception:  # noqa: BLE001 - disconnect ends the echo
        pass


async def _read_start(ws: WebSocket) -> dict:
    try:
        data = json.loads(await asyncio.wait_for(ws.receive_text(), 10))
    except Exception:  # noqa: BLE001
        return {}
    return data if isinstance(data, dict) and data.get("type") == "start" else {}


async def _refuse(ws: WebSocket, code: str, message: str) -> None:
    try:
        await ws.send_json({"type": "error", "code": code, "message": message})
        await ws.close(code=1008)
    except Exception:  # noqa: BLE001
        pass


async def _guard(ws: WebSocket) -> dict | None:
    """Origin, kill switch and rate limit checks shared by every session endpoint."""
    if not origin_allowed(ws.headers.get("origin")):
        await ws.close(code=1008)
        return None
    await ws.accept()
    start = await _read_start(ws)
    if KILL_SWITCH:
        await _refuse(ws, "disabled", "Live sessions are paused. Please use the replay demo.")
        return None
    reason = limiter.check(client_ip(ws))
    if reason:
        await _refuse(ws, "busy", reason)
        return None
    return start


async def _run_call(ws: WebSocket, mode: str) -> None:
    start = await _guard(ws)
    if start is None:
        return
    try:
        client_id = require_client_id(start.get("clientId"))
    except HTTPException:
        await _refuse(ws, "bad_request", "Missing client id.")
        return
    ip = client_ip(ws)
    limiter.enter(ip)
    try:
        profile = CallProfile()
        handler = CallHandler(client_id=client_id, ip=ip, mode=mode, record=profile.record)
        await store.put(f"calls/{handler.call_id}", handler.initial_doc())
        if mode == "live":
            jlog("INFO", "persona_profile", callId=handler.call_id, mood=profile.mood_key)
            session = LiveSession(ws, handler, system_instruction=build_persona(profile), voice=config.PERSONA_VOICE,
                                  tools=PERSONA_TOOLS, max_seconds=config.MAX_CALL_SECONDS, opening_cue=OPENING_CUE,
                                  temperature=config.PERSONA_TEMPERATURE)
        else:
            session = TextSession(ws, handler, profile)
        handler.emit = session.send
        await session.send({"type": "ready", "callId": handler.call_id, "playToken": handler.play_token,
                            "mode": mode, "maxSeconds": config.MAX_CALL_SECONDS})
        # Shown to the tester so they can play a genuine bank: a real bank has these endings on screen.
        await session.send({"type": "record", **profile.record.public()})
        jlog("INFO", "call_started", callId=handler.call_id, mode=mode)
        reason = await session.run()
        await handler.finish(reason)
    finally:
        limiter.leave()
    try:
        await ws.close()
    except Exception:  # noqa: BLE001
        pass


@app.websocket("/ws/call")
async def ws_call(ws: WebSocket) -> None:
    await _run_call(ws, "live")


@app.websocket("/ws/text")
async def ws_text(ws: WebSocket) -> None:
    await _run_call(ws, "text")


@app.websocket("/ws/drill")
async def ws_drill(ws: WebSocket) -> None:
    start = await _guard(ws)
    if start is None:
        return
    drill = await store.get(f"drills/{start.get('drillId', '')}")
    if not drill or not drill.get("consentGiven") or not secrets.compare_digest(
        str(drill.get("shareKey", "")), str(start.get("key", ""))
    ):
        await _refuse(ws, "not_found", "This drill invitation is not valid.")
        return
    strain = await find_strain(drill["strainId"])
    if not strain:
        await _refuse(ws, "not_found", "This drill is no longer available.")
        return
    ip = client_ip(ws)
    limiter.enter(ip)
    try:
        handler = DrillHandler(drill, strain)
        session = LiveSession(ws, handler, system_instruction=build_drill_prompt(strain, drill["parentTitle"]),
                              voice=config.DRILL_VOICE, tools=DRILL_TOOLS, max_seconds=config.MAX_DRILL_SECONDS,
                              opening_cue=DRILL_OPENING_CUE, grace_seconds=45)
        handler.emit = session.send
        await session.send({"type": "ready", "drillId": drill["drillId"], "maxSeconds": config.MAX_DRILL_SECONDS,
                            "steps": len(strain.get("steps", []))})
        jlog("INFO", "drill_started", drillId=drill["drillId"])
        reason = await session.run()
        await handler.finish(reason)
    finally:
        limiter.leave()
    try:
        await ws.close()
    except Exception:  # noqa: BLE001
        pass
