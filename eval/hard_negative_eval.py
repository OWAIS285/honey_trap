"""Scam or genuine? Paired hard-negative test: the same topic as a genuine call and as a scam.

Genuine banks, lenders, couriers and offices also call about loans, KYC, accounts and Aadhaar, so a classifier that
judges by topic flags them. This eval measures exactly that, on hand-written fictional calls in English, Hinglish and
Hindi (eval/fixtures/hard_negatives.json), for three methods:

  keyword   the deterministic keyword baseline from detection_eval.py
  legacy    the previous verifier prompt ("a suspected scammer", flag = any scam type except not_scam), copied here
            unchanged so the before-and-after comparison is measured, not remembered
  current   analysis.verify(): Gemini reports quoted red flags and legitimacy signals, decide_verdict() decides

Static = one verdict on the whole call. Streaming = re-checked after every caller turn, the way the live dashboard
works; a genuine call that is EVER shown as a scam counts as a false alarm.

    python eval/hard_negative_eval.py --runs 3
    python eval/hard_negative_eval.py --runs 1 --methods current --limit 6     # quick check

Needs Application Default Credentials (or GOOGLE_GENAI_USE_VERTEXAI=false with GOOGLE_API_KEY).
"""

import argparse
import asyncio
import json
import pathlib
import statistics
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "backend"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from google.genai import types  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

import analysis  # noqa: E402
from clients import flash, text_client  # noqa: E402
from detection_eval import keyword_flag  # noqa: E402
from persona import DETAIL_TYPES, STAGES  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures" / "hard_negatives.json"
RESULTS = HERE / "results"

# The verifier prompt as it was before the verdict rule, kept verbatim for the baseline.
LEGACY_PROMPT = f"""You analyse a phone call between a CALLER (a suspected scammer) and a PERSONA (a decoy elderly man).
Only the CALLER's words count as evidence.
Return JSON with:
- scam_type: one of {', '.join(analysis.TAXONOMY)}
- confidence: 0 to 1
- trigger_phrases: up to 4 short phrases copied EXACTLY from the CALLER's words that show the scam type
- impersonated_entity: the organisation the caller claims to be, or an empty string
- stage: the current stage, one of {', '.join(STAGES)}
- details: every detail the CALLER stated. type is one of {', '.join(DETAIL_TYPES)}. value is the detail written
  normally (digits as digits, UPI ID as name@handle, spoken numbers converted). raw_utterance is the caller's exact
  words containing it.
Callers may speak English, Hindi (Devanagari or Roman letters) or a mix. If nothing is stated, return an empty list."""


class LegacyResult(BaseModel):
    scam_type: str = Field(description="One of: " + ", ".join(analysis.TAXONOMY))
    confidence: float = Field(description="0 to 1")
    trigger_phrases: list[str]
    impersonated_entity: str
    stage: str
    details: list[analysis.VerifierDetail]


def load_calls() -> list[dict]:
    data = json.loads(FIXTURES.read_text(encoding="utf-8"))
    calls = []
    for c in data["calls"]:
        calls.append({**c, "turns": [{"speaker": s, "text": t} for s, t in c["turns"]]})
    return calls


def caller_prefixes(turns: list[dict]) -> list[list[dict]]:
    """The transcript as it stands after each caller turn."""
    return [turns[: i + 1] for i, t in enumerate(turns) if t["speaker"] == "caller"]


# ----- methods: each returns "scam" | "legitimate" | "undetermined" (None on a failed request) -----


class Method:
    name = ""

    async def static(self, turns):
        raise NotImplementedError

    async def stream(self, turns) -> list[str | None]:
        raise NotImplementedError


class Keyword(Method):
    name = "keyword"

    async def static(self, turns):
        return {"verdict": "scam" if keyword_flag(turns) else "legitimate"}

    async def stream(self, turns):
        return ["scam" if keyword_flag(p) else "legitimate" for p in caller_prefixes(turns)]


class Gemini(Method):
    def __init__(self, sem: asyncio.Semaphore, latencies: list[float]) -> None:
        self.sem = sem
        self.latencies = latencies

    async def timed(self, coro):
        async with self.sem:
            started = time.monotonic()
            out = await coro
            if out is not None:
                self.latencies.append(time.monotonic() - started)
            return out


