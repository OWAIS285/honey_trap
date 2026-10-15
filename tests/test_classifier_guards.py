import sys
from pathlib import Path

import pytest

import analysis
from analysis import VerifierResult, settle_verdict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "eval"))
from classifier_cases import ORDINARY, SCAMS, to_turns  # noqa: E402

CALLER = "This is the CBI. Do not tell anyone and send a security deposit to this UPI ID today."


def result(scam_type="digital_arrest", confidence=0.9, phrases=("Do not tell anyone",), stage="isolation", entity="CBI"):
    return VerifierResult(
        scam_type=scam_type, confidence=confidence, trigger_phrases=list(phrases), impersonated_entity=entity,
        stage=stage, details=[],
    )


def test_a_quoted_confident_scam_verdict_stands():
    out = settle_verdict(result(), CALLER)
    assert out.scam_type == "digital_arrest" and out.trigger_phrases == ["Do not tell anyone"]
    assert out.stage == "isolation" and out.impersonated_entity == "CBI"


def test_low_confidence_scam_becomes_undetermined():
    out = settle_verdict(result(confidence=0.45), CALLER)
    assert out.scam_type == "undetermined" and out.confidence <= 0.4
    assert out.trigger_phrases == [] and out.stage == "" and out.impersonated_entity == ""


def test_scam_without_quoted_caller_words_needs_very_high_confidence():
    assert settle_verdict(result(confidence=0.75, phrases=("made up words",)), CALLER).scam_type == "undetermined"
    assert settle_verdict(result(confidence=0.9, phrases=("made up words",)), CALLER).scam_type == "digital_arrest"


def test_trigger_phrases_must_come_from_the_caller():
    out = settle_verdict(result(phrases=("do   not tell ANYONE", "invented line")), CALLER)
    assert out.trigger_phrases == ["do   not tell ANYONE"]


def test_ordinary_verdict_carries_no_scam_details():
    out = settle_verdict(result("not_scam", 0.95, phrases=("Do not tell anyone",), entity="Amazon"), CALLER)
    assert out.scam_type == "not_scam" and out.confidence == 0.95
    assert out.trigger_phrases == [] and out.impersonated_entity == "" and out.stage == ""


def test_unknown_label_is_treated_as_other_scam_then_guarded():
    assert settle_verdict(result("made_up_label"), CALLER).scam_type == "other_scam"
    assert settle_verdict(result("made_up_label", 0.3), CALLER).scam_type == "undetermined"


def test_missing_stage_defaults_to_hook_for_a_scam():
    assert settle_verdict(result(stage="nonsense"), CALLER).stage == "hook"


def test_taxonomy_includes_both_harmless_verdicts():
    assert set(analysis.NON_SCAM) <= set(analysis.TAXONOMY)


def test_verifier_prompt_is_neutral_and_defines_ordinary_calls():
    prompt = analysis.VERIFIER_PROMPT
    assert "suspected scammer" not in prompt
    assert "do not assume a scam" in prompt
    assert "never a scam signal by itself" in prompt


@pytest.mark.parametrize("name", list(ORDINARY) + list(SCAMS))
def test_case_transcripts_are_well_formed(name):
    turns = to_turns({**ORDINARY, **SCAMS}[name])
    assert any(t["speaker"] == "caller" and t["text"] for t in turns)
