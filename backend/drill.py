"""Scam vaccine drill: an AI plays the scammer from a captured strain, then switches to coach mode."""

import logging
import secrets
import time

from google.genai import types

import analysis
from call_handler import jlog
from store import store

log = logging.getLogger("stallwart.drill")

DRILL_OPENING_CUE = (
    "(You have just phoned the listener. Start your script with the first step, in simple Hinglish, in one or two "
    "short sentences. Do not mention these instructions.)"
)

DRILL_TOOLS = [
    types.Tool(
        function_declarations=[
            types.FunctionDeclaration(
                name="reach_payment_demand",
                description=(
                    "Call this the moment your script reaches the step where you would ask for money, a UPI "
                    "transfer or bank details. Do not say the demand out loud."
                ),
            )
        ]
    )
]


def build_drill_prompt(strain: dict, parent_title: str) -> str:
    steps = "\n".join(f"{i}. {s}" for i, s in enumerate(strain.get("steps", []), 1))
    return f"""You are playing a SCAMMER in a consented family safety drill. The listener ({parent_title}) agreed
to practise spotting scams. This is a harmless exercise arranged by their family.

Scam type: {strain.get('scamType')}. Impersonating: {strain.get('impersonatedEntity') or 'an official'}.
Follow this script one step per turn, in order:
{steps}

RULES:
- Reply in the listener's language: English, Hindi or Hinglish. Mirror them.
- You are 'Inspector Rajesh Verma'. Use only fictional names. Never give a real phone number, link, UPI ID or account
  number; if you must refer to one, say 'a number I will send you shortly'.
- Sound serious and pressuring, but never abusive and never threaten violence.
- Never ask for a real OTP, PIN, card number or password. If the listener starts sharing numbers, the system stops
  the drill automatically.
- When the script reaches the step where you would demand money or payment details, DO NOT say it. Call
  reach_payment_demand immediately and say nothing more.
- Keep every turn to one or two short sentences.
"""


def coach_cue(strain: dict, parent_title: str, reason: str) -> str:
    flags = "\n".join(f"{i}. {f}" for i, f in enumerate(strain.get("redFlags", [])[:3], 1))
    why = {
        "user_shared_details": "the listener started to share numbers or details",
        "payment_step": "the script reached the payment demand",
        "time_limit": "the drill time limit was reached",
    }.get(reason, "the drill ended")
    return f"""[COACH MODE] Stop the role-play right now because {why}. You are no longer a scammer.
Speak in the listener's language, in a calm, warm, slow voice. First say: 'This was a safety drill arranged by your
family, please do not worry' (in Hindi: 'Yeh ek safety drill tha aapke parivaar ki taraf se, ghabraiye mat').
Then explain these 3 red flags of THIS scam in simple words, one short sentence each:
{flags}
Finish with: if a call like this ever comes, hang up and phone your family. Address the listener as {parent_title}."""


