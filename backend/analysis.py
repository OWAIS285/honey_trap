"""Verifier/classifier, detail merging with the confirmation rule, strain builder, redaction, evidence pack."""

from __future__ import annotations

import logging
import re
import secrets
from datetime import datetime, timezone

from google.genai import types
from pydantic import BaseModel, Field

import config
from clients import flash
from normalizer import normalize_digits
from persona import DETAIL_TYPES, STAGES
from validators import validate_detail

log = logging.getLogger("stallwart.analysis")

TAXONOMY = [
    "digital_arrest",
    "courier_parcel",
    "telecom_trai_sim_block",
    "bank_kyc_block",
    "electricity_bill",
    "investment_trading",
    "task_job",
    "lottery_prize",
    "fake_customer_care",
    "family_emergency",
    "loan_app",
    "other_scam",
    "not_scam",
    "undetermined",
]
NON_SCAM = ("not_scam", "undetermined")
# Below this a scam verdict is not shown; with no quoted caller words it must be very sure.
SCAM_CONFIDENCE_FLOOR = 0.6
SCAM_CONFIDENCE_UNQUOTED = 0.85

DISCLAIMER = (
    "Details were stated by an unverified caller during an automated decoy call and may be mis-heard or belong to "
    "an innocent third party. This pack is a lead for investigators, not a finding that any account is fraudulent."
)

DEFAULT_RED_FLAGS = [
    "The caller creates fear and urgency so you do not think.",
    "A real agency never asks for money or UPI transfers over a phone call.",
    "Hang up and call your family or the official number yourself.",
]


class VerifierDetail(BaseModel):
    type: str = Field(description="One of: " + ", ".join(DETAIL_TYPES))
    value: str = Field(description="The detail written normally: digits as digits, UPI ID as name@handle.")
    raw_utterance: str = Field(description="The caller's exact words that contain the detail.")


class VerifierResult(BaseModel):
    scam_type: str = Field(description="One of: " + ", ".join(TAXONOMY))
    confidence: float = Field(description="0 to 1")
    trigger_phrases: list[str] = Field(description="Up to 4 short phrases copied exactly from the CALLER's words.")
    impersonated_entity: str = Field(description="Organisation the caller claims to be, or an empty string.")
    stage: str = Field(description="One of: " + ", ".join(STAGES))
    details: list[VerifierDetail]


class StrainCard(BaseModel):
    scam_type: str
    impersonated_entity: str
    steps: list[str] = Field(description="3 to 6 short sentences describing the scammer's script in order.")
    red_flags: list[str] = Field(description="Exactly 3 plain-language warning signs of this script.")
    payment_method: str
    script_excerpts: list[str] = Field(description="2 or 3 short caller quotes with all identifiers replaced.")
    language: str = Field(description="english, hindi or hinglish")


VERIFIER_PROMPT = f"""You review a phone call between a CALLER and a PERSONA (an elderly man who picked up).
The CALLER is an unknown person. Most callers are ordinary and a few are scammers, so do not assume a scam.
Only the CALLER's words count as evidence.

A call is a SCAM only when the caller is trying to get money, credentials or control of the person's phone or
accounts through deception or pressure. Typical behaviours:
- fear or urgency: arrest, a blocked account or SIM, legal action, a deadline
- pretending to be an authority (police, CBI, bank, TRAI, courier, electricity board) and demanding action
- secrecy or isolation: 'tell nobody', 'stay on the line'
- asking for money, a fee, a deposit, a transfer to a personal account or UPI ID, or a payment for a prize, refund,
  job, loan or investment
- asking for an OTP, PIN, CVV, password or full card number, or asking to install a remote-access app or APK, or
  to click a link

A call is NOT a scam (not_scam) when it is ordinary: a wrong number, a friend or family member, a genuine delivery or
appointment, a survey, a shopkeeper or neighbour, small talk, simple questions about the person (name, area, phone
number, bank, account number, the time, general knowledge), or a mention of a bank, account or phone number that
carries no pressure and asks for no secret and no money. A name, city, phone number, bank name or account number is
never a scam signal by itself, and neither is one word such as 'bank', 'UPI' or 'police'. Judge the pattern of
behaviour over the whole call, not a single keyword.

If there is too little to judge (a greeting, a few neutral lines) answer undetermined with low confidence. Never
guess 'scam' to be safe: a false scam alert on a genuine caller is a serious error. When the call is clearly
ordinary answer not_scam.

Return JSON with:
- scam_type: one of {', '.join(TAXONOMY)}
- confidence: 0 to 1, how sure you are of that scam_type (for not_scam, how sure you are the call is harmless)
- trigger_phrases: for a scam only, up to 4 short phrases copied EXACTLY from the CALLER's words that show it;
  an empty list otherwise
- impersonated_entity: the organisation the caller claims to be, or an empty string
- stage: the current stage of a scam, one of {', '.join(STAGES)} (use hook when it is not a scam)
- details: every detail the CALLER stated. type is one of {', '.join(DETAIL_TYPES)}. value is the detail written
  normally (digits as digits, UPI ID as name@handle, spoken numbers converted). raw_utterance is the caller's exact
  words containing it.
Callers may speak English, Hindi (Devanagari or Roman letters) or a mix. If nothing is stated, return an empty list."""

