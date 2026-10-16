"""Automatic mule-account reports with a confidence gate and a cross-call watchlist.

Confidence of one sighting = how sure we are the call is a scam x how sure we caught the identifier right
(the scam verdict's confidence x the detail's two-check confidence). Nothing counts for a genuine or undetermined call.

- Below BANK_WATCH_CONFIDENCE (45%): ignored.
- From 45%: stored on the identifier's record (mule_accounts/{key}, one per UPI ID or account number, across calls).
- Every call that gives the same identifier adds its own sighting; the record's confidence combines independent calls
  as 1 - (1 - c1)(1 - c2)..., so two 50% calls make 75%. One call never counts twice.
- At BANK_REPORT_CONFIDENCE (65%) or more, a signed report goes to the bank (once per identifier per call), routed by
  IFSC, UPI handle or a bank the caller named; a route found in any earlier call is reused.
The decision runs inside a Firestore transaction, so two calls finishing together cannot both miss or double-send it.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import secrets
import time
from datetime import datetime, timezone
from typing import Awaitable, Callable

import httpx

import analysis
import bank_registry as registry
import config
from store import expiry, store

log = logging.getLogger("stallwart.banks")

SCHEMA = "stallwart.mule_report.v1"
REPORTABLE = ("upi_id", "bank_account")
CONTEXT_TYPES = ("phone_number", "person_name", "organisation_claimed", "case_or_badge_id", "amount_demanded", "url",
                 "app_name")
DECISIONS = ("monitoring", "frozen", "dismissed")
SIGNATURE_TOLERANCE_SEC = 300

_PROCESS_SECRET = secrets.token_bytes(32)


# ----- signing and bank keys -----


def _master() -> bytes:
    return config.BANK_SIGNING_SECRET.encode() if config.BANK_SIGNING_SECRET else _PROCESS_SECRET


def _bank_secret(code: str) -> bytes:
    return hmac.new(_master(), f"webhook:{code}".encode(), hashlib.sha256).digest()


def sign(code: str, timestamp: str, body: bytes) -> str:
    return "sha256=" + hmac.new(_bank_secret(code), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()


def verify_signature(code: str, timestamp: str, signature: str, body: bytes, now: float | None = None) -> bool:
    try:
        age = abs((now or time.time()) - int(timestamp))
    except (TypeError, ValueError):
        return False
    return age <= SIGNATURE_TOLERANCE_SEC and hmac.compare_digest(sign(code, timestamp, body), signature or "")


def bank_api_key(code: str) -> str | None:
    """The key a bank uses for the bank API. None while no signing secret is configured (API switched off)."""
    if not config.BANK_SIGNING_SECRET:
        return None
    return hmac.new(_master(), f"api:{code}".encode(), hashlib.sha256).hexdigest()[:40]


def check_bank_key(code: str, key: str | None) -> bool:
    expected = bank_api_key(code)
    return bool(expected and key and hmac.compare_digest(expected, key))


# ----- routing -----


def mule_key(detail_type: str, value: str) -> str:
    """One key per identifier across every call and bank, so a later call finds the earlier sightings."""
    return hashlib.sha256(f"{detail_type}:{value.lower()}".encode()).hexdigest()[:24]


def mask(value: str) -> str:
    return "•" * max(0, len(value) - 4) + value[-4:]


def _first_turn(detail: dict) -> int:
    return min(detail.get("turns") or [0])


def route_detail(detail: dict, details: dict[str, dict], turns: list[dict], final: bool = False) -> registry.Route | None:
    """Where this detail must be reported, or None while an account number is still waiting for its IFSC."""
    if detail["type"] == "upi_id":
        return registry.from_upi(detail["normalizedValue"])
    ifscs = []
    for other in details.values():
        if other["type"] == "ifsc" and other["valid"]:
            route = registry.from_ifsc(other["normalizedValue"])
            if route:
                ifscs.append((other, route))
    if ifscs:
        here = _first_turn(detail)
        # The IFSC said closest to the account wins; on a tie, the later one (callers usually give the IFSC after).
        return min(ifscs, key=lambda pair: (abs(_first_turn(pair[0]) - here), -_first_turn(pair[0])))[1]
    if not final:
        return None
    said = [detail.get("evidence", "")] + [t["text"] for t in turns
                                           if t["speaker"] == "caller" and t["n"] in (detail.get("turns") or [])]
    named = registry.banks_named_in(" ".join(said))
    if len(named) == 1:
        code = named[0]
        return registry.Route(code, registry.bank_name(code), "bank_named",
                              f"No IFSC was given; the caller named {registry.bank_name(code)} with this account")
    reason = "The caller named more than one bank with this account" if named else \
        "No IFSC and no bank name came with this account number"
    return registry.Route(registry.UNRESOLVED, registry.UNRESOLVED_NAME, "unresolved", reason)


# ----- confidence and the watchlist -----

_ROUTE_RANK = {"ifsc": 3, "upi_handle": 3, "bank_named": 2, "unresolved": 1}


def sighting_confidence(detail: dict, scam_confidence: float) -> float:
    if not detail.get("valid"):
        return 0.0
    return round(float(detail.get("confidence") or 0) * scam_confidence, 2)


def combine(calls: dict[str, float]) -> float:
    """Independent calls corroborate each other: the chance that every one of them is wrong shrinks."""
    miss = 1.0
    for confidence in calls.values():
        miss *= 1.0 - confidence
    return round(1.0 - miss, 2)


def route_dict(route: registry.Route | None) -> dict | None:
    if route is None:
        return None
    return {"bankCode": route.bank_code, "bankName": route.bank_name, "routedBy": route.routed_by,
            "reason": route.reason, "ifsc": route.ifsc, "upiApp": route.upi_app}


def better_route(a: dict | None, b: dict | None) -> dict | None:
    if not a or not b:
        return a or b
    return b if _ROUTE_RANK.get(b["routedBy"], 0) >= _ROUTE_RANK.get(a["routedBy"], 0) else a


def apply_sighting(doc: dict | None, *, key: str, detail_type: str, value: str, call_id: str, confidence: float,
                   route: dict | None, final: bool, now: datetime, expires: datetime) -> tuple[dict, dict]:
    """Pure: the identifier record after this call's sighting, and whether this call must send a report now."""
    doc = dict(doc or {})
    calls = {k: float(v) for k, v in (doc.get("calls") or {}).items()}
    previous = [c for c in calls if c != call_id]
    calls[call_id] = max(confidence, calls.get(call_id, 0.0))
    combined = combine(calls)
    best = better_route(doc.get("route"), route)
    reported_calls = list(doc.get("reportedCalls") or [])
    # An account number may still get its IFSC later in this call, so the unresolved queue only takes it at the end.
    routable = best is not None and (best["routedBy"] != "unresolved" or final or detail_type == "upi_id")
    send = combined >= config.BANK_REPORT_CONFIDENCE and call_id not in reported_calls and routable
    if send:
        reported_calls.append(call_id)
    new = {**doc, "muleKey": key, "type": detail_type, "value": value, "calls": calls, "confidence": combined,
           "sightings": len(calls), "reportedCalls": reported_calls,
           "stage": "reported" if reported_calls else "watching", "lastSeenAt": now, "expiresAt": expires}
    new.setdefault("firstSeenAt", now)
    if best:
        new.update(route=best, bankCode=best["bankCode"], bankName=best["bankName"], routedBy=best["routedBy"])
    if send:
        new.setdefault("status", "reported")
    return new, {"send": send, "combined": combined, "calls": calls, "previousCalls": previous, "route": best,
                 "stage": new["stage"], "bankStatus": new.get("status", "reported"),
                 "firstSeenAt": new["firstSeenAt"]}


