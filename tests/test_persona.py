import random
import re
from datetime import datetime

from persona import IST, MOVES, CallProfile, build_persona, build_persona_text, turn_note

NOW = datetime(2026, 10, 15, 15, 5, tzinfo=IST)


def test_profiles_differ_between_calls():
    prompts = {build_persona(CallProfile(random.Random(seed), NOW)) for seed in range(12)}
    assert len(prompts) > 8


def test_profile_is_reproducible_with_a_seed():
    assert build_persona(CallProfile(random.Random(3), NOW)) == build_persona(CallProfile(random.Random(3), NOW))


def test_prompt_carries_the_profile_and_keeps_the_safety_rules():
    profile = CallProfile(random.Random(1), NOW)
    prompt = build_persona(profile)
    assert profile.mood in prompt and profile.greeting in prompt
    assert "NEVER say any number or digit of your own" in prompt
    assert "NEVER SHARE" in prompt and "CVV" in prompt
    assert "record_detail" in prompt


def test_prompt_tells_the_persona_the_date_and_time():
    assert "Thursday, 15 October 2026, about 3:05 pm" in build_persona(CallProfile(random.Random(1), NOW))


def test_persona_answers_plain_questions_but_never_gives_numbers():
    prompt = build_persona(CallProfile(random.Random(1), NOW))
    assert "A plain question gets a plain, direct answer" in prompt
    assert "Numbers are different: you never say any number of your own" in prompt
    assert "9876543210" not in prompt and "34506721890" not in prompt and "House 42" not in prompt
    assert not re.search(r"\d{5,}", prompt)
    assert "answer a slightly different question" not in prompt


def test_persona_is_not_told_to_treat_every_caller_as_a_scammer():
    prompt = build_persona(CallProfile(random.Random(1), NOW))
    assert "most callers are\nordinary people" in prompt
    assert "Never call it for an ordinary caller" in prompt


def test_prompt_has_no_catchphrases_to_copy():
    prompt = build_persona_text(CallProfile(random.Random(2)))
    assert "sahi hai?" not in prompt
    assert "Arre... what parcel" not in prompt


def test_turn_note_forbids_recent_openers_and_suggests_a_move():
    note = turn_note(["Arre, which parcel?", "Haan ji, I am listening.", "Hmm... one moment"], random.Random(0))
    for word in ("arre", "haan", "hmm"):
        assert word in note
    assert any(move in note for move in MOVES)


def test_turn_note_without_history_has_no_forbidden_list():
    assert "Do not begin with" not in turn_note([], random.Random(0))


def test_hindi_deployment_greets_in_hindi(monkeypatch):
    import config

    monkeypatch.setattr(config, "LANGUAGE_CODE", "hi-IN")
    profile = CallProfile(random.Random(4))
    assert any("\u0900" <= ch <= "\u097f" for ch in profile.greeting)
    assert "Hindi" in build_persona(profile)


def test_english_deployment_greets_in_english():
    profile = CallProfile(random.Random(4))
    assert not any("\u0900" <= ch <= "\u097f" for ch in profile.greeting)


def test_english_replies_may_not_use_hindi_words():
    assert "No Hindi words at all" in build_persona(CallProfile(random.Random(5)))


def test_persona_tests_the_caller_before_calling_it_a_scam():
    prompt = build_persona(CallProfile(random.Random(6)))
    assert "decide by what the caller ASKS FOR, never by the topic" in prompt
    assert "ring back on the number printed on your passbook" in prompt
    assert "end_call and reason not_scam" in prompt
