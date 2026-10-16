"""Mule-account reporting: bank identification, the scam-only gate, routing, signing, delivery and the bank API."""

import asyncio
import json
import time

import pytest
from fastapi.testclient import TestClient

import bank_registry as registry
import bank_reports
import call_handler
import config
import main
from bank_reports import BankReporter, mask, route_detail, sign, verify_signature
from call_handler import CallHandler
from store import Store

# ----- an in-memory Firestore stand-in -----


class FakeStore:
    def __init__(self) -> None:
        self.docs: dict[str, dict] = {}

    async def put(self, path, data, merge=True):
        self.docs[path] = {**self.docs.get(path, {}), **data} if merge else dict(data)

    async def update(self, path, data):
        self.docs[path] = {**self.docs.get(path, {}), **data}

    async def get(self, path):
        doc = self.docs.get(path)
        return dict(doc) if doc else None

    async def record_sighting(self, path, data, call_id):
        doc = self.docs.setdefault(path, {"sightings": 0, "callIds": [], "status": "reported"})
        doc.update(data)
        doc["sightings"] += 1
        if call_id not in doc["callIds"]:
            doc["callIds"].append(call_id)
        return dict(doc)

    def _collection(self, name):
        prefix = name + "/"
        return [d for p, d in self.docs.items() if p.startswith(prefix) and p.count("/") == 1]

    async def list_owned(self, collection, owner, limit=60):
        return [dict(d) for d in self._collection(collection) if d.get("ownerHash") == owner][:limit]

    async def list_where(self, collection, field, value, limit=200):
        return [dict(d) for d in self._collection(collection) if d.get(field) == value][:limit]

    async def list_sub(self, path, order=None):
        return []

    async def put_recording(self, *a):
        return None


@pytest.fixture
def fake(monkeypatch):
    fs = FakeStore()
    for module in (bank_reports, call_handler, main):
        monkeypatch.setattr(module, "store", fs)
    monkeypatch.setattr(config, "BANK_DELIVERY", "local")
    monkeypatch.setattr(bank_reports.asyncio, "sleep", _no_sleep)
    return fs


async def _no_sleep(*_):
    return None


def detail(dtype, value, turn=1, confirmed=True, valid=True, evidence="", sources=("live_tool", "verifier")):
    return {"id": f"{dtype}-{value}", "type": dtype, "normalizedValue": value, "rawValue": value, "valid": valid,
            "confirmed": confirmed, "sources": list(sources), "turns": [turn], "evidence": evidence,
            "confidence": 0.9, "firstSeenSec": 4.0, "flags": []}


# ----- bank identification -----


@pytest.mark.parametrize("ifsc,code", [("SBIN0001234", "SBIN"), ("hdfc0000123", "HDFC"), ("UTIB0004321", "UTIB"),
                                       ("PUNB0123400", "PUNB")])
def test_ifsc_prefix_names_the_bank(ifsc, code):
    route = registry.from_ifsc(ifsc)
    assert route.bank_code == code and route.routed_by == "ifsc" and route.ifsc == ifsc.upper()


def test_unknown_ifsc_prefix_is_not_routed():
    assert registry.from_ifsc("ZZZZ0001234") is None


@pytest.mark.parametrize("upi,code,app", [("rahul.sharma@okaxis", "UTIB", "Google Pay"), ("98765@ybl", "YESB", "PhonePe"),
                                          ("x@ibl", "ICIC", "PhonePe"), ("shop@ptsbi", "SBIN", "Paytm"),
                                          ("me@hdfcbank", "HDFC", None), ("a@oksbi", "SBIN", "Google Pay")])
def test_upi_handle_names_the_psp_bank(upi, code, app):
    route = registry.from_upi(upi)
    assert (route.bank_code, route.upi_app, route.routed_by) == (code, app, "upi_handle")


def test_unknown_upi_handle_goes_to_the_unresolved_queue():
    route = registry.from_upi("fraud@madeuphandle")
    assert route.bank_code == registry.UNRESOLVED and "madeuphandle" in route.reason


def test_bank_names_longest_match_first():
    assert registry.banks_named_in("send it to my State Bank of India account") == ["SBIN"]
    assert registry.banks_named_in("Indian Overseas Bank, not Indian Bank") == ["IOBA", "IDIB"]
    assert registry.banks_named_in("खाता पंजाब नेशनल बैंक में है") == ["PUNB"]
    assert registry.banks_named_in("Axis or HDFC, either is fine") == ["UTIB", "HDFC"]
    assert registry.banks_named_in("send to my axis") == ["UTIB"]
    assert registry.banks_named_in("taxis are expensive") == []


