import analysis
from analysis import build_evidence, percentile, redact, shared_sensitive_info, upsert_detail


def add(details, dtype, raw, source, turn, quote=""):
    return upsert_detail(details, dtype=dtype, raw=raw, source=source, turn=turn, t_sec=1.0, quote=quote)


def test_single_source_is_unconfirmed():
    details = {}
    detail, changed = add(details, "upi_id", "rahul dot sharma at okaxis", "live_tool", 1)
    assert changed
    assert detail["normalizedValue"] == "rahul.sharma@okaxis"
    assert detail["valid"] and not detail["confirmed"]


def test_two_layers_agreeing_confirm_after_normalisation():
    details = {}
    add(details, "upi_id", "rahul dot sharma at okaxis", "live_tool", 1)
    detail, changed = add(details, "upi_id", "Rahul.Sharma@okaxis", "verifier", 1)
    assert changed and detail["confirmed"]
    assert len(details) == 1
    assert detail["confidence"] > 0.7


def test_caller_repeating_in_a_later_turn_confirms():
    details = {}
    add(details, "bank_account", "one two three four five six seven eight nine zero one two", "live_tool", 2)
    detail, _ = add(details, "bank_account", "123456789012", "live_tool", 4)
    assert detail["confirmed"]


def test_invalid_detail_is_never_confirmed():
    details = {}
    add(details, "bank_account", "123", "live_tool", 1)
    detail, _ = add(details, "bank_account", "123", "verifier", 1)
    assert not detail["valid"] and not detail["confirmed"]
    assert detail["confidence"] == 0.2


def test_unknown_type_and_empty_value_are_ignored():
    assert add({}, "favourite_colour", "blue", "live_tool", 1) == (None, False)
    assert add({}, "upi_id", "  ", "live_tool", 1) == (None, False)


def test_same_detail_again_reports_no_change():
    details = {}
    add(details, "phone_number", "98765 43210", "verifier", 1)
    _, changed = add(details, "phone_number", "9876543210", "verifier", 1)
    assert not changed


def test_redact_hides_identifiers():
    text = "Send to rahul.sharma@okaxis or visit http://bad.example.com/a.apk, account 123456789012."
    out = redact(text)
    assert "rahul" not in out and "bad.example" not in out
    assert "redacted@upi" in out and "[link]" in out and out.endswith("XXXXXXXX9012.")


def test_drill_stop_triggers_on_four_digits_spoken_or_written():
    assert shared_sensitive_info("mera otp hai 4 5 6 7")
    assert shared_sensitive_info("ek do teen char")
    assert shared_sensitive_info("१२३४५६")
    assert not shared_sensitive_info("OTP kya hota hai? Main toh do baje aaunga")


def test_payment_demand_detection_english_hinglish_hindi():
    assert analysis.looks_like_payment_demand("You must send the money by UPI right now")
    assert analysis.looks_like_payment_demand("Abhi paise bhejiye, ek ghante mein")
    assert analysis.looks_like_payment_demand("\u0905\u092d\u0940 \u092a\u0948\u0938\u0947 \u092d\u0947\u091c\u093f\u090f")
    assert not analysis.looks_like_payment_demand("A parcel in your name was caught with illegal items.")


def test_percentile():
    assert percentile([], 50) is None
    assert percentile([100, 200, 300, 400, 500], 50) == 300
    assert percentile([100, 200, 300, 400, 500], 90) == 500


def test_evidence_pack_separates_confirmed_and_carries_disclaimer():
    details = {}
    add(details, "upi_id", "rahul.sharma@okaxis", "live_tool", 1, quote="UPI ID hai rahul dot sharma at okaxis")
    add(details, "upi_id", "rahul.sharma@okaxis", "verifier", 1)
    add(details, "phone_number", "9876543210", "live_tool", 1)
    turns = [{"n": 1, "speaker": "caller", "text": "UPI ID hai rahul dot sharma at okaxis", "tSec": 4.2}]
    pack = build_evidence({"callId": "abc", "mode": "live", "scamType": "digital_arrest"}, turns,
                          list(details.values()), None)
    assert [d["value"] for d in pack["confirmedDetails"]] == ["rahul.sharma@okaxis"]
    assert [d["value"] for d in pack["unconfirmedDetails"]] == ["9876543210"]
    assert pack["confirmedDetails"][0]["quote"].startswith("UPI ID hai")
    assert "not a finding" in pack["disclaimer"]
    assert pack["schema"] == "honeytrap.evidence.v1"


def test_demo_strain_has_three_red_flags_and_no_identifiers():
    strain = analysis.DEMO_STRAINS[0]
    assert len(strain["redFlags"]) == 3
    assert all(redact(e) == e for e in strain["scriptExcerpts"])