STRAIN_PROMPT = """You are a fraud analyst. From this scam-call transcript build a 'scam strain' card as JSON:
- scam_type: one of {taxonomy}
- impersonated_entity: the organisation the caller claims to be
- steps: 3 to 6 short imperative sentences describing the scammer's script in order
- red_flags: EXACTLY 3 short plain-language warning signs of THIS script, written for an elderly listener
- payment_method: how the caller wants money sent, without any identifiers
- script_excerpts: 2 or 3 short quotes from the CALLER with every phone number, account number, UPI ID and link
  replaced by a placeholder
- language: english, hindi or hinglish
Write in English except for the quotes."""

DEMO_STRAINS = [
    {
        "strainId": "demo_digital_arrest",
        "demo": True,
        "scamType": "digital_arrest",
        "impersonatedEntity": "CBI / Cyber Crime",
        "steps": [
            "Caller claims to be a CBI officer and says a parcel in the victim's name contains illegal items.",
            "Says the victim's Aadhaar was used for a crime and an arrest warrant is ready.",
            "Orders the victim to stay on the call and tell nobody, calling it a secret investigation.",
            "Demands a 'security deposit' by UPI to prove innocence, with a deadline of one hour.",
        ],
        "redFlags": [
            "A real agency never arrests anyone over the phone or by video call.",
            "Being told to stay on the line and tell nobody is a trap to isolate you.",
            "No officer ever asks you to send money to a personal UPI ID to prove you are innocent.",
        ],
        "paymentMethod": "UPI transfer to a personal account called a security deposit",
        "scriptExcerpts": [
            "A parcel in your name was caught with illegal items, there is an arrest warrant.",
            "Do not tell anyone, send the deposit to redacted@upi within one hour.",
        ],
        "language": "hinglish",
    }
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def mask(value: str) -> str:
    """Keep only the last 4 characters so logs never hold a full identifier."""
    return value if len(value) <= 4 else "*" * (len(value) - 4) + value[-4:]


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(p / 100 * (len(ordered) - 1))))]


def upsert_detail(
    details: dict[str, dict],
    *,
    dtype: str,
    raw: str,
    source: str,
    turn: int | None,
    t_sec: float,
    quote: str = "",
) -> tuple[dict | None, bool]:
    """Add or update a detail. confirmed = valid and (seen by two layers or repeated in two caller turns)."""
    if dtype not in DETAIL_TYPES or not raw.strip():
        return None, False
    res = validate_detail(dtype, raw)
    key = f"{dtype}:{res.normalized.lower()}"
    detail = details.get(key)
    created = detail is None
    if created:
        detail = {
            "id": secrets.token_hex(4),
            "type": dtype,
            "rawValue": raw.strip(),
            "normalizedValue": res.normalized,
            "valid": res.valid,
            "flags": list(res.flags),
            "sources": [],
            "turns": [],
            "confirmed": False,
            "confidence": 0.0,
            "evidence": quote.strip(),
            "firstSeenSec": round(t_sec, 1),
        }
        details[key] = detail
        before = None
    else:
        before = (list(detail["sources"]), list(detail["turns"]), detail["confirmed"])
    if source not in detail["sources"]:
        detail["sources"].append(source)
    if turn is not None and turn not in detail["turns"]:
        detail["turns"].append(turn)
    if quote and not detail["evidence"]:
        detail["evidence"] = quote.strip()
    detail["confirmed"] = bool(detail["valid"] and (len(detail["sources"]) >= 2 or len(detail["turns"]) >= 2))
    confidence = 0.5 + 0.25 * (len(detail["sources"]) - 1) + 0.15 * (len(detail["turns"]) - 1)
    detail["confidence"] = round(min(0.99, confidence), 2) if detail["valid"] else 0.2
    after = (detail["sources"], detail["turns"], detail["confirmed"])
    return detail, created or before != after


