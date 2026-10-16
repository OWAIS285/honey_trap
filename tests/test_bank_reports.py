"""Mule-account reporting: bank identification, the confidence gate and watchlist, routing, signing, delivery, API."""

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
from bank_reports import BankReporter, apply_sighting, combine, mask, mule_key, route_detail, sign, verify_signature
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

    async def transact(self, path, step):
        new, result = step(dict(self.docs[path]) if path in self.docs else None)
        self.docs[path] = new
        return result

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


def detail(dtype, value, turn=1, confidence=0.9, valid=True, evidence="", sources=("live_tool", "verifier")):
    return {"id": f"{dtype}-{value}", "type": dtype, "normalizedValue": value, "rawValue": value, "valid": valid,
            "confirmed": confidence >= 0.65, "sources": list(sources), "turns": [turn], "evidence": evidence,
            "confidence": confidence, "firstSeenSec": 4.0, "flags": []}


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


# ----- confidence and the watchlist (pure) -----


def test_independent_calls_combine():
    assert combine({"a": 0.5}) == 0.5
    assert combine({"a": 0.5, "b": 0.5}) == 0.75
    assert combine({"a": 0.45, "b": 0.45}) == 0.7
    assert combine({}) == 0.0


def sight(doc, call, conf, route=None, final=False, dtype="upi_id", value="x@ybl"):
    from datetime import datetime, timezone
    now = datetime(2026, 10, 16, tzinfo=timezone.utc)
    return apply_sighting(doc, key="k", detail_type=dtype, value=value, call_id=call, confidence=conf, route=route,
                          final=final, now=now, expires=now)


YBL = {"bankCode": "YESB", "bankName": "Yes Bank", "routedBy": "upi_handle", "reason": "r", "ifsc": "", "upiApp": None}
SBI = {"bankCode": "SBIN", "bankName": "State Bank of India", "routedBy": "ifsc", "reason": "r", "ifsc": "SBIN0001234",
       "upiApp": None}
UNRES = {"bankCode": "UNRESOLVED", "bankName": "Unresolved", "routedBy": "unresolved", "reason": "r", "ifsc": "",
         "upiApp": None}


def test_one_call_at_report_level_sends():
    doc, out = sight(None, "c1", 0.7, YBL)
    assert out["send"] and doc["stage"] == "reported" and doc["reportedCalls"] == ["c1"] and doc["status"] == "reported"


def test_watch_level_is_kept_then_a_second_call_pushes_it_over():
    doc, out = sight(None, "c1", 0.5, YBL)
    assert not out["send"] and doc["stage"] == "watching" and doc["confidence"] == 0.5 and "status" not in doc
    doc, out = sight(doc, "c2", 0.5, YBL)
    assert out["send"] and out["previousCalls"] == ["c1"] and doc["confidence"] == 0.75 and doc["sightings"] == 2


def test_the_same_call_never_counts_twice():
    doc, _ = sight(None, "c1", 0.5, YBL)
    doc, out = sight(doc, "c1", 0.55, YBL)
    assert not out["send"] and doc["confidence"] == 0.55 and doc["calls"] == {"c1": 0.55}
    doc, _ = sight(doc, "c1", 0.4, YBL)
    assert doc["calls"] == {"c1": 0.55}


def test_one_report_per_call_and_follow_ups_from_new_calls():
    doc, first = sight(None, "c1", 0.8, YBL)
    doc, again = sight(doc, "c1", 0.9, YBL)
    doc, later = sight(doc, "c2", 0.5, YBL)
    assert first["send"] and not again["send"] and later["send"]
    assert doc["reportedCalls"] == ["c1", "c2"]


def test_a_route_from_an_earlier_call_is_reused():
    doc, _ = sight(None, "c1", 0.5, SBI, dtype="bank_account", value="123456789012")
    doc, out = sight(doc, "c2", 0.5, None, dtype="bank_account", value="123456789012")
    assert out["send"] and out["route"]["bankCode"] == "SBIN"


def test_a_better_route_replaces_the_unresolved_queue():
    doc, _ = sight(None, "c1", 0.5, UNRES, final=True, dtype="bank_account", value="123456789012")
    doc, out = sight(doc, "c2", 0.5, SBI, dtype="bank_account", value="123456789012")
    assert out["route"]["bankCode"] == "SBIN" and doc["bankCode"] == "SBIN"


def test_an_account_waits_for_its_bank_until_the_end_of_the_call():
    doc, out = sight(None, "c1", 0.8, None, dtype="bank_account", value="123456789012")
    assert not out["send"] and doc["confidence"] == 0.8
    doc, out = sight(doc, "c1", 0.8, UNRES, final=False, dtype="bank_account", value="123456789012")
    assert not out["send"]
    doc, out = sight(doc, "c1", 0.8, UNRES, final=True, dtype="bank_account", value="123456789012")
    assert out["send"] and out["route"]["bankCode"] == "UNRESOLVED"


