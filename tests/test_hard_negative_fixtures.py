"""Integrity of the hand-written scam-vs-genuine eval set (eval/fixtures/hard_negatives.json)."""

import json
import pathlib
import re
from collections import Counter

DATA = json.loads((pathlib.Path(__file__).resolve().parent.parent / "eval" / "fixtures" / "hard_negatives.json")
                  .read_text(encoding="utf-8"))
CALLS = DATA["calls"]


def test_ids_are_unique_and_fields_are_valid():
    assert len({c["id"] for c in CALLS}) == len(CALLS)
    for c in CALLS:
        assert c["label"] in ("scam", "legitimate")
        assert c["kind"] in ("pair", "late_turn", "benign")
        assert c["lang"] in ("en", "hi", "hinglish")
        assert c["turns"] and c["turns"][0][0] == "caller"
        assert all(s in ("caller", "persona") for s, _ in c["turns"])


def test_every_pair_has_one_genuine_and_one_scam_on_the_same_topic():
    pairs: dict[str, list[dict]] = {}
    for c in CALLS:
        if c["kind"] == "pair":
            pairs.setdefault(c["pair"], []).append(c)
    assert len(pairs) >= 15
    for group in pairs.values():
        assert sorted(c["label"] for c in group) == ["legitimate", "scam"]
        assert len({c["lang"] for c in group}) == 1


def test_set_is_balanced_and_covers_three_languages():
    labels = Counter(c["label"] for c in CALLS)
    assert labels["scam"] == labels["legitimate"]
    assert set(Counter(c["lang"] for c in CALLS)) == {"en", "hi", "hinglish"}


def test_late_turn_scams_point_at_a_real_caller_turn():
    for c in CALLS:
        if c["kind"] == "late_turn":
            caller_turns = sum(1 for s, _ in c["turns"] if s == "caller")
            assert c["label"] == "scam" and 2 <= c["scam_from_turn"] <= caller_turns


def test_no_real_looking_mobile_numbers():
    for c in CALLS:
        for _, text in c["turns"]:
            assert not re.search(r"(?<!\d)[6-9]\d{9}(?!\d)", text), c["id"]
