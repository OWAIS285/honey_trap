import random

from persona import MOVES, CallProfile, build_persona, build_persona_text, turn_note


def test_profiles_differ_between_calls():
    prompts = {build_persona(CallProfile(random.Random(seed))) for seed in range(12)}
    assert len(prompts) > 8


def test_profile_is_reproducible_with_a_seed():
    assert build_persona(CallProfile(random.Random(3))) == build_persona(CallProfile(random.Random(3)))


def test_prompt_carries_the_profile_and_keeps_the_safety_rules():
    profile = CallProfile(random.Random(1))
    prompt = build_persona(profile)
    assert profile.mood in prompt and profile.greeting in prompt
    assert "NEVER give any real personal" in prompt
    assert "record_detail" in prompt


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