def test_every_upi_handle_points_at_a_known_bank():
    assert all(code in registry.BANKS for code, _ in registry.UPI_HANDLES.values())


# ----- routing a bare account number -----


def test_account_number_takes_the_nearest_ifsc():
    acct = detail("bank_account", "123456789012", turn=5)
    details = {"a": acct, "i1": detail("ifsc", "HDFC0000001", turn=1), "i2": detail("ifsc", "SBIN0001234", turn=5)}
    assert route_detail(acct, details, []).bank_code == "SBIN"


def test_account_without_ifsc_waits_then_uses_a_bank_named_in_the_same_sentence():
    acct = detail("bank_account", "123456789012", turn=3)
    turns = [{"n": 1, "speaker": "caller", "text": "I am from SBI head office."},
             {"n": 3, "speaker": "caller", "text": "Send it to my Kotak account 123456789012."}]
    assert route_detail(acct, {"a": acct}, turns) is None
    route = route_detail(acct, {"a": acct}, turns, final=True)
    assert route.bank_code == "KKBK" and route.routed_by == "bank_named"


def test_account_with_no_bank_at_all_is_unresolved_at_the_end():
    acct = detail("bank_account", "123456789012", turn=2)
    route = route_detail(acct, {"a": acct}, [{"n": 2, "speaker": "caller", "text": "Account 123456789012."}], final=True)
    assert route.bank_code == registry.UNRESOLVED


# ----- signing -----


def test_signature_round_trip_and_tamper_checks():
    body = b'{"reportId":"r1"}'
    ts = str(int(time.time()))
    sig = sign("SBIN", ts, body)
    assert verify_signature("SBIN", ts, sig, body)
    assert not verify_signature("HDFC", ts, sig, body)  # every bank has its own key
    assert not verify_signature("SBIN", ts, sig, body + b" ")
    assert not verify_signature("SBIN", str(int(ts) - 3600), sign("SBIN", str(int(ts) - 3600), body), body)
    assert not verify_signature("SBIN", "not-a-time", sig, body)


def test_mask_keeps_last_four():
    assert mask("123456789012") == "••••••••9012"


# ----- the reporter -----


def make_reporter(fs, verdict="scam"):
    events, tasks = [], []

    async def emit(event):
        events.append(event)

    context = {"callId": "c1", "startedAt": "2026-10-16T08:00:00Z", "verdict": verdict, "scamType": "digital_arrest",
               "impersonatedEntity": "CBI", "redFlags": [{"signal": "arrest_or_legal_threat", "label": "x",
                                                          "severity": "hard", "quote": "arrest warrant"}],
               "details": {}, "turns": []}
    reporter = BankReporter(call_id="c1", owner="owner-a", emit=emit, spawn=lambda c: tasks.append(asyncio.ensure_future(c)),
                            context=lambda: context)
    reporter.set_verdict(verdict)
    return reporter, events, tasks, context


def test_nothing_is_reported_before_the_call_is_judged_a_scam(fake):
    async def go():
        reporter, events, tasks, _ = make_reporter(fake, verdict="undetermined")
        details = {"u": detail("upi_id", "rahul.sharma@okaxis")}
        await reporter.sweep(details, [])
        assert not events and not reporter.sent
        reporter.set_verdict("scam")
        await reporter.sweep(details, [])
        await asyncio.gather(*tasks)
        return events
    events = asyncio.run(go())
    assert [e["status"] for e in events] == ["pending", "delivered"]
    assert events[-1]["bankCode"] == "UTIB" and events[-1]["sightings"] == 1


def test_unconfirmed_or_invalid_details_are_never_reported(fake):
    async def go():
        reporter, events, tasks, _ = make_reporter(fake)
        details = {"a": detail("upi_id", "a@okaxis", confirmed=False), "b": detail("upi_id", "b@ybl", valid=False),
                   "c": detail("phone_number", "9876543210")}
        await reporter.sweep(details, [], final=True)
        return events
    assert asyncio.run(go()) == []


