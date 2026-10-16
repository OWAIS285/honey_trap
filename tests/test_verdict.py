import pytest

import analysis
from analysis import (
    HARD_FLAGS,
    LEGIT_SIGNALS,
    SOFT_FLAGS,
    Evidence,
    VerdictState,
    VerifierExtraction,
    decide_verdict,
    finalize,
    grounded,
    verdict_label,
)


def turns(*caller_lines: str) -> list[dict]:
    out = []
    for i, line in enumerate(caller_lines):
        out.append({"speaker": "caller", "text": line})
        out.append({"speaker": "persona", "text": f"reply {i}"})
    return out


def extraction(red=(), legit=(), scam_type="loan_app", details=()):
    return VerifierExtraction(
        scam_type=scam_type,
        impersonated_entity="HDFC Bank",
        stage="hook",
        red_flags=[Evidence(signal=s, quote=q) for s, q in red],
        legit_signals=[Evidence(signal=s, quote=q) for s, q in legit],
        details=list(details),
    )


# ----- the rule -----


@pytest.mark.parametrize("flag", sorted(HARD_FLAGS))
def test_any_hard_flag_alone_is_a_scam(flag):
    verdict, confidence = decide_verdict([flag], ["offers_official_verification", "accepts_refusal"], 1)
    assert verdict == "scam" and confidence >= 0.85


def test_one_soft_flag_alone_is_not_a_scam():
    # A real bank asking to confirm the full account number is a warning sign, not proof.
    assert decide_verdict(["asks_full_identifier"], [], 4)[0] == "undetermined"


def test_two_different_soft_flags_make_a_scam():
    assert decide_verdict(["asks_full_identifier", "urgency_deadline"], [], 2)[0] == "scam"


def test_topic_without_behaviour_stays_undetermined():
    assert decide_verdict([], [], 5) == ("undetermined", 0.0)


def test_genuine_bank_call_is_legitimate():
    verdict, confidence = decide_verdict([], ["offers_official_verification", "partial_identifier_only"], 3)
    assert verdict == "legitimate" and 0.5 < confidence <= 0.9


def test_one_soft_flag_needs_two_legit_signals_to_be_cleared():
    assert decide_verdict(["asks_full_identifier"], ["accepts_refusal"], 3)[0] == "undetermined"
    assert decide_verdict(["asks_full_identifier"], ["accepts_refusal", "offers_official_verification"], 3)[0] == "legitimate"


def test_legitimate_needs_more_than_one_caller_turn():
    assert decide_verdict([], ["no_request"], 1)[0] == "undetermined"
    assert decide_verdict([], ["no_request"], 2)[0] == "legitimate"


def test_persona_not_scam_only_breaks_ties():
    assert decide_verdict([], [], 1, persona_not_scam=True)[0] == "legitimate"
    assert decide_verdict(["urgency_deadline"], [], 3, persona_not_scam=True)[0] == "undetermined"
    assert decide_verdict(["asks_secret_credential"], [], 3, persona_not_scam=True)[0] == "scam"


def test_unknown_signals_are_ignored():
    assert decide_verdict(["made_up_flag"], ["made_up_signal"], 4)[0] == "undetermined"


def test_catalogues_do_not_overlap():
    assert not set(HARD_FLAGS) & set(SOFT_FLAGS)
    assert not (set(HARD_FLAGS) | set(SOFT_FLAGS)) & set(LEGIT_SIGNALS)


def test_label_shows_topic_only_for_scams():
    assert verdict_label("scam", "loan_app") == "loan_app"
    assert verdict_label("scam", "not_scam") == "other_scam"
    assert verdict_label("legitimate", "loan_app") == "not_scam"
    assert verdict_label("undetermined", "loan_app") == "undetermined"
    assert verdict_label("scam", "undetermined") == "other_scam"


# ----- evidence grounding -----


def test_quote_must_come_from_the_caller():
    text = "Sir please share the OTP you just received on your mobile"
    assert grounded("share the OTP you just received", text)
    assert grounded("Share the OTP, you just received!", text)  # punctuation and case drift
    assert not grounded("send money to my UPI", text)
    assert not grounded("", text)