_UPI = re.compile(r"[\w.\-]{2,}@[A-Za-z]{2,}")
_URL = re.compile(r"https?://\S+|\b[\w-]+\.(?:com|in|net|org|app|apk|xyz|link|co)\b\S*", re.IGNORECASE)
_LONG_NUMBER = re.compile(r"\d[\d \-]{5,}\d")


def redact(text: str) -> str:
    """Replace identifiers with placeholders (UPI IDs, links, long numbers keep their last 4 digits)."""

    def number(match: re.Match) -> str:
        digits = re.sub(r"\D", "", match.group())
        return "X" * (len(digits) - 4) + digits[-4:] if len(digits) > 4 else match.group()

    text = _UPI.sub("redacted@upi", text)
    text = _URL.sub("[link]", text)
    return _LONG_NUMBER.sub(number, text)


def shared_sensitive_info(text: str) -> bool:
    """Drill stop (a): the listener says four or more digits in a row, spoken or written."""
    return len(normalize_digits(text)) >= 4


_PAYMENT_DEMAND = re.compile(
    r"\b(upi|transfer|deposit|payment|pay|paise|rupaye|rupees|rupay|bhej\w*|account number|bank details|send (?:the )?(?:money|amount))\b"
    r"|पैसे|रुपये|ट्रांसफर|भेज",
    re.IGNORECASE,
)


def looks_like_payment_demand(text: str) -> bool:
    """Drill stop (b): the scammer actor is about to ask for money or payment details."""
    return bool(_PAYMENT_DEMAND.search(text))


def _thinking() -> types.ThinkingConfig | None:
    try:
        return types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW)
    except Exception:  # noqa: BLE001 - older SDKs lack the field
        return None


def _transcript(turns: list[dict], limit: int) -> str:
    return "\n".join(
        f"{'CALLER' if t['speaker'] == 'caller' else 'PERSONA'}: {t['text']}" for t in turns[-limit:]
    )


_DEVANAGARI = re.compile(r"[\u0900-\u097F]")
# Words that are Hindi and never English, to spot Roman-script Hindi and Hinglish.
_ROMAN_HINDI = re.compile(
    r"\b(hai|hain|nahi|nahin|kya|aap|aapka|aapke|aapki|mera|meri|mere|mujhe|kaun|kyun|kaise|abhi|jaldi|beta|haan|"
    r"achha|accha|paisa|paise|rupaye|bhej|bhejo|batao|bataiye|bolo|boliye|karo|kijiye|sahab|sahib|arre|arey|theek|"
    r"thik|samajh|matlab|ghar|bhai|suniye|suno|dekhiye|namaste|dhanyavaad|shukriya)\b",
    re.IGNORECASE,
)


def needs_translation(text: str) -> bool:
    """True when a transcript line is Hindi (Devanagari or Roman letters) or Hinglish, so the display needs English."""
    return bool(_DEVANAGARI.search(text) or _ROMAN_HINDI.search(text))


TRANSLATE_PROMPT = (
    "Translate this line from a phone call into plain, natural English, keeping the speaker's tone. Keep names, "
    "numbers, UPI IDs, IFSC codes and acronyms (CBI, UPI, OTP) exactly as written, with spoken digits written as digits. "
    "Output only the translation: no quotes, notes or explanations.\n\nLINE:\n"
)


async def to_english(client, text: str) -> str | None:
    """English version of a Hindi or Hinglish line, or None when the translation fails (the caller keeps the original)."""
    try:
        response = await flash(
            client,
            contents=TRANSLATE_PROMPT + text,
            cfg=types.GenerateContentConfig(temperature=0.0, thinking_config=types.ThinkingConfig(thinking_budget=0)),
            attempts=3,
            model=config.TRANSLATE_MODEL,
        )
        english = " ".join((response.text or "").split())
    except Exception:  # noqa: BLE001 - a missing translation must never break the call
        log.warning("translation failed")
        return None
    return english if english and not _DEVANAGARI.search(english) else None


def settle_verdict(result: VerifierResult, caller_text: str) -> VerifierResult:
    """Clean the model's verdict. A scam label has to be backed by confidence and, usually, quoted caller words."""
    if result.scam_type not in TAXONOMY:
        result.scam_type = "other_scam"
    result.confidence = max(0.0, min(1.0, result.confidence))
    haystack = re.sub(r"\s+", " ", caller_text.lower())
    result.trigger_phrases = [
        p.strip() for p in result.trigger_phrases if p.strip() and re.sub(r"\s+", " ", p.strip().lower()) in haystack
    ][:4]
    if result.scam_type not in NON_SCAM and (
        result.confidence < SCAM_CONFIDENCE_FLOOR
        or (not result.trigger_phrases and result.confidence < SCAM_CONFIDENCE_UNQUOTED)
    ):
        result.scam_type = "undetermined"
        result.confidence = min(result.confidence, 0.4)
    if result.scam_type in NON_SCAM:
        result.trigger_phrases = []
        result.impersonated_entity = ""
        result.stage = ""
    elif result.stage not in STAGES:
        result.stage = "hook"
    return result


