"""Ramesh's private record: never spoken, only used to test a caller who claims to be his bank."""

import asyncio
import random
import re

import pytest

import call_handler
from analysis import decide_verdict
from call_handler import CallHandler
from persona import CallProfile, PrivateRecord, build_persona


def record(seed: int = 11) -> PrivateRecord:
    return PrivateRecord(random.Random(seed))


def test_only_the_last_four_digits_exist():
    for seed in range(200):
        r = record(seed)
        assert set(r.last4) == {"account", "aadhaar", "card"}
        assert all(re.fullmatch(r"\d{4}", v) for v in r.last4.values())
        assert len(set(r.last4.values())) == 3
        assert not any(len(set(v)) == 1 for v in r.last4.values())


def test_prompt_never_contains_a_long_number():
    for seed in range(50):
        prompt = build_persona(CallProfile(random.Random(seed)))
        assert not re.search(r"\d{5,}", prompt)


def test_prompt_explains_the_record_test_and_upi_questions():
    profile = CallProfile(random.Random(3))
    prompt = build_persona(profile)
    for four in profile.record.last4.values():
        assert four in prompt
    assert profile.record.upi_app in prompt and profile.record.bank in prompt
    assert "NEVER say any number or digit of your own" in prompt
    assert "they should tell YOU the last four digits" in prompt
    assert "never tell them the right digits" in prompt
    assert "why would it need your PIN if you are only receiving" in prompt
    assert "You never say your UPI ID" in prompt


def test_matches_short_numbers_only():
    r = record()
    acct, aadhaar = r.last4["account"], r.last4["aadhaar"]
    assert r.matches(f"Sir your account ends in {acct}") == ["account"]
    assert r.matches(" ".join(acct)) == ["account"]  # spoken digit by digit
    assert sorted(r.matches(f"account ending {acct}, Aadhaar ending {aadhaar}")) == ["aadhaar", "account"]
    assert r.matches(f"Send it to 98765{acct}21") == []  # a long number that merely contains the digits
    assert r.matches("Your account ends in 12") == []
    assert r.matches("Hello sir, how are you?") == []


def test_spoken_words_are_understood():
    r = PrivateRecord(random.Random(0))
    words = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]
    spoken = " ".join(words[int(c)] for c in r.last4["card"])
    assert r.matches(f"your debit card ends with {spoken}") == ["card"]


def test_knowing_the_record_counts_as_a_legit_signal_but_never_clears_a_hard_flag():
    assert decide_verdict([], ["knows_customer_record"], 2)[0] == "legitimate"
    assert decide_verdict(["asks_secret_credential"], ["knows_customer_record", "accepts_refusal"], 3)[0] == "scam"


# ----- the call handler -----


@pytest.fixture
def handler(monkeypatch):
    async def noop(*args, **kwargs):
        return None

    for name in ("put", "update"):
        monkeypatch.setattr(call_handler.store, name, noop)
    monkeypatch.setattr(call_handler, "text_client", lambda: None)
    monkeypatch.setattr(call_handler.analysis, "verify", noop)
    r = record()
    h = CallHandler(client_id="t" * 20, ip="127.0.0.1", mode="text", record=r)
    events = []

    async def emit(event):
        events.append(event)

    h.emit = emit
    return h, r, events


def test_caller_who_knows_the_account_ending_is_recorded(handler):
    h, r, events = handler

    async def go():
        await h.on_typed_caller("Good morning sir, this is your bank about your fixed deposit.")
        await h.on_typed_caller(f"For your security, your account ends in {r.last4['account']}.")
        await h.on_typed_caller(f"Yes, account ending {r.last4['account']}.")

    asyncio.run(go())
    assert list(h.record_checks) == ["account"]
    last = [e for e in events if e["type"] == "classification"][-1]
    assert last["verdict"] == "legitimate"
    assert [s["signal"] for s in last["legitSignals"]] == ["knows_customer_record"]


def test_wrong_digits_prove_nothing(handler):
    h, r, events = handler
    wrong = next(f"{n:04d}" for n in range(10000) if f"{n:04d}" not in r.last4.values())

    async def go():
        await h.on_typed_caller(f"I am from your bank, your account ends in {wrong}, right?")

    asyncio.run(go())
    assert h.record_checks == {}
    assert not [e for e in events if e["type"] == "classification"]


def test_without_a_record_nothing_is_checked(monkeypatch):
    async def noop(*args, **kwargs):
        return None

    for name in ("put", "update"):
        monkeypatch.setattr(call_handler.store, name, noop)
    monkeypatch.setattr(call_handler, "text_client", lambda: None)
    monkeypatch.setattr(call_handler.analysis, "verify", noop)
    h = CallHandler(client_id="t" * 20, ip="127.0.0.1", mode="text")
    asyncio.run(h.on_typed_caller("Your account ends in 1234."))
    assert h.record_checks == {}
