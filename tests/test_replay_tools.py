import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

import make_replay as replay  # noqa: E402


def test_english_lines_may_not_contain_hindi_or_devanagari():
    assert replay.language_problems("Sir, you must transfer the deposit now.", "english") == []
    assert replay.language_problems("Beta, haan, I understand", "english")
    assert replay.language_problems("सर, ट्रांसफर कीजिए", "english") == ["Devanagari"]


def test_hindi_lines_allow_acronyms_and_upi_ids_only():
    assert replay.language_problems("सीबीआई साइबर क्राइम से UPI आईडी rahul.sharma@okaxis", "hindi") == []
    assert replay.language_problems("सर, please transfer करें", "hindi") == ["please", "transfer"]


def test_details_the_script_never_contained_are_spurious():
    assert replay.spurious({"type": "phone_number", "normalizedValue": "4523153108624"}, {})
    assert replay.spurious({"type": "case_or_badge_id", "normalizedValue": "4523153108624"}, {})
    assert not replay.spurious({"type": "case_or_badge_id", "normalizedValue": "4721"}, {})
    assert not replay.spurious({"type": "upi_id", "normalizedValue": "rahul.sharma@okaxis"}, {})


def test_squeeze_shortens_long_pauses_but_keeps_speech():
    rate = replay.RATE
    tone = (0.3 * np.sin(np.linspace(0, 2000, rate))).astype(np.float32)  # one second of sound
    clip = np.concatenate([tone, np.zeros(rate * 2, dtype=np.float32), tone])
    squeezed = replay.squeeze(clip)
    assert len(squeezed) < len(clip) - rate
    assert len(squeezed) > 2 * rate
