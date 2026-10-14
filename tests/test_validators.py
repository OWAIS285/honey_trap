import pytest

from validators import validate_detail


@pytest.mark.parametrize(
    "detail_type, raw, valid, normalized",
    [
        ("upi_id", "rahul dot sharma at okaxis", True, "rahul.sharma@okaxis"),
        ("upi_id", "Rahul.Sharma@OkAxis", True, "rahul.sharma@okaxis"),
        ("upi_id", "rahul sharma", False, "rahulsharma"),
        ("bank_account", "one two three four five six seven eight nine zero one two", True, "123456789012"),
        ("bank_account", "one two three", False, "123"),
        ("ifsc", "S B I N zero zero zero one two three four", True, "SBIN0001234"),
        ("ifsc", "SBIN1001234", False, "SBIN1001234"),
        ("phone_number", "nau aath saat chhe paanch char teen do ek shunya", True, "9876543210"),
        ("phone_number", "plus nine one 98765 43210", True, "9876543210"),
        ("phone_number", "0 98765 43210", True, "9876543210"),
        ("phone_number", "5876543210", False, "5876543210"),
        ("person_name", "  Inspector Verma ", True, "Inspector Verma"),
        ("amount_demanded", "Rs 50,000 rupees", True, "50000"),
        ("amount_demanded", "pachaas hazaar", True, "pachaas hazaar"),
    ],
)
def test_validate_detail(detail_type: str, raw: str, valid: bool, normalized: str) -> None:
    result = validate_detail(detail_type, raw)
    assert result.valid is valid
    assert result.normalized == normalized


def test_url_flags_apk() -> None:
    result = validate_detail("url", "http://bank-kyc.example.com/update.apk")
    assert result.valid
    assert result.flags == ("apk",)


@pytest.mark.parametrize("raw", ["not a url", "", "http://nodot"])
def test_url_rejects_garbage(raw: str) -> None:
    assert not validate_detail("url", raw).valid