def test_each_detail_is_reported_once_per_call_and_delivered_signed(fake):
    async def go():
        reporter, events, tasks, context = make_reporter(fake)
        details = {"u": detail("upi_id", "rahul.sharma@okaxis"), "a": detail("bank_account", "123456789012", turn=3),
                   "i": detail("ifsc", "SBIN0001234", turn=3), "p": detail("phone_number", "9876543210"),
                   "x": detail("upi_id", "other@ybl")}
        context["details"] = details
        for _ in range(3):
            await reporter.sweep(details, [])
        await asyncio.gather(*tasks)
        return reporter, events
    reporter, events = asyncio.run(go())
    banks = sorted(e["bankCode"] for e in events if e["status"] == "delivered")
    assert banks == ["SBIN", "UTIB", "YESB"]
    reports = {d["bankCode"]: d for p, d in fake.docs.items() if p.startswith("bank_reports/")}
    sbi = reports["SBIN"]
    assert sbi["status"] == "delivered" and sbi["verified"] and sbi["ownerHash"] == "owner-a"
    payload = sbi["payload"]
    assert payload["schema"] == "stallwart.mule_report.v1"
    assert payload["subject"] == {**payload["subject"], "type": "bank_account", "value": "123456789012",
                                  "ifsc": "SBIN0001234", "routedBy": "ifsc"}
    assert payload["recommendedAction"] == "review_for_freeze"
    linked = {(l["type"], l.get("value") or l.get("valueMasked")) for l in payload["linkedDetails"]}
    assert ("phone_number", "9876543210") in linked
    # Other banks' identifiers are linked by bank and last four characters, never in full.
    others = {l["valueMasked"]: l["bank"] for l in payload["linkedDetails"] if "valueMasked" in l}
    assert others == {mask("rahul.sharma@okaxis"): "Axis Bank", mask("other@ybl"): "Yes Bank"}
    assert all(l.get("value") not in ("rahul.sharma@okaxis", "other@ybl") for l in payload["linkedDetails"])


def test_the_same_account_from_two_calls_counts_two_sightings(fake):
    async def one_call(call_id):
        events, tasks = [], []

        async def emit(e):
            events.append(e)
        ctx = {"callId": call_id, "verdict": "scam", "redFlags": [], "details": {}, "turns": []}
        r = BankReporter(call_id=call_id, owner="o", emit=emit, spawn=lambda c: tasks.append(asyncio.ensure_future(c)),
                         context=lambda: ctx)
        r.set_verdict("scam")
        await r.sweep({"u": detail("upi_id", "mule@ybl")}, [])
        await asyncio.gather(*tasks)
        return events[-1]

    async def go():
        await one_call("call-1")
        return await one_call("call-2")
    last = asyncio.run(go())
    assert last["sightings"] == 2 and last["recommendedAction"] == "monitor"
    mule = fake.docs[f"mule_accounts/{last['muleKey']}"]
    assert mule["callIds"] == ["call-1", "call-2"]


def test_receiver_rejects_bad_signatures_and_ignores_duplicates(fake):
    async def go():
        body = json.dumps({"reportId": "r9", "bank": {"code": "SBIN"}}).encode()
        ts = str(int(time.time()))
        good = {"X-Stallwart-Timestamp": ts, "X-Stallwart-Signature": sign("SBIN", ts, body), "Idempotency-Key": "r9"}
        bad = {**good, "X-Stallwart-Signature": "sha256=00"}
        wrong_bank = await bank_reports.receive("HDFC", good, body)
        rejected = await bank_reports.receive("SBIN", bad, body)
        first = await bank_reports.receive("SBIN", good, body)
        again = await bank_reports.receive("SBIN", good, body)
        unknown = await bank_reports.receive("NOPE", good, body)
        return wrong_bank, rejected, first, again, unknown
    wrong_bank, rejected, first, again, unknown = asyncio.run(go())
    assert wrong_bank[0] == 401 and rejected[0] == 401 and unknown[0] == 404
    assert first == (200, {"status": "accepted", "reportId": "r9"})
    assert again[1]["status"] == "duplicate"


# ----- end to end through the call handler and the HTTP API -----


@pytest.fixture
def stubbed_call(fake, monkeypatch):
    async def noop(*a, **k):
        return None
    monkeypatch.setattr(call_handler, "text_client", lambda: None)
    monkeypatch.setattr(call_handler.analysis, "verify", noop)
    monkeypatch.setattr(call_handler.analysis, "build_strain", noop)
    return fake


def test_call_handler_reports_once_the_scam_verdict_lands(stubbed_call):
    async def go():
        h = CallHandler(client_id="t" * 20, ip="127.0.0.1", mode="text")
        events = []

        async def emit(e):
            events.append(e)
        h.emit = emit
        await h.on_typed_caller("Send the deposit to fraud.desk@okaxis")
        await h._upsert("upi_id", "fraud.desk@okaxis", "live_tool", quote="fraud.desk@okaxis")
        await h._upsert("upi_id", "fraud.desk@okaxis", "verifier", quote="fraud.desk@okaxis")
        before = [e for e in events if e["type"] == "bank_report"]
        h.verdict.red["asks_secret_credential"] = "tell me the OTP"
        await h._publish_verdict()
        summary = await h.finish("caller_ended")
        return before, events, summary
    before, events, summary = asyncio.run(go())
    assert before == []  # confirmed, but the call was not yet a scam
    assert [r["bankCode"] for r in summary["bankReports"]] == ["UTIB"]
    assert summary["bankReports"][0]["status"] == "delivered"
    ended = [e for e in events if e["type"] == "ended"][0]
    assert ended["bankReports"][0]["bankName"] == "Axis Bank"


