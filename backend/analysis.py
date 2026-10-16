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

DISCLAIMER = (
    "Details were stated by an unverified caller during an automated decoy call and may be mis-heard or belong to "
    "an innocent third party. This pack is a lead for investigators, not a finding that any account is fraudulent."
)

DEFAULT_RED_FLAGS = [
    "The caller creates fear and urgency so you do not think.",
    "A real agency never asks for money or UPI transfers over a phone call.",
    "Hang up and call your family or the official number yourself.",
]


# What separates a scam from a genuine bank, lender, courier or government call is what the caller ASKS FOR, not
# what they talk about: real banks also mention loans, KYC, accounts and Aadhaar. Gemini only reports which of these
# behaviours it can quote from the caller; decide_verdict() turns them into a verdict with a fixed, testable rule.
HARD_FLAGS = {
    "asks_secret_credential": "Asks for an OTP, PIN, UPI PIN, CVV, card expiry, password or net-banking login",
    "remote_access_or_install": "Asks to install an app (AnyDesk, TeamViewer, QuickSupport, an APK) or share the screen",
    "pay_to_receive": "Wants a fee, deposit, charge or tax paid first to receive a loan, refund, prize, job or release, "
    "or asks to approve a UPI collect request or scan a QR code to receive money",
    "payment_to_personal_account": "Wants money sent to a personal UPI ID, an individual's account, gift cards or crypto "
    "instead of the organisation's own official channel",
    "arrest_or_legal_threat": "Threatens arrest, police, court, a warrant, a case or 'digital arrest' over the phone",
    "secrecy_or_isolation": "Tells the listener not to tell family or the bank, or to stay on the call or video",
    "extortion_threat": "Threatens to shame, expose or harm the listener unless they pay: sending their photos or "
    "messages to their contacts, telling their family or employer, or violence",
}
SOFT_FLAGS = {
    "urgency_deadline": "Pressure to act right now under threat of loss: account, card, SIM or power blocked today, a "
    "penalty or case within hours. A marketing offer that simply ends on a date is not this flag",
    "discourages_verification": "Refuses or talks the listener out of calling back on the official number, visiting "
    "the branch or office, or checking with family",
    "asks_full_identifier": "Asks the listener to read out a full account number, Aadhaar, PAN or card number",
    "link_or_unofficial_channel": "Sends or asks to open a link, a WhatsApp or SMS form, or gives a personal mobile "
    "number as an official line",
    "too_good_to_be_true": "A lottery the listener never entered, guaranteed or very high returns, a loan with no "
    "checks at all, or easy work that pays far too much. A bank's ordinary pre-approved offer is not this flag",
    "emotional_emergency": "A family member in trouble (accident, hospital, arrest) who needs money urgently",
    "identity_inconsistency": "The caller's name, organisation or story changes, or they cannot answer basic questions "
    "about it (for example, says they are the listener's bank but cannot say the last digits of the account)",
}
LEGIT_SIGNALS = {
    "offers_official_verification": "Invites or agrees to a callback on the official number (back of the card, "
    "passbook, website), a branch or office visit, or the official app",
    "partial_identifier_only": "Asks only for a partial detail (last 4 digits) or reads out what they already have "
    "for the listener to confirm",
    "official_channel_only": "Any payment or action goes only through the official app, branch, website or biller",
    "accepts_refusal": "Accepts 'no' or 'I will check myself' calmly, without pressure",
    "no_request": "Asks for no money, no details and no action (wrong number, family chat, a plain reminder or "
    "delivery notice)",
}
# Set by the call engine itself, never by Gemini: the caller correctly said the last four digits of one of the
# persona's own accounts, which a genuine bank has on screen and a cold-calling scammer usually does not.
RECORD_SIGNALS = {
    "knows_customer_record": "Correctly said the last four digits of the listener's own account, Aadhaar or card",
}
ALL_LEGIT = {**LEGIT_SIGNALS, **RECORD_SIGNALS}
RED_FLAGS = {**HARD_FLAGS, **SOFT_FLAGS}
VERDICTS = ["scam", "legitimate", "undetermined"]


class VerifierDetail(BaseModel):
    type: str = Field(description="One of: " + ", ".join(DETAIL_TYPES))
    value: str = Field(description="The detail written normally: digits as digits, UPI ID as name@handle.")
    raw_utterance: str = Field(description="The caller's exact words that contain the detail.")


class Evidence(BaseModel):
    signal: str = Field(description="The id of the red flag or legitimacy signal.")
    quote: str = Field(description="The CALLER's exact words that show it, copied verbatim.")