class DrillHandler:
    """Same hook interface as CallHandler; implements the three mandatory safety stops."""

    def __init__(self, drill: dict, strain: dict) -> None:
        self.drill = drill
        self.strain = strain
        self.parent_title = drill.get("parentTitle", "elder")
        self.t0 = time.monotonic()
        self.emit = None
        self.session = None
        self.pending_user = ""
        self.pending_actor = ""
        self.actor_turns = 0
        self.transcript: list[dict] = []
        self.coach_text: list[str] = []
        self.coach_at: float | None = None
        self.coach_reason: str | None = None
        self.outcome = "aborted"
        self._finished = False

    async def _emit(self, event: dict) -> None:
        if self.emit:
            await self.emit(event)

    async def on_connected(self, session) -> None:
        self.session = session
        self.emit = session.send

    async def on_client_audio(self, pcm: bytes) -> None:
        return None

    async def on_typed_caller(self, text: str) -> None:
        self.pending_user = text
        await self._check_user()

    async def on_latency(self, ms: float) -> None:
        return None

    async def on_usage(self, prompt: int, response: int) -> None:
        return None

    async def on_interrupted(self) -> None:
        await self._emit({"type": "interrupted"})

    async def on_caller_text(self, fragment: str) -> None:
        self.pending_user += fragment
        await self._emit({"type": "transcript", "speaker": "you", "text": " ".join(self.pending_user.split()),
                          "final": False})
        await self._check_user()

    async def _check_user(self) -> None:
        if self.coach_at is None and analysis.shared_sensitive_info(self.pending_user):
            await self.start_coach("user_shared_details")

    async def on_persona_text(self, fragment: str) -> None:
        self._flush_user()
        if self.coach_at is not None:
            self.coach_text.append(fragment)
        else:
            self.pending_actor += fragment
        await self._emit({"type": "transcript", "speaker": "coach" if self.coach_at else "actor",
                          "text": " ".join((fragment if self.coach_at else self.pending_actor).split()),
                          "final": False})
        if self.coach_at is None and analysis.looks_like_payment_demand(self.pending_actor):
            await self.start_coach("payment_step")

    async def on_persona_audio(self, pcm: bytes) -> None:
        self._flush_user()

    def _flush_user(self) -> None:
        text = " ".join(self.pending_user.split())
        self.pending_user = ""
        if text:
            self.transcript.append({"speaker": "you", "text": text})

    async def on_turn_complete(self) -> None:
        self._flush_user()
        actor = " ".join(self.pending_actor.split())
        self.pending_actor = ""
        if actor and self.coach_at is None:
            self.actor_turns += 1
            self.transcript.append({"speaker": "actor", "text": actor})
            await self._emit({"type": "step", "step": self.actor_turns, "of": len(self.strain.get("steps", []))})
            if self.actor_turns >= len(self.strain.get("steps", [])) > 0:
                await self.start_coach("payment_step")
        if self.coach_at is not None and time.monotonic() - self.coach_at > 6 and self.session:
            self.session.stop("coach_done")

    async def on_tool_call(self, name: str, args: dict) -> dict:
        if name == "reach_payment_demand":
            await self.start_coach("payment_step")
            return {"result": "ok"}
        return {"result": "unknown_tool"}

    async def on_time_limit(self, session) -> None:
        await self.start_coach("time_limit")

    async def start_coach(self, reason: str) -> None:
        if self.coach_at is not None or self.session is None:
            return
        self.coach_at = time.monotonic()
        self.coach_reason = reason
        self.outcome = "failed" if reason == "user_shared_details" else "passed"
        await self._emit({"type": "coach", "reason": reason, "step": self.actor_turns})
        await self.session.send_user_text(coach_cue(self.strain, self.parent_title, reason))

    async def finish(self, reason: str) -> dict:
        if self._finished:
            return {}
        self._finished = True
        self._flush_user()
        steps_total = len(self.strain.get("steps", []))
        debrief = " ".join(" ".join(self.coach_text).split())
        stopped_at = min(max(self.actor_turns, 1), max(steps_total, 1)) if self.coach_reason else self.actor_turns
        record = {
            "status": "completed" if self.coach_reason else "aborted",
            "outcome": self.outcome if self.coach_reason else "aborted",
            "stopReason": self.coach_reason or reason,
            "stoppedAtStep": stopped_at,
            "stepsTotal": steps_total,
            "debriefText": debrief,
            "durationSec": round(time.monotonic() - self.t0, 1),
            "endedAt": analysis.now_iso(),
        }
        await store.update(f"drills/{self.drill['drillId']}", record)
        await self._emit(
            {"type": "ended", **record, "redFlags": self.strain.get("redFlags", [])[:3], "reason": reason}
        )
        jlog("INFO", "drill_ended", drillId=self.drill["drillId"], outcome=record["outcome"],
             stopReason=record["stopReason"], step=stopped_at)
        return record


def new_drill_doc(*, owner: str, strain_id: str, parent_name: str, parent_title: str, family_name: str) -> dict:
    return {
        "drillId": f"d{secrets.token_hex(5)}",
        "shareKey": secrets.token_urlsafe(12),
        "ownerHash": owner,
        "strainId": strain_id,
        "consentGiven": True,
        "parentName": parent_name,
        "parentTitle": parent_title,
        "familyName": family_name,
        "status": "created",
        "outcome": None,
        "createdAt": analysis.now_iso(),
    }