# ----- the report -----


def _iso(value) -> str | None:
    return value.isoformat() if isinstance(value, datetime) else value


def _jlog(message: str, **fields) -> None:
    print(json.dumps({"severity": "INFO", "message": message, **fields}), flush=True)


def build_payload(*, report_id: str, route: dict, detail: dict, context: dict, outcome: dict, this_call: float) -> dict:
    details = context.get("details", {})
    combined = outcome["combined"]
    linked = []
    for other in details.values():
        same = other["type"] == detail["type"] and other["normalizedValue"] == detail["normalizedValue"]
        if same or not other.get("valid"):
            continue
        if other["type"] in CONTEXT_TYPES:
            linked.append({"type": other["type"], "value": other["normalizedValue"]})
        elif other["type"] in REPORTABLE:
            # Another bank's identifier: enough to link the cases, not enough to act on it here.
            other_route = route_detail(other, details, context.get("turns", []), final=True)
            linked.append({"type": other["type"], "bank": other_route.bank_name if other_route else None,
                           "valueMasked": mask(other["normalizedValue"])})
    subject = {
        "type": detail["type"],
        "value": detail["normalizedValue"],
        "valid": detail["valid"],
        "confirmedBy": detail.get("sources", []),
        "confidence": detail.get("confidence"),
        "callerQuote": detail.get("evidence", ""),
        "firstSeenSec": detail.get("firstSeenSec"),
        "routedBy": route["routedBy"],
        "routingReason": route["reason"],
    }
    if route.get("ifsc"):
        subject["ifsc"] = route["ifsc"]
    if route.get("upiApp"):
        subject["upiApp"] = route["upiApp"]
    return {
        "schema": SCHEMA,
        "reportId": report_id,
        "sentAt": analysis.now_iso(),
        "reportedBy": "Stallwart decoy line (prototype)",
        "bank": {"code": route["bankCode"], "name": route["bankName"]},
        "subject": subject,
        "call": {
            "callId": context.get("callId"),
            "startedAt": context.get("startedAt"),
            "verdict": context.get("verdict"),
            "scamType": context.get("scamType"),
            "impersonatedEntity": context.get("impersonatedEntity"),
            "redFlags": [{"signal": f["signal"], "label": f["label"], "quote": f.get("quote", "")}
                         for f in context.get("redFlags", [])],
        },
        "linkedDetails": linked,
        "confidence": {
            "report": combined,
            "thisCall": this_call,
            "threshold": config.BANK_REPORT_CONFIDENCE,
            "method": "per call: scam-verdict confidence x detail confidence; across calls: 1 - product(1 - c)",
            "promotedFromWatchlist": bool(outcome["previousCalls"]),
        },
        "aggregate": {
            "sightings": len(outcome["calls"]),
            "callCount": len(outcome["calls"]),
            "firstSeenAt": _iso(outcome.get("firstSeenAt")),
            "bankStatus": outcome.get("bankStatus", "reported"),
        },
        "recommendedAction": "review_for_freeze" if combined >= 0.8 else "monitor",
        "disclaimer": analysis.DISCLAIMER,
    }