def test_portal_and_bank_api(fake, monkeypatch):
    monkeypatch.setattr(config, "BANK_SIGNING_SECRET", "test-secret")

    async def seed():
        reporter, events, tasks, _ = make_reporter(fake)
        await reporter.sweep({"u": detail("upi_id", "mule@okaxis")}, [])
        await asyncio.gather(*tasks)
    asyncio.run(seed())
    client = TestClient(main.app)
    owner_id = "x" * 20
    # The demo portal only shows a browser its own calls' reports.
    for doc in fake.docs.values():
        if "ownerHash" in doc:
            doc["ownerHash"] = main.owner_hash(owner_id)
    banks = client.get("/api/banks", headers={"X-Client-Id": owner_id}).json()
    assert {b["code"]: b["reports"] for b in banks["banks"]}["UTIB"] == 1 and banks["apiEnabled"]
    inbox = client.get("/api/banks/UTIB/reports", headers={"X-Client-Id": owner_id}).json()["reports"]
    assert inbox[0]["value"] == "mule@okaxis" and inbox[0]["sightings"] == 1
    assert client.get("/api/banks/UTIB/reports", headers={"X-Client-Id": "y" * 20}).json()["reports"] == []
    rid = inbox[0]["reportId"]
    ok = client.post(f"/api/banks/UTIB/reports/{rid}/decision", json={"decision": "frozen"}, headers={"X-Client-Id": owner_id})
    assert ok.status_code == 200 and fake.docs[f"bank_reports/{rid}"]["simulatedDecision"] == "frozen"
    assert client.post(f"/api/banks/UTIB/reports/{rid}/decision", json={"decision": "frozen"},
                       headers={"X-Client-Id": "y" * 20}).status_code == 404

    key = bank_reports.bank_api_key("UTIB")
    assert client.get("/bank-api/v1/UTIB/reports").status_code == 401
    assert client.get("/bank-api/v1/UTIB/reports", headers={"X-Bank-Key": bank_reports.bank_api_key("HDFC")}).status_code == 401
    reports = client.get("/bank-api/v1/UTIB/reports", headers={"X-Bank-Key": key}).json()["reports"]
    assert reports[0]["subject"]["value"] == "mule@okaxis"
    mules = client.get("/bank-api/v1/UTIB/mule-accounts", headers={"X-Bank-Key": key}).json()["muleAccounts"]
    assert mules[0]["callCount"] == 1 and "callIds" not in mules[0]
    status = client.post(f"/bank-api/v1/UTIB/mule-accounts/{mules[0]['muleKey']}/status", json={"decision": "frozen"},
                         headers={"X-Bank-Key": key})
    assert status.status_code == 200 and fake.docs[f"mule_accounts/{mules[0]['muleKey']}"]["status"] == "frozen"
    assert client.get("/bank-api/v1/NOPE/reports", headers={"X-Bank-Key": key}).status_code == 404


def test_bank_api_is_off_without_a_secret(fake, monkeypatch):
    monkeypatch.setattr(config, "BANK_SIGNING_SECRET", "")
    assert bank_reports.bank_api_key("UTIB") is None
    assert TestClient(main.app).get("/bank-api/v1/UTIB/reports", headers={"X-Bank-Key": "x"}).status_code == 503


def test_webhook_endpoint_accepts_a_signed_report(fake):
    body = json.dumps({"reportId": "w1", "bank": {"code": "HDFC"}}).encode()
    ts = str(int(time.time()))
    headers = {"X-Stallwart-Timestamp": ts, "X-Stallwart-Signature": sign("HDFC", ts, body), "Idempotency-Key": "w1",
               "Content-Type": "application/json"}
    client = TestClient(main.app)
    assert client.post("/proxy-banks/HDFC/webhook", content=body, headers=headers).json()["status"] == "accepted"
    assert client.post("/proxy-banks/HDFC/webhook", content=body,
                       headers={**headers, "X-Stallwart-Signature": "sha256=bad"}).status_code == 401


def test_real_store_has_the_new_methods():
    assert hasattr(Store, "record_sighting") and hasattr(Store, "list_where")
