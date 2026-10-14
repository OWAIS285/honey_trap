"""Deterministic validators for details extracted from scam calls."""

import re
from dataclasses import dataclass
from urllib.parse import urlparse

from normalizer import normalize_digits, normalize_identifier

UPI_RE = re.compile(r"^[a-zA-Z0-9._-]{2,256}@[a-zA-Z]{2,64}$")
ACCOUNT_RE = re.compile(r"^[0-9]{9,18}$")
IFSC_RE = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")
MOBILE_RE = re.compile(r"^[6-9][0-9]{9}$")


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    normalized: str
    flags: tuple[str, ...] = ()


def _normalize_phone(raw: str) -> str:
    digits = normalize_digits(raw)
    if len(digits) == 12 and digits.startswith("91"):
        return digits[2:]
    if len(digits) == 11 and digits.startswith("0"):
        return digits[1:]
    return digits


def _validate_url(raw: str) -> ValidationResult:
    value = raw.strip()
    if not value or re.search(r"\s", value):
        return ValidationResult(False, value)
    parsed = urlparse(value if "://" in value else f"http://{value}")
    if parsed.scheme not in ("http", "https") or "." not in parsed.netloc:
        return ValidationResult(False, value)
    flags = ("apk",) if parsed.path.lower().endswith(".apk") else ()
    return ValidationResult(True, value, flags)


def validate_detail(detail_type: str, raw: str) -> ValidationResult:
    """Normalize ``raw`` for ``detail_type`` and check it; free-text types are always valid."""
    if detail_type == "upi_id":
        value = normalize_identifier(raw).lower()
        return ValidationResult(bool(UPI_RE.match(value)), value)
    if detail_type == "bank_account":
        value = normalize_digits(raw)
        return ValidationResult(bool(ACCOUNT_RE.match(value)), value)
    if detail_type == "ifsc":
        value = normalize_identifier(raw).upper()
        return ValidationResult(bool(IFSC_RE.match(value)), value)
    if detail_type == "phone_number":
        value = _normalize_phone(raw)
        return ValidationResult(bool(MOBILE_RE.match(value)), value)
    if detail_type == "url":
        return _validate_url(raw)
    return ValidationResult(True, raw.strip())