async def verify(client, turns: list[dict]) -> VerifierResult | None:
    """Second, independent extraction layer: Gemini Flash over the recent turns with a strict JSON schema."""
    if not any(t["speaker"] == "caller" for t in turns):
        return None
    try:
        response = await flash(
            client,
            contents=VERIFIER_PROMPT + "\n\nTRANSCRIPT:\n" + _transcript(turns, 16),
            cfg=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=VerifierResult,
                thinking_config=_thinking(),
            ),
            attempts=3,
        )
        result = VerifierResult.model_validate_json(response.text)
    except Exception:  # noqa: BLE001 - the call must continue if the verifier fails
        log.exception("verifier failed")
        return None
    return settle_verdict(result, " ".join(t["text"] for t in turns if t["speaker"] == "caller"))


async def build_strain(client, turns: list[dict], scam_type: str) -> dict | None:
    """Turn a finished call into a redacted strain card."""
    if not any(t["speaker"] == "caller" for t in turns):
        return None
    try:
        response = await flash(
            client,
            contents=STRAIN_PROMPT.format(taxonomy=", ".join(t for t in TAXONOMY if t not in NON_SCAM))
            + "\n\nTRANSCRIPT:\n" + _transcript(turns, 40),
            cfg=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=StrainCard,
                thinking_config=_thinking(),
            ),
            attempts=3,
        )
        card = StrainCard.model_validate_json(response.text)
    except Exception:  # noqa: BLE001
        log.exception("strain builder failed")
        return None
    flags = [f.strip() for f in card.red_flags if f.strip()][:3]
    flags += [f for f in DEFAULT_RED_FLAGS if f not in flags][: 3 - len(flags)]
    return {
        "scamType": card.scam_type if card.scam_type in TAXONOMY and card.scam_type not in NON_SCAM else scam_type,
        "impersonatedEntity": card.impersonated_entity,
        "steps": [s.strip() for s in card.steps if s.strip()][:6],
        "redFlags": flags,
        "paymentMethod": redact(card.payment_method),
        "scriptExcerpts": [redact(e) for e in card.script_excerpts][:3],
        "language": card.language,
    }


def build_evidence(call: dict, turns: list[dict], details: list[dict], strain: dict | None) -> dict:
    """Bank-ready evidence pack: confirmed and unconfirmed details with quotes, timestamps and confidence."""
    by_turn = {t["n"]: t for t in turns}

    def row(d: dict) -> dict:
        turn_ref = d["turns"][0] if d.get("turns") else None
        return {
            "type": d["type"],
            "value": d["normalizedValue"],
            "valid": d["valid"],
            "flags": d.get("flags", []),
            "confidence": d["confidence"],
            "confirmed": d["confirmed"],
            "detectedBy": d["sources"],
            "firstSeenSec": d.get("firstSeenSec"),
            "quote": d.get("evidence") or (by_turn.get(turn_ref, {}).get("text") if turn_ref else ""),
            "turnRefs": d.get("turns", []),
        }

    ordered = sorted(details, key=lambda d: (not d["confirmed"], d["type"]))
    return {
        "schema": "stallwart.evidence.v1",
        "generatedAt": now_iso(),
        "callId": call.get("callId"),
        "mode": call.get("mode"),
        "startedAt": call.get("startedAt"),
        "durationSec": call.get("durationSec"),
        "scamType": call.get("scamType"),
        "scamTypeConfidence": call.get("scamTypeConfidence"),
        "impersonatedEntity": call.get("impersonatedEntity"),
        "triggerPhrases": call.get("triggerPhrases", []),
        "confirmedDetails": [row(d) for d in ordered if d["confirmed"]],
        "unconfirmedDetails": [row(d) for d in ordered if not d["confirmed"]],
        "transcript": [
            {"turn": t["n"], "speaker": t["speaker"], "text": t["text"], "textEn": t.get("textEn"), "tSec": t.get("tSec")}
            for t in turns
        ],
        "strain": strain,
        "recordingAvailable": bool(call.get("recording")),
        "disclaimer": DISCLAIMER,
    }