# ----- delivery and the proxy bank receiver -----


async def receive(code: str, headers: dict[str, str], body: bytes) -> tuple[int, dict]:
    """The proxy bank's webhook: verify, de-duplicate, file the report in the bank's inbox."""
    h = {k.lower(): v for k, v in headers.items()}
    if code not in registry.BANKS and code != registry.UNRESOLVED:
        return 404, {"error": "unknown bank"}
    if not verify_signature(code, h.get("x-stallwart-timestamp", ""), h.get("x-stallwart-signature", ""), body):
        return 401, {"error": "bad signature"}
    try:
        payload = json.loads(body)
        report_id = str(payload["reportId"])
    except (ValueError, KeyError, TypeError):
        return 400, {"error": "malformed report"}
    if payload.get("bank", {}).get("code") != code or h.get("idempotency-key", report_id) != report_id:
        return 400, {"error": "report is for another bank"}
    existing = await store.get(f"bank_reports/{report_id}")
    if existing and existing.get("receivedAt"):
        return 200, {"status": "duplicate", "reportId": report_id}
    await store.update(f"bank_reports/{report_id}", {"status": "delivered", "verified": True,
                                                     "receivedAt": datetime.now(timezone.utc)})
    return 200, {"status": "accepted", "reportId": report_id}


async def deliver(code: str, body: bytes, report_id: str, attempts: int = 3) -> bool:
    timestamp = str(int(time.time()))
    headers = {"Content-Type": "application/json", "X-Stallwart-Timestamp": timestamp,
               "X-Stallwart-Signature": sign(code, timestamp, body), "Idempotency-Key": report_id}
    for attempt in range(attempts):
        try:
            if config.BANK_DELIVERY == "http" and config.BANK_WEBHOOK_BASE:
                async with httpx.AsyncClient(timeout=10) as client:
                    response = await client.post(f"{config.BANK_WEBHOOK_BASE}/proxy-banks/{code}/webhook",
                                                 content=body, headers=headers)
                status = response.status_code
            else:
                status, _ = await receive(code, headers, body)
            if status < 300:
                return True
            if status < 500:
                log.warning("bank %s rejected report %s (%s)", code, report_id, status)
                return False
        except Exception:  # noqa: BLE001 - retried below
            log.warning("delivery of report %s to %s failed (attempt %d)", report_id, code, attempt + 1)
        await asyncio.sleep(0.5 * 2**attempt)
    return False


