"""Guards on the verifier's output: a scam verdict needs quoted caller behaviour, never just a topic or a label."""

import sys
from pathlib import Path

import pytest

import analysis
from analysis import Evidence, VerifierExtraction, finalize

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "eval"))
from classifier_cases import ORDINARY, SCAMS, to_turns  # noqa: E402

CALLER = "This is the CBI. Do not tell anyone and send a security deposit to this UPI ID today."
TURNS = [{"speaker": "caller", "text": CALLER}]


def raw(scam_type="digital_arrest", red=(), legit=(), stage="isolation", entity="CBI"):
    return VerifierExtraction(
        scam_type=scam_type, impersonated_entity=entity, stage=stage,
        red_flags=[Evidence(signal=s, quote=q) for s, q in red],
        legit_signals=[Evidence(signal=s, quote=q) for s, q in legit], details=[],
    )


def test_a_quoted_hard_flag_makes_a_scam():
    out = finalize(raw(red=[("secrecy_or_isolation", "Do not tell anyone")]), TURNS)
    assert out.verdict == "scam" and out.trigger_phrases == ["Do not tell anyone"]
    assert out.stage == "isolation" and out.impersonated_entity == "CBI"


def test_a_scam_label_without_quoted_behaviour_is_not_a_scam():
    assert finalize(raw("digital_arrest"), TURNS).verdict == "undetermined"


def test_flags_quoting_words_the_caller_never_said_are_dropped():
    out = finalize(raw(red=[("asks_secret_credential", "tell me your OTP now")]), TURNS)
    assert out.red_flags == [] and out.verdict == "undetermined"


def test_unknown_label_and_stage_are_normalised():
    out = finalize(raw("made_up_label", stage="nonsense"), TURNS)
    assert out.scam_type == "other_scam" and out.stage == "hook"


def test_taxonomy_includes_both_harmless_verdicts():
    assert set(analysis.NON_SCAM) <= set(analysis.TAXONOMY)


def test_verifier_prompt_is_neutral_and_defines_ordinary_calls():
    prompt = analysis.VERIFIER_PROMPT
    assert "suspected scammer" not in prompt
    assert "do not assume a scam" in prompt
    assert "never a red flag by\nitself" in prompt or "never a red flag by itself" in prompt


@pytest.mark.parametrize("name", list(ORDINARY) + list(SCAMS))
def test_case_transcripts_are_well_formed(name):
    turns = to_turns({**ORDINARY, **SCAMS}[name])
    assert any(t["speaker"] == "caller" and t["text"] for t in turns)