class Legacy(Gemini):
    name = "legacy"

    async def _one(self, turns):
        try:
            response = await flash(
                text_client(),
                contents=LEGACY_PROMPT + "\n\nTRANSCRIPT:\n" + analysis._transcript(turns, 10),
                cfg=types.GenerateContentConfig(response_mime_type="application/json", response_schema=LegacyResult,
                                                thinking_config=analysis._thinking()),
                attempts=3,
            )
            return LegacyResult.model_validate_json(response.text)
        except Exception as exc:  # noqa: BLE001
            print(f"  legacy request failed: {type(exc).__name__}")
            return None

    async def static(self, turns):
        res = await self.timed(self._one(turns))
        if res is None:
            return None
        return {"verdict": "scam" if res.scam_type != "not_scam" else "legitimate", "type": res.scam_type,
                "confidence": res.confidence}

    async def stream(self, turns):
        # The old dashboard showed any scam type other than not_scam as a scam the moment it arrived.
        out = []
        for prefix in caller_prefixes(turns):
            res = await self.timed(self._one(prefix))
            out.append(None if res is None else ("scam" if res.scam_type != "not_scam" else "legitimate"))
        return out


class Current(Gemini):
    name = "current"

    async def static(self, turns):
        res = await self.timed(analysis.verify(text_client(), turns))
        if res is None:
            return None
        return {"verdict": res.verdict, "type": analysis.verdict_label(res.verdict, res.scam_type),
                "confidence": res.confidence,
                "redFlags": [[e.signal, e.quote] for e in res.red_flags],
                "legitSignals": [[e.signal, e.quote] for e in res.legit_signals]}

    async def stream(self, turns):
        state = analysis.VerdictState()
        out = []
        for prefix in caller_prefixes(turns):
            res = await self.timed(analysis.verify(text_client(), prefix))
            if res is not None:
                state.merge(res)
            out.append(state.summary(sum(1 for t in prefix if t["speaker"] == "caller"))["verdict"])
        return out


# ----- scoring -----


def score(calls: list[dict], static: dict[str, dict | None], stream: dict[str, list] | None) -> dict:
    legit = [c for c in calls if c["label"] == "legitimate"]
    scams = [c for c in calls if c["label"] == "scam"]
    ok = {cid: r for cid, r in static.items() if r is not None}

    def rate(items, pred):
        vals = [pred(ok[c["id"]]) for c in items if c["id"] in ok]
        return round(sum(vals) / len(vals), 3) if vals else None

    pairs: dict[str, list[dict]] = {}
    for c in calls:
        if c.get("pair"):
            pairs.setdefault(c["pair"], []).append(c)
    pair_hits = [
        all(ok[c["id"]]["verdict"] == ("scam" if c["label"] == "scam" else "legitimate") for c in group)
        for group in pairs.values() if all(c["id"] in ok for c in group)
    ]
    out = {
        "legit_calls": len(legit),
        "scam_calls": len(scams),
        "failed_requests": len(static) - len(ok),
        "false_positive_rate": rate(legit, lambda r: r["verdict"] == "scam"),
        "legit_cleared_rate": rate(legit, lambda r: r["verdict"] == "legitimate"),
        "legit_undetermined_rate": rate(legit, lambda r: r["verdict"] == "undetermined"),
        "scam_recall": rate(scams, lambda r: r["verdict"] == "scam"),
        "pair_accuracy": round(sum(pair_hits) / len(pair_hits), 3) if pair_hits else None,
        "pairs": len(pair_hits),
        "false_positives": sorted(c["id"] for c in legit if c["id"] in ok and ok[c["id"]]["verdict"] == "scam"),
        "missed_scams": sorted(c["id"] for c in scams if c["id"] in ok and ok[c["id"]]["verdict"] != "scam"),
    }
    by_lang = {}
    for lang in sorted({c["lang"] for c in calls}):
        group = [c for c in calls if c["lang"] == lang and c["id"] in ok]
        right = sum(1 for c in group if ok[c["id"]]["verdict"] == ("scam" if c["label"] == "scam" else "legitimate"))
        by_lang[lang] = f"{right}/{len(group)}"
    out["correct_by_language"] = by_lang
    if stream is not None:
        alarms = [c["id"] for c in legit if "scam" in [v for v in stream.get(c["id"], []) if v]]
        caught, delays, early = 0, [], []
        for c in scams:
            seq = stream.get(c["id"], [])
            first = next((i + 1 for i, v in enumerate(seq) if v == "scam"), None)
            if first is not None:
                caught += 1
                start = c.get("scam_from_turn")
                if start:
                    if first < start:
                        early.append(c["id"])
                    else:
                        delays.append(first - start)
        out["stream_false_alarm_rate"] = round(len(alarms) / len(legit), 3) if legit else None
        out["stream_false_alarms"] = sorted(alarms)
        out["stream_scam_recall"] = round(caught / len(scams), 3) if scams else None
        out["late_turn_flagged_before_scam_began"] = early
        out["late_turn_extra_turns_to_flag"] = delays
    return out


