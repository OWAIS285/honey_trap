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
PERSONA_VOICE = os.getenv("PERSONA_VOICE", "Achird").strip()
DRILL_VOICE = os.getenv("DRILL_VOICE", "Orus").strip()
LANGUAGE_CODE = os.getenv("LANGUAGE_CODE", "en-IN").strip()
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
