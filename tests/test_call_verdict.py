"""CallHandler with Gemini and storage stubbed: the verdict decides whether a strain card is ever built."""

import asyncio

import pytest

import analysis
import call_handler
from analysis import Evidence, VerifierExtraction, finalize
from call_handler import CallHandler

LOAN_LEGIT = [
    "Good morning sir, this is Priya from HDFC Bank. You have a pre-approved personal loan offer.",
    "Of course sir, please call the number on the back of your debit card or visit your branch to check.",
    "No problem at all sir, take your time. Thank you.",
]
LOAN_SCAM = LOAN_LEGIT[:2] + ["Sir to release the loan today first pay a processing fee of 2999 to my UPI."]


def fake_verify(script):
    """Return evidence a well-behaved verifier would report for the turns seen so far."""

    async def verify(client, turns):
        said = " ".join(t["text"] for t in turns if t["speaker"] == "caller")
        red, legit = [], []
        if "call the number on the back of your debit card" in said:
            legit.append(Evidence(signal="offers_official_verification",
                                  quote="call the number on the back of your debit card"))
        if "take your time" in said:
            legit.append(Evidence(signal="accepts_refusal", quote="take your time"))
        if "processing fee" in said:
            red.append(Evidence(signal="pay_to_receive", quote="first pay a processing fee of 2999 to my UPI"))
        raw = VerifierExtraction(scam_type="loan_app", impersonated_entity="HDFC Bank", stage="hook",
                                 red_flags=red, legit_signals=legit, details=[])
        script.append(len(turns))
        return finalize(raw, turns)

    return verify


@pytest.fixture
def stubbed(monkeypatch):
    calls = {"verify": [], "strain": 0}

    async def noop(*args, **kwargs):
        return None

    async def strain(client, turns, scam_type):
        calls["strain"] += 1
        return {"scamType": "loan_app", "impersonatedEntity": "HDFC Bank", "steps": ["a"], "redFlags": ["x", "y", "z"],
                "paymentMethod": "UPI", "scriptExcerpts": [], "language": "english"}

    for name in ("put", "update", "put_recording"):
        monkeypatch.setattr(call_handler.store, name, noop)
    monkeypatch.setattr(call_handler, "text_client", lambda: None)
    monkeypatch.setattr(analysis, "verify", fake_verify(calls["verify"]))
    monkeypatch.setattr(analysis, "build_strain", strain)
    return calls


async def play(lines, end_reason=None):
    handler = CallHandler(client_id="t" * 20, ip="127.0.0.1", mode="text")
    events = []

    async def emit(event):
        events.append(event)

    handler.emit = emit
    for line in lines:
        await handler.on_typed_caller(line)
        await handler.on_persona_text("Hmm, I see.")
        await handler.on_turn_complete()
        if handler._verify_task:
            await handler._verify_task
    if end_reason:
        await handler.on_tool_call("end_call", {"reason": end_reason})
    summary = await handler.finish("caller_ended")
    return summary, events


def test_genuine_loan_call_is_not_a_scam_and_builds_no_strain(stubbed):
    summary, events = asyncio.run(play(LOAN_LEGIT))
    assert summary["verdict"] == "legitimate" and summary["scamType"] == "not_scam"
    assert summary["strainId"] is None and stubbed["strain"] == 0
    assert {s["signal"] for s in summary["legitSignals"]} == {"offers_official_verification", "accepts_refusal"}
    ended = [e for e in events if e["type"] == "ended"][0]
    assert ended["verdict"] == "legitimate" and ended["strain"] is None


def test_same_call_turns_into_a_scam_when_a_fee_is_demanded(stubbed):
    summary, events = asyncio.run(play(LOAN_SCAM))
    assert summary["verdict"] == "scam" and summary["scamType"] == "loan_app"
    assert summary["strainId"] and stubbed["strain"] == 1
    verdicts = [e["verdict"] for e in events if e["type"] == "classification"]
    assert "legitimate" in verdicts and verdicts[-1] == "scam"


def test_persona_not_scam_cannot_clear_a_red_flag(stubbed):
    summary, _ = asyncio.run(play(LOAN_SCAM, end_reason="not_scam"))
    assert summary["verdict"] == "scam"


def test_classification_events_keep_the_old_fields_for_the_dashboard(stubbed):
    _, events = asyncio.run(play(LOAN_LEGIT[:1]))
    event = [e for e in events if e["type"] == "classification"][-1]
    for key in ("scamType", "confidence", "triggerPhrases", "impersonatedEntity", "stage", "verdict", "redFlags",
                "legitSignals"):
        assert key in event
    assert event["verdict"] == "undetermined"