class VerifierExtraction(BaseModel):
    """What Gemini returns: observations with quotes. It never returns the verdict itself."""

    scam_type: str = Field(description="One of: " + ", ".join(TAXONOMY))
    impersonated_entity: str = Field(description="Organisation the caller claims to be, or an empty string.")
    stage: str = Field(description="One of: " + ", ".join(STAGES))
    red_flags: list[Evidence]
    legit_signals: list[Evidence]
    details: list[VerifierDetail]


class VerifierResult(BaseModel):
    """The verifier's output after the deterministic rule has been applied to one transcript window."""

    scam_type: str = Field(description="The pattern the call resembles; a label, never the verdict.")
    verdict: str = "undetermined"
    confidence: float = 0.0
    trigger_phrases: list[str] = []
    impersonated_entity: str = ""
    stage: str | None = None
    red_flags: list[Evidence] = []
    legit_signals: list[Evidence] = []
    details: list[VerifierDetail] = []


class StrainCard(BaseModel):
    scam_type: str
    impersonated_entity: str
    steps: list[str] = Field(description="3 to 6 short sentences describing the scammer's script in order.")
    red_flags: list[str] = Field(description="Exactly 3 plain-language warning signs of this script.")
    payment_method: str
    script_excerpts: list[str] = Field(description="2 or 3 short caller quotes with all identifiers replaced.")
    language: str = Field(description="english, hindi or hinglish")


def _catalogue(items: dict[str, str]) -> str:
    return "\n".join(f"  - {key}: {text}" for key, text in items.items())


VERIFIER_PROMPT = f"""You review a phone call between a CALLER and a PERSONA (an elderly man who picked up).
The CALLER is an unknown person. Most callers are ordinary (a wrong number, family, a genuine bank, lender, insurer,
courier, government office, shop or survey) and a few are scammers, so do not assume a scam.
Only the CALLER's words count as evidence. Do not judge by topic: genuine banks and lenders also call about loans,
KYC, accounts, cards and Aadhaar. A name, city, phone number, bank name or account number is never a red flag by
itself, and neither is one word such as 'bank', 'UPI' or 'police'. Report only behaviour the caller actually showed,
never what they might do later. A false scam alert on a genuine caller is a serious error.
Return JSON with:
- scam_type: the pattern this call resembles, one of {', '.join(TAXONOMY)}. Use not_scam when the call matches
  no scam pattern at all, undetermined when there is too little to tell. This is a label for the topic, not a verdict.
- impersonated_entity: the organisation the caller says they are from, or an empty string
- stage: one of {', '.join(STAGES)} (use hook if nothing risky has happened yet)
- red_flags: one entry per flag the CALLER clearly showed, each with signal (an id below) and quote (the caller's
  exact words, copied verbatim). Leave the list empty if none. Allowed ids:
{_catalogue(RED_FLAGS)}
- legit_signals: one entry per signal the CALLER clearly showed, same format. Allowed ids:
{_catalogue(LEGIT_SIGNALS)}
- details: every detail the CALLER stated. type is one of {', '.join(DETAIL_TYPES)}. value is the detail written
  normally (digits as digits, UPI ID as name@handle, spoken numbers converted). raw_utterance is the caller's exact
  words containing it.
Callers may speak English, Hindi (Devanagari or Roman letters) or a mix. Quotes keep the caller's own language."""

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


_QUOTE_TOKEN = re.compile(r"[\u0900-\u097F]+|[^\W_]+")


def _tokens(text: str) -> list[str]:
    return _QUOTE_TOKEN.findall(text.lower())


def grounded(quote: str, caller_text: str) -> bool:
    """A flag counts only if its quote is really in the caller's words (tolerates small transcription drift)."""
    words = _tokens(quote)
    if not words:
        return False
    if " ".join(words) in " ".join(_tokens(caller_text)):
        return True
    have = set(_tokens(caller_text))
    hits = sum(1 for w in words if w in have)
    return len(words) > 2 and hits / len(words) >= 0.7


def decide_verdict(red_flags, legit_signals, caller_turns: int, persona_not_scam: bool = False) -> tuple[str, float]:
    """The scam / legitimate / undetermined rule. Pure and deterministic so it can be unit-tested and explained.

    scam: any hard flag, or two different soft flags.
    legitimate: at least two caller turns, no hard flag, and either no soft flag with one legitimacy signal, or a
      single soft flag outweighed by two legitimacy signals.
    undetermined: everything else (including 'talks about loans or KYC but has asked for nothing risky yet').
    """
    red = set(red_flags)
    legit = set(legit_signals) & set(ALL_LEGIT)
    hard = red & set(HARD_FLAGS)
    soft = red & set(SOFT_FLAGS)
    if hard:
        return "scam", round(min(0.99, 0.85 + 0.05 * (len(hard) - 1) + 0.02 * len(soft)), 2)
    if len(soft) >= 2:
        return "scam", round(min(0.9, 0.55 + 0.1 * len(soft)), 2)
    if caller_turns >= 2 and ((not soft and legit) or (len(soft) == 1 and len(legit) >= 2)):
        return "legitimate", round(min(0.9, 0.55 + 0.1 * len(legit) - 0.15 * len(soft)), 2)
    if persona_not_scam and not soft:
        return "legitimate", 0.5
    return "undetermined", 0.0


