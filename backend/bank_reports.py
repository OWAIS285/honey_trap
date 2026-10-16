"""Automatic mule-account reports: route each confirmed payee detail to its bank and deliver a signed report.

Flow for one call:
1. A UPI ID or account number becomes confirmed (two checks, valid format) in a call whose verdict is scam.
   Nothing is ever sent for a genuine or undetermined call.
2. bank_registry decides the bank (IFSC, UPI handle, or a bank the caller named); an account number with no IFSC
   waits until the end of the call before falling back to a named bank or the UNRESOLVED queue.
3. The detail is counted on its bank-wide aggregate (mule_accounts/{key}): every call that gives it adds a sighting.
4. A report (schema stallwart.mule_report.v1) is signed with HMAC-SHA256 and delivered to the bank's proxy inbox,
   once per detail per call, with retries. The receiver checks the signature, the timestamp and the idempotency key.
5. Banks read their inbox through the bank API (X-Bank-Key) and send back a decision: monitoring, frozen or dismissed.
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
from store import store

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


def mule_key(code: str, detail_type: str, value: str) -> str:
    return f"{code}-{hashlib.sha256(f'{detail_type}:{value.lower()}'.encode()).hexdigest()[:20]}"


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


# ----- the report -----


def _iso(value) -> str | None:
    return value.isoformat() if isinstance(value, datetime) else value


def _jlog(message: str, **fields) -> None:
    print(json.dumps({"severity": "INFO", "message": message, **fields}), flush=True)


def build_payload(*, report_id: str, route: registry.Route, detail: dict, context: dict, aggregate: dict) -> dict:
    details = context.get("details", {})
    hard = [f for f in context.get("redFlags", []) if f.get("severity") == "hard"]
    two_checks = len(detail.get("sources", [])) >= 2 or len(detail.get("turns", [])) >= 2
    linked = []
    for other in details.values():
        if other is detail or not other.get("valid"):
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
        "routedBy": route.routed_by,
        "routingReason": route.reason,
    }
    if route.ifsc:
        subject["ifsc"] = route.ifsc
    if route.upi_app:
        subject["upiApp"] = route.upi_app
    return {
        "schema": SCHEMA,
        "reportId": report_id,
        "sentAt": analysis.now_iso(),
        "reportedBy": "Stallwart decoy line (prototype)",
        "bank": {"code": route.bank_code, "name": route.bank_name},
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
        "aggregate": {
            "sightings": aggregate.get("sightings", 1),
            "callCount": len(aggregate.get("callIds", [])) or 1,
            "firstSeenAt": _iso(aggregate.get("firstSeenAt")),
            "bankStatus": aggregate.get("status", "reported"),
        },
        "recommendedAction": "review_for_freeze" if hard and two_checks else "monitor",
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
    """One per call. Reports each confirmed payee detail to its bank once, the moment the call is judged a scam."""

    def __init__(self, *, call_id: str, owner: str, emit: Callable[[dict], Awaitable[None]],
                 spawn: Callable[[Awaitable], None], context: Callable[[], dict]) -> None:
        self.call_id = call_id
        self.owner = owner
        self.emit = emit
        self.spawn = spawn
        self.context = context
        self.active = False
        self.sent: dict[str, dict] = {}

    def set_verdict(self, verdict: str | None) -> None:
        # Verdicts never go back from scam (red flags are cumulative), so this only ever switches on.
        self.active = self.active or verdict == "scam"

    async def sweep(self, details: dict[str, dict], turns: list[dict], final: bool = False) -> None:
        if not self.active:
            return
        for detail in list(details.values()):
            if detail["type"] not in REPORTABLE or not (detail.get("confirmed") and detail.get("valid")):
                continue
            route = route_detail(detail, details, turns, final=final)
            if route is None:
                continue
            key = mule_key(route.bank_code, detail["type"], detail["normalizedValue"])
            if key in self.sent:
                continue
            entry = {
                "reportId": secrets.token_hex(8),
                "muleKey": key,
                "bankCode": route.bank_code,
                "bankName": route.bank_name,
                "detailType": detail["type"],
                "value": detail["normalizedValue"],
                "routedBy": route.routed_by,
                "reason": route.reason,
                "status": "pending",
                "tSec": detail.get("firstSeenSec"),
            }
            self.sent[key] = entry
            await self.emit({"type": "bank_report", **entry})
            self.spawn(self._send(entry, route, detail))

    async def _send(self, entry: dict, route: registry.Route, detail: dict) -> None:
        aggregate = await store.record_sighting(
            f"mule_accounts/{entry['muleKey']}",
            {"muleKey": entry["muleKey"], "bankCode": route.bank_code, "bankName": route.bank_name,
             "type": detail["type"], "value": detail["normalizedValue"], "routedBy": route.routed_by},
            self.call_id,
        ) or {}
        context = self.context()
        payload = build_payload(report_id=entry["reportId"], route=route, detail=detail, context=context,
                                aggregate=aggregate)
        await store.put(f"bank_reports/{entry['reportId']}", {
            **{k: entry[k] for k in ("reportId", "muleKey", "bankCode", "bankName", "detailType", "value", "routedBy")},
            "callId": self.call_id, "ownerHash": self.owner, "status": "pending", "sentAt": payload["sentAt"],
            "scamType": context.get("scamType"), "recommendedAction": payload["recommendedAction"], "payload": payload,
        })
        body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()
        ok = await deliver(route.bank_code, body, entry["reportId"])
        if not ok:
            await store.update(f"bank_reports/{entry['reportId']}", {"status": "failed"})
        entry.update(status="delivered" if ok else "failed", sightings=payload["aggregate"]["sightings"],
                     bankStatus=payload["aggregate"]["bankStatus"], recommendedAction=payload["recommendedAction"])
        _jlog("bank_report", callId=self.call_id, bank=route.bank_code, type=detail["type"], status=entry["status"],
              sightings=entry["sightings"], routedBy=route.routed_by)
        await self.emit({"type": "bank_report", **entry})

    def summary(self) -> list[dict]:
        return [dict(e) for e in self.sent.values()]
