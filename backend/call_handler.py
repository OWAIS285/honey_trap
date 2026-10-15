"""Per-call state: turns, tool calls, verifier layer, confirmation rule, recording, strain, final summary."""

import asyncio
import json
import logging
import re
import secrets
import sys
import time

import analysis
from clients import text_client
from recorder import CallRecorder
from store import clean, owner_hash, store

log = logging.getLogger("stallwart.call")

_STAGE_DIRECTION = re.compile(r"\*[^*]*(\*|$)")


def strip_stage_directions(text: str) -> str:
    """Remove '*coughs*'-style narration (also a half-streamed one) and tidy the spaces."""
    return " ".join(_STAGE_DIRECTION.sub(" ", text).split())


def jlog(severity: str, message: str, **fields) -> None:
    """One JSON line per event so Cloud Logging indexes the fields (never transcript text or identifiers)."""
    print(json.dumps({"severity": severity, "message": message, **fields}), file=sys.stdout, flush=True)


class CallHandler:
    """Receives events from a LiveSession (voice) or TextSession (chat) and runs the analysis around them."""

    def __init__(self, *, client_id: str, ip: str, mode: str = "live") -> None:
        self.mode = mode
        self.call_id = secrets.token_hex(6)
        self.play_token = secrets.token_urlsafe(12)
        self.owner = owner_hash(client_id)
        self.ip = ip
        self.t0 = time.monotonic()
        self.started_at = analysis.now_iso()
        self.turns: list[dict] = []
        self.details: dict[str, dict] = {}
        self.classification = {
            "scamType": None,
            "confidence": 0.0,
            "triggerPhrases": [],
            "impersonatedEntity": "",
            "stage": None,
        }
        self.pending_caller = ""
        self.pending_persona = ""
        self.latencies: list[float] = []
        self.prompt_tokens = 0
        self.response_tokens = 0
        self.recorder = CallRecorder() if mode == "live" else None
        self.emit = None
        self.session = None
        self.end_requested = False
        self.end_reason: str | None = None
        self._verify_task: asyncio.Task | None = None
        self._verify_dirty = False
        self._verified_turns = 0
        self._bg: set[asyncio.Task] = set()
        self._finished = False

    def t(self) -> float:
        return round(time.monotonic() - self.t0, 1)

    def initial_doc(self) -> dict:
        return {
            "callId": self.call_id,
            "mode": self.mode,
            "ownerHash": self.owner,
            "playToken": self.play_token,
            "startedAt": self.started_at,
            "status": "live",
            "scamType": None,
            "scamTypeConfidence": 0.0,
            "currentStage": None,
        }

    async def _emit(self, event: dict) -> None:
        if self.emit:
            await self.emit(event)

    def _spawn(self, coro) -> None:
        task = asyncio.create_task(coro)
        self._bg.add(task)
        task.add_done_callback(self._bg.discard)

    # ----- hooks called by LiveSession / TextSession -----

    async def on_connected(self, session) -> None:
        self.session = session
        self.emit = session.send

    async def on_client_audio(self, pcm: bytes) -> None:
        if self.recorder:
            self.recorder.add_caller(pcm)

    async def on_typed_caller(self, text: str) -> None:
        await self._flush_caller()
        self.pending_caller = text
        await self._flush_caller()

    async def on_latency(self, ms: float) -> None:
        if 0 < ms < 15000:
            self.latencies.append(ms)
            jlog("INFO", "voice_latency", callId=self.call_id, ms=round(ms))
            await self._emit(
                {"type": "latency", "ms": round(ms), "p50": analysis.percentile(self.latencies, 50),
                 "p90": analysis.percentile(self.latencies, 90)}
            )

    async def on_usage(self, prompt: int, response: int) -> None:
        self.prompt_tokens = max(self.prompt_tokens, prompt)
        self.response_tokens = max(self.response_tokens, response)

    def add_usage(self, prompt: int, response: int) -> None:
        self.prompt_tokens += prompt
        self.response_tokens += response

    async def on_caller_text(self, fragment: str) -> None:
        self.pending_caller += fragment
        text = " ".join(self.pending_caller.split())
        foreign = analysis.needs_translation(text)
        await self._emit(
            {"type": "transcript", "speaker": "caller", "text": "" if foreign else text,
             "turn": len(self.turns) + 1, "final": False, "translating": foreign}
        )

    async def on_persona_text(self, fragment: str) -> None:
        if self.pending_caller:
            await self._flush_caller()
        self.pending_persona += fragment
        text = strip_stage_directions(self.pending_persona)
        foreign = analysis.needs_translation(text)
        await self._emit(
            {"type": "transcript", "speaker": "persona", "text": "" if foreign else text,
             "turn": len(self.turns) + 1, "final": False, "translating": foreign}
        )

    async def on_persona_audio(self, pcm: bytes) -> None:
        if self.pending_caller:
            await self._flush_caller()
        if self.recorder:
            self.recorder.add_persona(pcm)

    async def on_interrupted(self) -> None:
        if self.recorder:
            self.recorder.interrupted()
        await self._flush_persona()
        await self._emit({"type": "interrupted"})

    async def on_turn_complete(self) -> None:
        await self._flush_caller()
        await self._flush_persona()
        if self.end_requested and self.session is not None:
            self.session.stop(self.end_reason or "persona_ended")

    async def on_time_limit(self, session) -> None:
        await self._emit({"type": "time_limit"})

    async def on_tool_call(self, name: str, args: dict) -> dict:
        await self._flush_caller()
        if name == "record_detail":
            raw = str(args.get("raw_utterance") or "")
            value = str(args.get("value") or raw)
            detail = await self._upsert(str(args.get("detail_type", "")), value, "live_tool", quote=raw)
            if not detail:
                return {"result": "ignored"}
            return {"result": "recorded", "normalized": detail["normalizedValue"], "valid": detail["valid"]}
        if name == "flag_scam_stage":
            await self._set_stage(str(args.get("stage", "")))
            return {"result": "ok"}
        if name == "end_call":
            self.end_requested = True
            self.end_reason = str(args.get("reason") or "persona_ended")
            return {"result": "ok"}
        return {"result": "unknown_tool"}

    # ----- turns -----

    def _add_turn(self, speaker: str, text: str, persist: bool = True) -> dict:
        turn = {"n": len(self.turns) + 1, "speaker": speaker, "text": text, "tSec": self.t()}
        self.turns.append(turn)
        if persist:
            self._spawn(store.put(f"calls/{self.call_id}/turns/{turn['n']:04d}", turn))
        return turn

    async def _final_line(self, speaker: str, text: str) -> dict:
        """Record a finished turn; Hindi and Hinglish lines reach the screen in English, a moment later."""
        foreign = analysis.needs_translation(text)
        turn = self._add_turn(speaker, text, persist=not foreign)
        if foreign:
            self._spawn(self._translate_and_emit(turn))
        else:
            await self._emit(
                {"type": "transcript", "speaker": speaker, "text": text, "turn": turn["n"], "final": True,
                 "tSec": turn["tSec"]}
            )
        return turn

    async def _translate_and_emit(self, turn: dict) -> None:
        english = await analysis.to_english(text_client(), turn["text"])
        if english:
            turn["textEn"] = english
        await self._emit(
            {"type": "transcript", "speaker": turn["speaker"], "text": english or turn["text"], "turn": turn["n"],
             "final": True, "tSec": turn["tSec"]}
        )
        await store.put(f"calls/{self.call_id}/turns/{turn['n']:04d}", turn)

    async def _flush_caller(self) -> None:
        text = " ".join(self.pending_caller.split())
        self.pending_caller = ""
        if not text:
            return
        await self._final_line("caller", text)
        self._schedule_verify()

    async def _flush_persona(self) -> None:
        text = strip_stage_directions(self.pending_persona)
        self.pending_persona = ""
        if not text:
            return
        await self._final_line("persona", text)

    def _last_caller_turn(self) -> int | None:
        for turn in reversed(self.turns):
            if turn["speaker"] == "caller":
                return turn["n"]
        return None

    def _find_turn(self, quote: str) -> int | None:
        needle = " ".join(quote.lower().split())
        if needle:
            for turn in reversed(self.turns):
                if turn["speaker"] == "caller" and needle in " ".join(turn["text"].lower().split()):
                    return turn["n"]
        return self._last_caller_turn()

    # ----- details, stage, verifier -----

    async def _upsert(self, dtype: str, raw: str, source: str, quote: str = "", turn: int | None = None) -> dict | None:
        detail, changed = analysis.upsert_detail(
            self.details,
            dtype=dtype,
            raw=raw,
            source=source,
            turn=turn if turn is not None else self._last_caller_turn(),
            t_sec=self.t(),
            quote=quote,
        )
        if detail and changed:
            self._spawn(store.put(f"calls/{self.call_id}/details/{detail['id']}", detail))
            await self._emit({"type": "detail", "detail": detail})
        return detail

    async def _set_stage(self, stage: str) -> None:
        if stage not in analysis.STAGES:
            return
        self.classification["stage"] = stage
        await self._emit({"type": "stage", "stage": stage})

    def _schedule_verify(self) -> None:
        self._verify_dirty = True
        if self._verify_task is None or self._verify_task.done():
            self._verify_task = asyncio.create_task(self._verify_loop())

    async def _verify_loop(self) -> None:
        while self._verify_dirty:
            self._verify_dirty = False
            snapshot = list(self.turns)
            result = await analysis.verify(text_client(), snapshot)
            if result:
                await self._apply_verifier(result)
                self._verified_turns = len(snapshot)

    async def _apply_verifier(self, result: analysis.VerifierResult) -> None:
        for item in result.details:
            await self._upsert(item.type, item.value, "verifier", quote=item.raw_utterance,
                               turn=self._find_turn(item.raw_utterance or item.value))
        # A call that first looked harmless may turn into a scam once the caller actually speaks.
        current = self.classification
        stable = current["scamType"] == result.scam_type
        turned_scam = current["scamType"] == "not_scam" and result.scam_type != "not_scam"
        if current["scamType"] is None or stable or turned_scam or result.confidence > current["confidence"] + 0.02:
            current.update(
                scamType=result.scam_type,
                confidence=round(result.confidence, 2),
                triggerPhrases=result.trigger_phrases,
                impersonatedEntity=result.impersonated_entity,
            )
        if result.stage:
            current["stage"] = result.stage
        await self._emit({"type": "classification", **current})
        self._spawn(
            store.update(
                f"calls/{self.call_id}",
                {"scamType": current["scamType"], "scamTypeConfidence": current["confidence"],
                 "impersonatedEntity": current["impersonatedEntity"], "triggerPhrases": current["triggerPhrases"],
                 "currentStage": current["stage"]},
            )
        )

    # ----- end of call -----

    async def finish(self, reason: str) -> dict:
        if self._finished:
            return {}
        self._finished = True
        await self._flush_caller()
        await self._flush_persona()
        duration = round(time.monotonic() - self.t0, 1)

        # The strain card only needs the transcript, so build it while the verifier finishes.
        strain_task = asyncio.create_task(analysis.build_strain(text_client(), list(self.turns), "other_scam"))
        if self._verify_task:
            try:
                await asyncio.wait_for(self._verify_task, 25)
            except Exception:  # noqa: BLE001
                log.warning("verifier did not finish in time")
        if len(self.turns) > self._verified_turns:
            # Last word on classification: one pass over the whole call so late turns are never missed.
            try:
                final = await asyncio.wait_for(analysis.verify(text_client(), list(self.turns)), 20)
                if final:
                    await self._apply_verifier(final)
            except Exception:  # noqa: BLE001
                log.warning("final verification failed")

        recording = None
        if self.recorder and self.recorder.has_audio():
            wav = self.recorder.to_wav()
            path = await store.put_recording(self.call_id, wav)
            if path:
                recording = {"path": path, "bytes": len(wav), "durationSec": round(self.recorder.duration_sec(), 1)}

        strain = None
        try:
            card = await asyncio.wait_for(strain_task, 50)
        except Exception:  # noqa: BLE001
            log.warning("strain card was not ready in time")
            card = None
        if card:
            card["scamType"] = self.classification["scamType"] or card["scamType"]
            strain = {**card, "strainId": f"s{secrets.token_hex(5)}", "sourceCallId": self.call_id,
                      "createdAt": analysis.now_iso(), "ownerHash": self.owner}
            await store.put(f"strains/{strain['strainId']}", strain)

        if self._bg:
            await asyncio.gather(*self._bg, return_exceptions=True)

        p50, p90 = analysis.percentile(self.latencies, 50), analysis.percentile(self.latencies, 90)
        input_rate, output_rate = (0.75, 3.75) if self.mode == "text" else (0.75, 12.0)
        est_cost = round(self.prompt_tokens * input_rate / 1e6 + self.response_tokens * output_rate / 1e6, 4)
        confirmed = sum(1 for d in self.details.values() if d["confirmed"])
        summary = {
            "status": "ended",
            "endedAt": analysis.now_iso(),
            "durationSec": duration,
            "endReason": reason,
            "scamType": self.classification["scamType"],
            "scamTypeConfidence": self.classification["confidence"],
            "impersonatedEntity": self.classification["impersonatedEntity"],
            "triggerPhrases": self.classification["triggerPhrases"],
            "currentStage": self.classification["stage"],
            "latencyMsP50": p50,
            "latencyMsP90": p90,
            "latencyCount": len(self.latencies),
            "recording": recording,
            "strainId": strain["strainId"] if strain else None,
            "counts": {"turns": len(self.turns), "details": len(self.details), "confirmed": confirmed},
            "tokens": {"prompt": self.prompt_tokens, "response": self.response_tokens},
            "estCostUsd": est_cost,
        }
        await store.update(f"calls/{self.call_id}", summary)
        await self._emit(
            {"type": "ended", "reason": reason, "durationSec": duration, "recording": bool(recording),
             "strainId": summary["strainId"], "strain": clean(strain), "scamType": summary["scamType"],
             "counts": summary["counts"], "latency": {"p50": p50, "p90": p90}, "estCostUsd": est_cost}
        )
        jlog("INFO", "call_ended", callId=self.call_id, mode=self.mode, durationSec=duration, turns=len(self.turns),
             details=len(self.details), confirmed=confirmed, scamType=summary["scamType"], latencyP50=p50,
             latencyP90=p90, estCostUsd=est_cost, reason=reason)
        return summary