def verdict_label(verdict: str, topic: str | None) -> str | None:
    """The scam-type label shown to users: the topic only once the behaviour says scam."""
    if verdict == "scam":
        return topic if topic in TAXONOMY and topic not in NON_SCAM else "other_scam"
    if verdict == "legitimate":
        return "not_scam"
    return "undetermined"


class VerdictState:
    """Evidence gathered over a whole call. Flags are never removed, so a call that starts genuine and later asks for
    an OTP still becomes a scam, while a topic on its own can never make one."""

    def __init__(self) -> None:
        self.red: dict[str, str] = {}
        self.legit: dict[str, str] = {}
        self.topic: str | None = None
        self.entity = ""
        self.stage: str | None = None
        self.persona_not_scam = False

    def merge(self, result: VerifierResult) -> None:
        for item in result.red_flags:
            self.red.setdefault(item.signal, item.quote)
        for item in result.legit_signals:
            self.legit.setdefault(item.signal, item.quote)
        if result.scam_type in TAXONOMY and (result.scam_type not in NON_SCAM or self.topic is None):
            self.topic = result.scam_type
        if result.impersonated_entity:
            self.entity = result.impersonated_entity
        if result.stage:
            self.stage = result.stage

    def summary(self, caller_turns: int) -> dict:
        verdict, confidence = decide_verdict(self.red, self.legit, caller_turns, self.persona_not_scam)
        return {
            "verdict": verdict,
            "scamType": verdict_label(verdict, self.topic),
            "topic": self.topic,
            "confidence": confidence,
            "triggerPhrases": list(dict.fromkeys(self.red.values()))[:4],
            "impersonatedEntity": self.entity,
            "stage": self.stage if verdict == "scam" else None,
            "redFlags": [
                {"signal": k, "label": RED_FLAGS[k], "severity": "hard" if k in HARD_FLAGS else "soft", "quote": q}
                for k, q in self.red.items()
            ],
            "legitSignals": [{"signal": k, "label": ALL_LEGIT[k], "quote": q} for k, q in self.legit.items()],
        }


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
                response_schema=VerifierExtraction,
                thinking_config=_thinking(),
            ),
            attempts=3,
        )
        raw = VerifierExtraction.model_validate_json(response.text)
    except Exception:  # noqa: BLE001 - the call must continue if the verifier fails
        log.exception("verifier failed")
        return None
    return finalize(raw, turns)


def finalize(raw: VerifierExtraction, turns: list[dict]) -> VerifierResult:
    """Keep only known, quoted signals and apply the decision rule to this window."""
    caller_turns = [t for t in turns if t["speaker"] == "caller"]
    caller_text = " ".join(t["text"] for t in caller_turns)

    def keep(items: list[Evidence], allowed: dict[str, str]) -> list[Evidence]:
        out: dict[str, Evidence] = {}
        for item in items:
            if item.signal in allowed and item.signal not in out and grounded(item.quote, caller_text):
                out[item.signal] = Evidence(signal=item.signal, quote=item.quote.strip())
        return list(out.values())

    red = keep(raw.red_flags, RED_FLAGS)
    legit = keep(raw.legit_signals, LEGIT_SIGNALS)
    verdict, confidence = decide_verdict([e.signal for e in red], [e.signal for e in legit], len(caller_turns))
    return VerifierResult(
        scam_type=raw.scam_type if raw.scam_type in TAXONOMY else "other_scam",
        verdict=verdict,
        confidence=confidence,
        trigger_phrases=list(dict.fromkeys(e.quote for e in red))[:4],
        impersonated_entity=raw.impersonated_entity,
        stage=raw.stage if raw.stage in STAGES else "hook",
        red_flags=red,
        legit_signals=legit,
        details=raw.details,
    )


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
        "verdict": call.get("verdict"),
        "redFlags": call.get("redFlags", []),
        "legitSignals": call.get("legitSignals", []),
        "recordChecks": call.get("recordChecks", []),
        "bankReports": call.get("bankReports", []),
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