def test_thresholds_come_from_config(monkeypatch):
    monkeypatch.setattr(config, "BANK_REPORT_CONFIDENCE", 0.9)
    _, out = sight(None, "c1", 0.8, YBL)
    assert not out["send"]


def test_identifier_key_ignores_bank_and_case():
    assert mule_key("upi_id", "Rahul@OKAXIS") == mule_key("upi_id", "rahul@okaxis") != mule_key("bank_account", "rahul@okaxis")


# ----- the reporter -----


def make_reporter(fs, verdict="scam", confidence=0.97, call_id="c1"):
    events, tasks = [], []

    async def emit(event):
        events.append(event)

    context = {"callId": call_id, "startedAt": "2026-10-16T08:00:00Z", "verdict": verdict, "scamType": "digital_arrest",
               "impersonatedEntity": "CBI", "redFlags": [{"signal": "arrest_or_legal_threat", "label": "x",
                                                          "severity": "hard", "quote": "arrest warrant"}],
               "details": {}, "turns": []}
    reporter = BankReporter(call_id=call_id, owner="owner-a", emit=emit,
                            spawn=lambda c: tasks.append(asyncio.ensure_future(c)), context=lambda: context)
    reporter.set_verdict(verdict, confidence)
    return reporter, events, tasks, context


async def drain(tasks):
    while tasks:
        batch = list(tasks)
        tasks.clear()
        await asyncio.gather(*batch)


def reports(fs):
    return [d for p, d in fs.docs.items() if p.startswith("bank_reports/")]


def test_nothing_is_scored_before_the_call_is_judged_a_scam(fake):
    async def go():
        reporter, events, tasks, _ = make_reporter(fake, verdict="undetermined", confidence=0.0)
        details = {"u": detail("upi_id", "rahul.sharma@okaxis")}
        await reporter.sweep(details, [])
        assert not events and not tasks
        reporter.set_verdict("scam", 0.97)
        await reporter.sweep(details, [])
        await drain(tasks)
        return events
    events = asyncio.run(go())
    assert [e["status"] for e in events] == ["pending", "delivered"]
    assert events[-1]["bankCode"] == "UTIB" and events[-1]["confidence"] == 0.87 and events[-1]["stage"] == "reported"


def test_below_watch_level_is_ignored_and_watch_level_is_only_stored(fake):
    async def go():
        reporter, events, tasks, _ = make_reporter(fake, confidence=0.85)
        details = {"low": detail("upi_id", "low@ybl", confidence=0.5),        # 0.5 x 0.85 = 0.43 -> ignored
                   "mid": detail("upi_id", "mid@ybl", confidence=0.75),       # 0.64 -> watchlist
                   "bad": detail("upi_id", "bad@ybl", valid=False),
                   "phone": detail("phone_number", "9876543210")}
        await reporter.sweep(details, [], final=True)
        await drain(tasks)
        return events
    events = asyncio.run(go())
    assert [(e["value"], e["stage"], e["confidence"]) for e in events] == [("mid@ybl", "watching", 0.64)]
    assert reports(fake) == []
    mule = fake.docs[f"mule_accounts/{mule_key('upi_id', 'mid@ybl')}"]
    assert mule["stage"] == "watching" and mule["calls"] == {"c1": 0.64}
    assert f"mule_accounts/{mule_key('upi_id', 'low@ybl')}" not in fake.docs
    assert fake.docs[f"watch_sightings/c1-{mule_key('upi_id', 'mid@ybl')}"]["ownerHash"] == "owner-a"


def test_a_watched_detail_is_reported_when_a_later_call_gives_it_again(fake):
    async def call(call_id):
        reporter, events, tasks, _ = make_reporter(fake, call_id=call_id)
        await reporter.sweep({"u": detail("upi_id", "mule@ybl", confidence=0.5)}, [])   # 0.5 x 0.97 = 0.48 each
        await drain(tasks)
        return events

    async def go():
        return await call("call-1"), await call("call-2")
    first, second = asyncio.run(go())
    assert [e["stage"] for e in first] == ["watching"] and first[0]["confidence"] == 0.48
    assert second[-1]["status"] == "delivered" and second[-1]["confidence"] == 0.73 and second[-1]["sightings"] == 2
    (report,) = reports(fake)
    assert report["callId"] == "call-2" and report["bankCode"] == "YESB"
    assert report["payload"]["confidence"]["promotedFromWatchlist"] is True
    assert report["payload"]["aggregate"]["callCount"] == 2


def test_a_watched_detail_grows_into_a_report_within_the_same_call(fake):
    async def go():
        reporter, events, tasks, _ = make_reporter(fake)
        await reporter.sweep({"u": detail("upi_id", "mule@ybl", confidence=0.5)}, [])
        await drain(tasks)
        await reporter.sweep({"u": detail("upi_id", "mule@ybl", confidence=0.75)}, [])
        await drain(tasks)
        return events
    events = asyncio.run(go())
    assert [(e["stage"], e.get("status")) for e in events] == [("watching", None), ("reported", "pending"),
                                                               ("reported", "delivered")]
    assert len(reports(fake)) == 1