def test_grounding_works_for_devanagari():
    text = "आपका खाता आज बंद हो जाएगा, अभी ओटीपी बताइए"
    assert grounded("अभी ओटीपी बताइए", text)
    assert not grounded("पैसे भेजिए", text)


def test_finalize_drops_hallucinated_and_unknown_flags():
    t = turns("Hello, I am calling from HDFC Bank about a pre-approved personal loan.",
              "You can call back on the number behind your card if you want to check.")
    raw = extraction(
        red=[("asks_secret_credential", "tell me the OTP"),          # never said: dropped
             ("not_a_flag", "pre-approved personal loan")],          # unknown id: dropped
        legit=[("offers_official_verification", "call back on the number behind your card")],
    )
    result = finalize(raw, t)
    assert result.red_flags == []
    assert [e.signal for e in result.legit_signals] == ["offers_official_verification"]
    assert result.verdict == "legitimate"


def test_finalize_ignores_persona_words_as_evidence():
    t = [{"speaker": "caller", "text": "Hello sir, loan offer from the bank."},
         {"speaker": "persona", "text": "Should I tell you my OTP?"},
         {"speaker": "caller", "text": "No sir, never share it."}]
    result = finalize(extraction(red=[("asks_secret_credential", "Should I tell you my OTP")]), t)
    assert result.verdict != "scam"


def test_finalize_unknown_topic_becomes_other_scam():
    t = turns("Send the processing fee of 2999 to this UPI to release your loan.")
    raw = extraction(red=[("pay_to_receive", "Send the processing fee of 2999 to this UPI to release your loan")],
                     scam_type="mystery")
    result = finalize(raw, t)
    assert result.verdict == "scam" and result.scam_type == "other_scam"
    assert result.trigger_phrases == ["Send the processing fee of 2999 to this UPI to release your loan"]


# ----- the call-long state -----


def result_for(t, **kw):
    return finalize(extraction(**kw), t)


def test_state_flips_to_scam_when_a_genuine_looking_call_asks_for_an_otp():
    state = VerdictState()
    t = turns("This is Axis Bank about your credit card upgrade.", "You can visit your branch to confirm.")
    state.merge(result_for(t, legit=[("offers_official_verification", "You can visit your branch to confirm")]))
    assert state.summary(2)["verdict"] == "legitimate"
    t2 = t + turns("To finish the upgrade tell me the OTP sent to your phone.")
    state.merge(result_for(t2, red=[("asks_secret_credential", "tell me the OTP sent to your phone")]))
    summary = state.summary(3)
    assert summary["verdict"] == "scam" and summary["scamType"] == "loan_app"
    assert summary["redFlags"][0]["severity"] == "hard"


def test_state_never_forgets_a_flag_when_a_later_window_misses_it():
    state = VerdictState()
    t = turns("Do not tell your son about this case, stay on the line.")
    state.merge(result_for(t, red=[("secrecy_or_isolation", "Do not tell your son about this case")],
                           scam_type="digital_arrest"))
    state.merge(result_for(turns("Okay, hold on."), scam_type="not_scam"))
    summary = state.summary(2)
    assert summary["verdict"] == "scam" and summary["scamType"] == "digital_arrest"


def test_state_summary_carries_labels_and_quotes():
    state = VerdictState()
    t = turns("Please read out your full account number for verification.")
    state.merge(result_for(t, red=[("asks_full_identifier", "read out your full account number")]))
    summary = state.summary(1)
    assert summary["verdict"] == "undetermined" and summary["scamType"] == "undetermined" and summary["stage"] is None
    flag = summary["redFlags"][0]
    assert flag["severity"] == "soft" and flag["quote"] == "read out your full account number"
    assert flag["label"] == analysis.RED_FLAGS["asks_full_identifier"]


def test_verifier_prompt_is_neutral_and_lists_every_signal():
    prompt = analysis.VERIFIER_PROMPT
    assert "suspected scammer" not in prompt
    assert "Do not judge by topic" in prompt
    for key in list(analysis.RED_FLAGS) + list(LEGIT_SIGNALS):
        assert key in prompt