class BankReporter:
    """One per call. Scores each UPI ID and account number, keeps 45-65% ones on the watchlist, and reports to the
    bank once the identifier's confidence (this call plus earlier calls) reaches 65%."""

    def __init__(self, *, call_id: str, owner: str, emit: Callable[[dict], Awaitable[None]],
                 spawn: Callable[[Awaitable], None], context: Callable[[], dict]) -> None:
        self.call_id = call_id
        self.owner = owner
        self.emit = emit
        self.spawn = spawn
        self.context = context
        self.scam_confidence = 0.0
        self.items: dict[str, dict] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def set_verdict(self, verdict: str | None, confidence: float | None = None) -> None:
        # Red flags are cumulative, so a scam verdict and its confidence only ever grow during a call.
        if verdict == "scam":
            self.scam_confidence = max(self.scam_confidence, float(confidence or 0))

    async def sweep(self, details: dict[str, dict], turns: list[dict], final: bool = False) -> None:
        if self.scam_confidence <= 0:
            return
        for detail in list(details.values()):
            if detail["type"] not in REPORTABLE:
                continue
            confidence = sighting_confidence(detail, self.scam_confidence)
            if confidence < config.BANK_WATCH_CONFIDENCE:
                continue
            key = mule_key(detail["type"], detail["normalizedValue"])
            route = route_detail(detail, details, turns, final=final)
            item = self.items.get(key)
            if item is None:
                item = self.items[key] = {
                    "key": key, "detailType": detail["type"], "value": detail["normalizedValue"],
                    "stage": "watching", "status": None, "thisCall": 0.0, "confidence": 0.0, "sightings": 0,
                    "routeKnown": False, "finalChecked": False, "sent": False, "tSec": detail.get("firstSeenSec"),
                }
            waiting = not item["sent"] and ((route is not None and not item["routeKnown"]) or
                                            (final and not item["finalChecked"]))
            if confidence <= item["thisCall"] and not waiting:
                continue
            item["thisCall"] = max(item["thisCall"], confidence)
            item["routeKnown"] = item["routeKnown"] or route is not None
            item["finalChecked"] = item["finalChecked"] or final
            self.spawn(self._update(key, dict(detail), confidence, route_dict(route), final))

    async def _update(self, key: str, detail: dict, confidence: float, route: dict | None, final: bool) -> None:
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            now = datetime.now(timezone.utc)
            outcome = await store.transact(f"mule_accounts/{key}", lambda doc: apply_sighting(
                doc, key=key, detail_type=detail["type"], value=detail["normalizedValue"], call_id=self.call_id,
                confidence=confidence, route=route, final=final, now=now, expires=expiry()))
            if outcome is None:
                return
            item = self.items[key]
            best = outcome["route"] or {}
            item.update(confidence=outcome["combined"], sightings=len(outcome["calls"]), stage=outcome["stage"],
                        bankCode=best.get("bankCode"), bankName=best.get("bankName"), routedBy=best.get("routedBy"),
                        reason=best.get("reason"), bankStatus=outcome["bankStatus"])
            await store.put(f"watch_sightings/{self.call_id}-{key}", {
                "muleKey": key, "callId": self.call_id, "ownerHash": self.owner, "type": item["detailType"],
                "value": item["value"], "thisCall": item["thisCall"], "seenAt": analysis.now_iso(),
            })
            if outcome["send"]:
                item["sent"] = True
                await self._send(item, detail, best, outcome)
            else:
                await self.emit(self._event(item))

    async def _send(self, item: dict, detail: dict, route: dict, outcome: dict) -> None:
        report_id = secrets.token_hex(8)
        context = self.context()
        item.update(reportId=report_id, status="pending",
                    recommendedAction="review_for_freeze" if outcome["combined"] >= 0.8 else "monitor")
        await self.emit(self._event(item))
        payload = build_payload(report_id=report_id, route=route, detail=detail, context=context, outcome=outcome,
                                this_call=item["thisCall"])
        await store.put(f"bank_reports/{report_id}", {
            "reportId": report_id, "muleKey": item["key"], "bankCode": route["bankCode"], "bankName": route["bankName"],
            "detailType": item["detailType"], "value": item["value"], "routedBy": route["routedBy"],
            "callId": self.call_id, "ownerHash": self.owner, "status": "pending", "sentAt": payload["sentAt"],
            "scamType": context.get("scamType"), "recommendedAction": payload["recommendedAction"],
            "confidence": outcome["combined"], "payload": payload,
        })
        body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()
        ok = await deliver(route["bankCode"], body, report_id)
        if not ok:
            await store.update(f"bank_reports/{report_id}", {"status": "failed"})
        item["status"] = "delivered" if ok else "failed"
        _jlog("bank_report", callId=self.call_id, bank=route["bankCode"], type=item["detailType"], status=item["status"],
              confidence=outcome["combined"], calls=len(outcome["calls"]), routedBy=route["routedBy"])
        await self.emit(self._event(item))

    @staticmethod
    def _public(item: dict) -> dict:
        return {k: v for k, v in item.items() if k not in ("routeKnown", "finalChecked")}

    def _event(self, item: dict) -> dict:
        return {"type": "bank_report", **self._public(item)}

    def summary(self) -> list[dict]:
        return [self._public(item) for item in self.items.values()]