def test_each_detail_is_reported_once_per_call_and_delivered_signed(fake):
    async def go():
        reporter, events, tasks, context = make_reporter(fake)
        details = {"u": detail("upi_id", "rahul.sharma@okaxis"), "a": detail("bank_account", "123456789012", turn=3),
                   "i": detail("ifsc", "SBIN0001234", turn=3), "p": detail("phone_number", "9876543210"),
                   "x": detail("upi_id", "other@ybl")}
        context["details"] = details
        for _ in range(3):
            await reporter.sweep(details, [])
        await drain(tasks)
        return reporter, events
    reporter, events = asyncio.run(go())
    banks = sorted(e["bankCode"] for e in events if e.get("status") == "delivered")
    assert banks == ["SBIN", "UTIB", "YESB"]
    by_bank = {d["bankCode"]: d for d in reports(fake)}
    sbi = by_bank["SBIN"]
    assert sbi["status"] == "delivered" and sbi["verified"] and sbi["ownerHash"] == "owner-a"
    payload = sbi["payload"]
    assert payload["schema"] == "stallwart.mule_report.v1"
    assert payload["subject"] == {**payload["subject"], "type": "bank_account", "value": "123456789012",
                                  "ifsc": "SBIN0001234", "routedBy": "ifsc"}
    assert payload["confidence"]["report"] == 0.87 and payload["confidence"]["threshold"] == 0.65
    assert payload["recommendedAction"] == "review_for_freeze"
    linked = {(link["type"], link.get("value")) for link in payload["linkedDetails"]}
    assert ("phone_number", "9876543210") in linked
    # Other banks' identifiers are linked by bank and last four characters, never in full.
    others = {link["valueMasked"]: link["bank"] for link in payload["linkedDetails"] if "valueMasked" in link}
    assert others == {mask("rahul.sharma@okaxis"): "Axis Bank", mask("other@ybl"): "Yes Bank"}
    assert all(link.get("value") not in ("rahul.sharma@okaxis", "other@ybl") for link in payload["linkedDetails"])
    assert len(reporter.summary()) == 3 and all("routeKnown" not in s for s in reporter.summary())


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


def test_call_handler_watches_then_reports_as_the_scam_evidence_grows(stubbed_call):
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
        h.verdict.red["asks_secret_credential"] = "tell me the OTP"          # one hard flag: 0.85 x 0.75 = 0.64
        await h._publish_verdict()
        await asyncio.gather(*list(h._bg))
        watching = [e for e in events if e["type"] == "bank_report"]
        h.verdict.red["secrecy_or_isolation"] = "tell nobody"                # two hard flags: 0.90 x 0.75 = 0.68
        await h._publish_verdict()
        summary = await h.finish("caller_ended")
        return before, watching, events, summary
    before, watching, events, summary = asyncio.run(go())
    assert before == []  # heard twice, but the call was not yet a scam
    assert [(e["stage"], e["confidence"]) for e in watching] == [("watching", 0.64)]
    (item,) = summary["bankReports"]
    assert item["bankCode"] == "UTIB" and item["status"] == "delivered" and item["confidence"] == 0.68
    ended = [e for e in events if e["type"] == "ended"][0]
    assert ended["bankReports"][0]["bankName"] == "Axis Bank"


def test_portal_and_bank_api(fake, monkeypatch):
    monkeypatch.setattr(config, "BANK_SIGNING_SECRET", "test-secret")

    async def seed():
        reporter, events, tasks, _ = make_reporter(fake)
        await reporter.sweep({"u": detail("upi_id", "mule@okaxis"), "w": detail("upi_id", "watch@okaxis", confidence=0.5)}, [])
        await drain(tasks)
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
    assert [m["value"] for m in mules] == ["mule@okaxis"]  # the watched one is never shown to the bank
    assert mules[0]["callCount"] == 1 and "calls" not in mules[0] and mules[0]["confidence"] == 0.87
    watched_key = mule_key("upi_id", "watch@okaxis")
    assert client.post(f"/bank-api/v1/UTIB/mule-accounts/{watched_key}/status", json={"decision": "frozen"},
                       headers={"X-Bank-Key": key}).status_code == 404
    watch = client.get("/api/watchlist", headers={"X-Client-Id": owner_id}).json()
    assert [(i["value"], i["stage"]) for i in watch["items"]] == [("watch@okaxis", "watching"), ("mule@okaxis", "reported")]
    assert watch["reportAt"] == 0.65 and watch["watchAt"] == 0.45
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
    assert hasattr(Store, "transact") and hasattr(Store, "list_where")
