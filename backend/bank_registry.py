"""Which bank must hear about a payee detail: IFSC prefixes, UPI handles and bank names spoken by the caller.

Routing rules (in order of confidence):
- An IFSC names the bank directly: its first four letters are the bank code (SBIN0001234 -> State Bank of India).
- A UPI ID is hosted by the PSP bank behind its handle (name@okaxis -> Axis Bank, which runs that Google Pay handle).
  The PSP bank can resolve the ID to the linked account, even when that account sits at another bank.
- A bare account number carries no bank. It is routed by an IFSC given in the same call, or by a bank the caller names
  in the same sentence; otherwise it waits for a human (the UNRESOLVED queue).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# IFSC bank code -> bank. Real codes, because routing depends on them; the inboxes they feed are proxies.
BANKS: dict[str, str] = {
    "SBIN": "State Bank of India",
    "HDFC": "HDFC Bank",
    "ICIC": "ICICI Bank",
    "UTIB": "Axis Bank",
    "PUNB": "Punjab National Bank",
    "BARB": "Bank of Baroda",
    "CNRB": "Canara Bank",
    "UBIN": "Union Bank of India",
    "KKBK": "Kotak Mahindra Bank",
    "YESB": "Yes Bank",
    "IDIB": "Indian Bank",
    "IOBA": "Indian Overseas Bank",
    "BKID": "Bank of India",
    "MAHB": "Bank of Maharashtra",
    "CBIN": "Central Bank of India",
    "UCBA": "UCO Bank",
    "PSIB": "Punjab & Sind Bank",
    "INDB": "IndusInd Bank",
    "IDFB": "IDFC First Bank",
    "FDRL": "Federal Bank",
    "RATN": "RBL Bank",
    "AUBL": "AU Small Finance Bank",
    "BDBL": "Bandhan Bank",
    "KARB": "Karnataka Bank",
    "KVBL": "Karur Vysya Bank",
    "SIBL": "South Indian Bank",
    "TMBL": "Tamilnad Mercantile Bank",
    "CSBK": "CSB Bank",
    "DLXB": "Dhanlaxmi Bank",
    "JAKA": "Jammu & Kashmir Bank",
    "ESFB": "Equitas Small Finance Bank",
    "UJVN": "Ujjivan Small Finance Bank",
    "PYTM": "Paytm Payments Bank",
    "AIRP": "Airtel Payments Bank",
    "IPOS": "India Post Payments Bank",
    "FINO": "Fino Payments Bank",
}
UNRESOLVED = "UNRESOLVED"
UNRESOLVED_NAME = "Unresolved (needs an NPCI or I4C lookup)"

# UPI handle -> (PSP bank code, app that issues it). Only handles we are sure of; anything else is UNRESOLVED.
UPI_HANDLES: dict[str, tuple[str, str | None]] = {
    "okaxis": ("UTIB", "Google Pay"),
    "okhdfcbank": ("HDFC", "Google Pay"),
    "okicici": ("ICIC", "Google Pay"),
    "oksbi": ("SBIN", "Google Pay"),
    "ybl": ("YESB", "PhonePe"),
    "ibl": ("ICIC", "PhonePe"),
    "axl": ("UTIB", "PhonePe"),
    "paytm": ("PYTM", "Paytm"),
    "ptyes": ("YESB", "Paytm"),
    "ptaxis": ("UTIB", "Paytm"),
    "pthdfc": ("HDFC", "Paytm"),
    "ptsbi": ("SBIN", "Paytm"),
    "apl": ("UTIB", "Amazon Pay"),
    "yapl": ("YESB", "Amazon Pay"),
    "jupiteraxis": ("UTIB", "Jupiter"),
    "sbi": ("SBIN", None),
    "hdfcbank": ("HDFC", None),
    "icici": ("ICIC", None),
    "axisbank": ("UTIB", None),
    "pnb": ("PUNB", None),
    "barodampay": ("BARB", "bob World"),
    "kotak": ("KKBK", None),
    "yesbank": ("YESB", None),
    "idfcbank": ("IDFB", None),
    "federal": ("FDRL", None),
    "indus": ("INDB", None),
    "aubank": ("AUBL", None),
    "rbl": ("RATN", None),
    "kbl": ("KARB", None),
    "cnrb": ("CNRB", None),
    "unionbank": ("UBIN", None),
    "unionbankofindia": ("UBIN", None),
    "boi": ("BKID", None),
    "mahb": ("MAHB", None),
    "cbin": ("CBIN", None),
    "airtel": ("AIRP", "Airtel Thanks"),
    "postbank": ("IPOS", "IPPB"),
}

# Spoken or written bank names -> code. Longest names are tried first, so 'state bank of india' never also matches
# 'bank of india', and 'indian overseas bank' never also matches 'indian bank'.
_ALIASES: dict[str, str] = {
    "state bank of india": "SBIN", "state bank": "SBIN", "sbi": "SBIN",
    "hdfc bank": "HDFC", "hdfc": "HDFC",
    "icici bank": "ICIC", "icici": "ICIC",
    "axis bank": "UTIB", "axis": "UTIB",
    "punjab national bank": "PUNB", "pnb": "PUNB",
    "bank of baroda": "BARB", "baroda bank": "BARB",
    "canara bank": "CNRB", "canara": "CNRB",
    "union bank of india": "UBIN", "union bank": "UBIN",
    "kotak mahindra bank": "KKBK", "kotak bank": "KKBK", "kotak": "KKBK",
    "yes bank": "YESB",
    "indian overseas bank": "IOBA",
    "indian bank": "IDIB",
    "bank of india": "BKID",
    "bank of maharashtra": "MAHB",
    "central bank of india": "CBIN", "central bank": "CBIN",
    "uco bank": "UCBA",
    "punjab and sind bank": "PSIB", "punjab & sind bank": "PSIB",
    "indusind bank": "INDB", "indusind": "INDB",
    "idfc first bank": "IDFB", "idfc bank": "IDFB", "idfc": "IDFB",
    "federal bank": "FDRL",
    "rbl bank": "RATN",
    "au small finance bank": "AUBL", "au bank": "AUBL",
    "bandhan bank": "BDBL",
    "paytm payments bank": "PYTM", "paytm bank": "PYTM",
    "airtel payments bank": "AIRP",
    "india post payments bank": "IPOS", "ippb": "IPOS",
    "स्टेट बैंक": "SBIN", "एसबीआई": "SBIN",
    "एचडीएफसी": "HDFC",
    "आईसीआईसीआई": "ICIC",
    "एक्सिस": "UTIB",
    "पंजाब नेशनल": "PUNB", "पीएनबी": "PUNB",
    "बैंक ऑफ बड़ौदा": "BARB", "बड़ौदा": "BARB",
    "केनरा": "CNRB",
    "कोटक": "KKBK",
    "यस बैंक": "YESB",
}
_ALIAS_RE = re.compile(
    "|".join(rf"(?<![\w\u0900-\u097F]){re.escape(a)}(?![\w\u0900-\u097F])" for a in sorted(_ALIASES, key=len, reverse=True)),
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Route:
    """Where a detail goes and why."""

    bank_code: str
    bank_name: str
    routed_by: str  # "ifsc" | "upi_handle" | "bank_named" | "unresolved"
    reason: str
    ifsc: str = ""
    upi_app: str | None = None


def bank_name(code: str) -> str:
    return UNRESOLVED_NAME if code == UNRESOLVED else BANKS.get(code, code)


def from_ifsc(ifsc: str) -> Route | None:
    code = ifsc[:4].upper()
    if code not in BANKS:
        return None
    return Route(code, BANKS[code], "ifsc", f"IFSC {ifsc.upper()} belongs to {BANKS[code]}", ifsc=ifsc.upper())


def from_upi(upi_id: str) -> Route:
    handle = upi_id.rsplit("@", 1)[-1].lower() if "@" in upi_id else ""
    if handle in UPI_HANDLES:
        code, app = UPI_HANDLES[handle]
        via = f" ({app})" if app else ""
        return Route(code, BANKS[code], "upi_handle",
                     f"UPI handle @{handle}{via} is run by {BANKS[code]}, which can resolve it to the linked account",
                     upi_app=app)
    return Route(UNRESOLVED, UNRESOLVED_NAME, "unresolved", f"Unknown UPI handle @{handle or '?'}")


def banks_named_in(text: str) -> list[str]:
    """Bank codes the text names, in order of first mention, without duplicates."""
    out: list[str] = []
    for match in _ALIAS_RE.finditer(text or ""):
        word = match.group(0)
        code = _ALIASES.get(word.lower()) or _ALIASES.get(word)
        if code and code not in out:
            out.append(code)
    return out


def directory() -> list[dict]:
    """Every proxy bank inbox, for the portal."""
    return [{"code": code, "name": name} for code, name in BANKS.items()] + [{"code": UNRESOLVED, "name": UNRESOLVED_NAME}]
