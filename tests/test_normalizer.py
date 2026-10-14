import pytest

from normalizer import normalize_digits, normalize_identifier


@pytest.mark.parametrize(
    "spoken, expected",
    [
        ("nau aath saat chhe paanch char teen do ek shunya", "9876543210"),
        ("nine eight seven six five four three two one zero", "9876543210"),
        ("नौ आठ सात छह पाँच चार तीन दो एक शून्य", "9876543210"),
        ("९८७६५४३२१०", "9876543210"),
        ("double nine eight triple seven", "998777"),
        ("zero oh one", "001"),
        ("98765-43210", "9876543210"),
        ("98765 43210", "9876543210"),
        ("98765.43210", "9876543210"),
        ("my number is nine eight", "98"),
    ],
)
def test_normalize_digits(spoken: str, expected: str) -> None:
    assert normalize_digits(spoken) == expected


@pytest.mark.parametrize(
    "spoken, expected",
    [
        ("rahul dot sharma at okaxis", "rahul.sharma@okaxis"),
        ("rahul nine eight at the rate of okaxis", "rahul98@okaxis"),
        ("r a h u l at okaxis", "rahul@okaxis"),
        ("S B I N zero zero zero one two three four", "SBIN0001234"),
        ("rahul underscore double seven at ybl", "rahul_77@ybl"),
        ("rahul.sharma@okaxis", "rahul.sharma@okaxis"),
        ("one.piece@okaxis", "one.piece@okaxis"),
        ("एस बी आई एन शून्य शून्य शून्य एक दो तीन चार", "SBIN0001234"),
        ("एच डी एफ सी शून्य एक दो तीन चार पाँच छह", "HDFC0123456"),
    ],
)
def test_normalize_identifier(spoken: str, expected: str) -> None:
    assert normalize_identifier(spoken) == expected
