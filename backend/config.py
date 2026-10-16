"""Runtime settings read from the environment (see .env.example)."""

import os

from dotenv import load_dotenv

load_dotenv()


def _flag(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes")


PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT", "").strip()
USE_VERTEX = _flag("GOOGLE_GENAI_USE_VERTEXAI", True)
LIVE_LOCATION = os.getenv("LIVE_LOCATION", "us-central1").strip()
TEXT_LOCATION = os.getenv("TEXT_LOCATION", "global").strip()
LIVE_MODEL = os.getenv("LIVE_MODEL", "gemini-3.8-live").strip()
FLASH_MODEL = os.getenv("FLASH_MODEL", "gemini-3.8-flash").strip()
TRANSLATE_MODEL = os.getenv("TRANSLATE_MODEL", "gemini-2.5-flash").strip()  # small and fast: transcript lines wait on it
PERSONA_VOICE = os.getenv("PERSONA_VOICE", "Achird").strip()
DRILL_VOICE = os.getenv("DRILL_VOICE", "Orus").strip()
LANGUAGE_CODE = os.getenv("LANGUAGE_CODE", "en-IN").strip()
# Higher = more varied wording from call to call; the persona prompt does the rest.
PERSONA_TEMPERATURE = float(os.getenv("PERSONA_TEMPERATURE", "1.1"))
# How long the caller must stay silent before the decoy answers. Lower = quicker replies, higher = fewer interruptions.
END_OF_SPEECH_MS = int(os.getenv("END_OF_SPEECH_MS", "450"))

ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]
KILL_SWITCH = _flag("KILL_SWITCH")
MAX_CALL_SECONDS = int(os.getenv("MAX_CALL_SECONDS", "300"))
MAX_DRILL_SECONDS = int(os.getenv("MAX_DRILL_SECONDS", "240"))
CALLS_PER_HOUR_PER_IP = int(os.getenv("CALLS_PER_HOUR_PER_IP", "10"))
MAX_CONCURRENT_SESSIONS = int(os.getenv("MAX_CONCURRENT_SESSIONS", "4"))
RETENTION_DAYS = int(os.getenv("RETENTION_DAYS", "14"))
RECORDINGS_BUCKET = os.getenv("RECORDINGS_BUCKET", "").strip() or f"{PROJECT}-recordings"

# Bank reports. "local" hands each signed report to the proxy bank receiver in-process; "http" POSTs it to
# {BANK_WEBHOOK_BASE}/proxy-banks/{code}/webhook, the way a real bank's webhook would be called.
BANK_DELIVERY = os.getenv("BANK_DELIVERY", "local").strip().lower()
BANK_WEBHOOK_BASE = os.getenv("BANK_WEBHOOK_BASE", "").strip().rstrip("/")
# Signs every report and derives each bank's API key. Keep it in Secret Manager; without it reports are signed with a
# per-process key and the bank API is switched off.
BANK_SIGNING_SECRET = os.getenv("BANK_SIGNING_SECRET", "").strip()
# Report a UPI ID or account to its bank at this confidence or more (this call plus every earlier call that gave it);
# from the watch level up it is kept and matched against future calls; below it, ignored.
BANK_REPORT_CONFIDENCE = float(os.getenv("BANK_REPORT_CONFIDENCE", "0.65"))
BANK_WATCH_CONFIDENCE = float(os.getenv("BANK_WATCH_CONFIDENCE", "0.45"))