async def run_method(method: Method, calls: list[dict], streaming: bool) -> dict:
    static_results = await asyncio.gather(*[method.static(c["turns"]) for c in calls])
    static = {c["id"]: r for c, r in zip(calls, static_results)}
    stream = None
    if streaming:
        stream_results = await asyncio.gather(*[method.stream(c["turns"]) for c in calls])
        stream = {c["id"]: r for c, r in zip(calls, stream_results)}
    return {"metrics": score(calls, static, stream), "static": static, "stream": stream}


def mean_of(runs: list[dict], key: str):
    values = [r["metrics"][key] for r in runs if r["metrics"].get(key) is not None]
    return round(statistics.mean(values), 3) if values else None


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--methods", default="keyword,legacy,current")
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--no-stream", action="store_true")
    parser.add_argument("--limit", type=int, default=0, help="only the first N calls (smoke test)")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    calls = load_calls()
    if args.limit:
        calls = calls[: args.limit]
    sem = asyncio.Semaphore(args.concurrency)
    latencies: list[float] = []
    available = {"keyword": Keyword(), "legacy": Legacy(sem, latencies), "current": Current(sem, latencies)}
    chosen = [available[m.strip()] for m in args.methods.split(",") if m.strip()]
    print(f"{len(calls)} calls: {sum(c['label'] == 'legitimate' for c in calls)} genuine, "
          f"{sum(c['label'] == 'scam' for c in calls)} scam")

    report: dict[str, dict] = {}
    for method in chosen:
        n_runs = 1 if method.name == "keyword" else args.runs
        runs = []
        for i in range(n_runs):
            result = await run_method(method, calls, not args.no_stream)
            runs.append(result)
            m = result["metrics"]
            print(f"{method.name} run {i + 1}: FPR {m['false_positive_rate']} recall {m['scam_recall']} "
                  f"pairs {m['pair_accuracy']} stream-alarms {m.get('stream_false_alarm_rate')} "
                  f"FP {m['false_positives']} missed {m['missed_scams']}")
        keys = ["false_positive_rate", "legit_cleared_rate", "legit_undetermined_rate", "scam_recall", "pair_accuracy",
                "stream_false_alarm_rate", "stream_scam_recall"]
        report[method.name] = {
            "runs": len(runs),
            "mean": {k: mean_of(runs, k) for k in keys},
            "range": {k: [min(v), max(v)] for k in keys
                      if (v := [r["metrics"][k] for r in runs if r["metrics"].get(k) is not None])},
            "per_run": runs,
        }

    summary = {
        "dataset": f"{FIXTURES.name}: {len(calls)} hand-written fictional calls (pairs, late-turn scams, benign)",
        "legit_calls": sum(c["label"] == "legitimate" for c in calls),
        "scam_calls": sum(c["label"] == "scam" for c in calls),
        "methods": {name: {"runs": r["runs"], "mean": r["mean"], "range": r["range"]} for name, r in report.items()},
        "classifier_latency_seconds": {"p50": analysis.percentile(latencies, 50),
                                       "p90": analysis.percentile(latencies, 90), "calls": len(latencies)},
        "caveats": [
            "Hand-written by the team, so the calls are cleaner than real speech-to-text and the scams are clear-cut.",
            "Small set: one wrong call moves a rate by several points.",
            "Streaming re-checks after each caller turn on the full prefix; the live product also adds the persona's "
            "own end_call(not_scam) as a tie-breaker, which is not exercised here.",
        ],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    if args.limit:
        print("--limit was used, results not saved")
        return
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "hard_negatives.json").write_text(
        json.dumps({"summary": summary, "detail": report}, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"saved {RESULTS / 'hard_negatives.json'}")


if __name__ == "__main__":
    asyncio.run(main())
