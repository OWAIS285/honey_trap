"""Scam detection on ICFD-31k (synthetic Indian call transcripts): the product's classifier vs a keyword baseline.

ICFD-31k (Hugging Face rishia2220/icfd-31k, IJCAI-ECAI 2026) is licensed for defensive research and evaluation only.
It is used here to measure the classifier and never to build or tune the decoy persona or the drill scripts, and it is
not stored in this repository. Run `python eval/fetch_icfd.py` first.

    python eval/detection_eval.py --runs 3
    python eval/detection_eval.py --runs 1 --per-domain 4 --cross-per-domain 4 --stream-fraud-per-domain 1 --stream-legit 6

Data: the full TEST split (4,500 calls, 10 fraud domains, 23 non-fraud) and the CROSS-DOMAIN split (1,000 calls,
5 fraud types never seen in training, 39 non-fraud). ICFD labels whether the AGENT (the caller) commits fraud; its
non-fraud calls are mostly reverse scenarios where the agent stays honest while the customer tries a trick, so they
also test that only the caller is judged.

How the product is scored (the same code that runs on a live call):
  static     the call is read the way the product reads it, in 16-turn windows, quoted red flags accumulate, and the
             verdict rule decides (scam / legitimate / undetermined; undetermined counts as not flagged).
  streaming  re-checked after every caller turn; a non-fraud call shown as a scam at any point is a false alarm, and
             for fraud calls we record the seconds into the call of the first scam flag, next to ICFD's own label.
  baseline   a deterministic keyword filter, run on all 5,500 calls.
"""

import argparse
import ast
import asyncio
import json
import math
import pathlib
import random
import re
import statistics
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "backend"))

import analysis  # noqa: E402
from clients import text_client  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
DATASETS = HERE / "datasets"
FILES = {"test": ["test-00000-of-00002.jsonl", "test-00001-of-00002.jsonl"],
         "cross_domain": ["cross_domain-00000-of-00001.jsonl"]}
RESULTS = HERE / "results"
WINDOW = 16  # analysis.verify reads the last 16 turns of what it is given

# Our own judgement of which of our labels fit each ICFD test domain (cross-domain types are scored for detection only).
PLAUSIBLE = {
    "bank_payment_fraud": {"bank_kyc_block", "loan_app", "investment_trading", "fake_customer_care", "digital_arrest", "other_scam"},
    "utility_bill_service": {"electricity_bill", "telecom_trai_sim_block", "fake_customer_care", "other_scam"},
    "job_employment": {"task_job", "other_scam"},
    "loan_shark_harassment": {"loan_app", "other_scam"},
    "ecommerce_marketplace": {"fake_customer_care", "other_scam", "bank_kyc_block", "lottery_prize"},
    "government_impersonation": {"digital_arrest", "courier_parcel", "telecom_trai_sim_block", "bank_kyc_block", "other_scam"},
    "insurance_healthcare": {"fake_customer_care", "lottery_prize", "investment_trading", "family_emergency", "other_scam"},
    "personal_emergency_extortion": {"family_emergency", "digital_arrest", "loan_app", "other_scam"},
    "tech_support_account": {"fake_customer_care", "bank_kyc_block", "telecom_trai_sim_block", "other_scam"},
    "travel_lottery": {"lottery_prize", "fake_customer_care", "investment_trading", "other_scam"},
}

KEYWORDS = [
    r"\botp\b", r"processing fee", r"advance", r"\bupi\b", r"\bkyc\b", r"block", r"arrest", r"legal action", r"refund",
    r"\blink\b", r"anydesk|teamviewer|quicksupport", r"\bapk\b", r"gift", r"prize|lottery", r"registration fee",
    r"deposit", r"urgent|immediately|turant|abhi", r"disconnect|band ho", r"pay now|payment|bhejiye|bhejo",
    r"screenshot", r"\bqr\b|scan", r"daily income|commission|per day", r"recovery|vasooli", r"contacts|photos|gallery",
    r"police|court|warrant", r"password|pin\b", r"account number|bank details", r"sim card|sim swap|sim block",
]
KEYWORD_RE = [re.compile(k, re.IGNORECASE) for k in KEYWORDS]


def parse(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return ast.literal_eval(value)
    return value


def load_rows() -> list[dict]:
    rows = []
    for split, names in FILES.items():
        for name in names:
            path = DATASETS / name
            if not path.exists():
                sys.exit(f"missing {path}; run python eval/fetch_icfd.py")
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                r = json.loads(line)
                turns = [
                    {"speaker": "caller" if t["speaker"].lower().startswith("agent") else "persona", "text": t["text"],
                     "t": t.get("timestamp_end", 0)}
                    for t in parse(r["transcript"]) if t["speaker"].lower() in ("agent", "customer")
                ]
                chunks = parse(r.get("chunk_level_analysis")) or []
                meta = parse(r["release_metadata"])
                rows.append({
                    "id": meta["conversation_uid"], "split": split, "domain": meta["domain"],
                    "fraud": r["final_verdict"] == "YES", "turns": turns,
                    "gt_first_yes": next((c["timestamp"] for c in chunks if str(c.get("verdict_at_chunk")).upper() == "YES"), None),
                })
    return rows


def keyword_flag(turns: list[dict]) -> bool:
    text = " ".join(t["text"] for t in turns if t["speaker"] == "caller")
    return sum(1 for rx in KEYWORD_RE if rx.search(text)) >= 2


# ----- metrics -----


def wilson(k: float, n: float, z: float = 1.96) -> tuple[float, float] | None:
    if n <= 0:
        return None
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return round(max(0.0, centre - half), 3), round(min(1.0, centre + half), 3)


def metrics(pairs: list[tuple[bool, bool]]) -> dict:
    """pairs of (truth_is_fraud, predicted_fraud)."""
    tp = sum(1 for t, p in pairs if t and p)
    fp = sum(1 for t, p in pairs if not t and p)
    tn = sum(1 for t, p in pairs if not t and not p)
    fn = sum(1 for t, p in pairs if t and not p)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    specificity = tn / (tn + fp) if tn + fp else None
    denom = math.sqrt((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn))
    return {
        "n": len(pairs), "tp": tp, "fp": fp, "tn": tn, "fn": fn,
        "accuracy": round((tp + tn) / len(pairs), 3) if pairs else 0,
        "precision": round(precision, 3), "recall": round(recall, 3),
        "f1": round(2 * precision * recall / (precision + recall), 3) if precision + recall else 0.0,
        "specificity": round(specificity, 3) if specificity is not None else None,
        "false_positive_rate": round(1 - specificity, 3) if specificity is not None else None,
        "balanced_accuracy": round((recall + specificity) / 2, 3) if specificity is not None else None,
        "mcc": round((tp * tn - fp * fn) / denom, 3) if denom else 0.0,
        "recall_ci95": wilson(tp, tp + fn), "specificity_ci95": wilson(tn, tn + fp), "precision_ci95": wilson(tp, tp + fp),
    }


def median(values: list[float]):
    return round(statistics.median(values), 1) if values else None


# ----- the product's classifier -----


class Scorer:
    def __init__(self, concurrency: int) -> None:
        self.sem = asyncio.Semaphore(concurrency)
        self.latencies: list[float] = []
        self.requests = 0
        self.failed = 0

    async def verify(self, prefix: list[dict]):
        async with self.sem:
            started = time.monotonic()
            self.requests += 1
            result = await analysis.verify(text_client(), prefix)
            if result is None:
                self.failed += 1
            else:
                self.latencies.append(time.monotonic() - started)
            return result

    async def whole_call(self, row: dict) -> dict:
        """The product's verdict after reading the whole call in 16-turn windows."""
        turns = row["turns"]
        cuts = list(range(WINDOW, len(turns), WINDOW)) + [len(turns)]
        results = await asyncio.gather(*[self.verify(turns[:cut]) for cut in cuts])
        if all(r is None for r in results):
            return {"id": row["id"], "split": row["split"], "domain": row["domain"], "fraud": row["fraud"], "error": True}
        state = analysis.VerdictState()
        for r in results:
            if r is not None:
                state.merge(r)
        summary = state.summary(sum(1 for t in turns if t["speaker"] == "caller"))
        return {"id": row["id"], "split": row["split"], "domain": row["domain"], "fraud": row["fraud"], "error": False,
                "verdict": summary["verdict"], "type": summary["scamType"], "confidence": summary["confidence"],
                "red_flags": [f["signal"] for f in summary["redFlags"]], "windows": len(cuts)}

    async def streaming(self, row: dict) -> dict:
        state = analysis.VerdictState()
        first = None
        caller_turns = 0
        for i, turn in enumerate(row["turns"]):
            if turn["speaker"] != "caller":
                continue
            caller_turns += 1
            result = await self.verify(row["turns"][: i + 1])
            if result is not None:
                state.merge(result)
            if state.summary(caller_turns)["verdict"] == "scam":
                first = turn["t"]
                break
        end = row["turns"][-1]["t"] if row["turns"] else 0
        return {"id": row["id"], "split": row["split"], "domain": row["domain"], "fraud": row["fraud"], "flagged_at": first,
                "call_end": end, "dataset_first_yes": row["gt_first_yes"],
                "keyword_at": next((t["t"] for i, t in enumerate(row["turns"])
                                    if t["speaker"] == "caller" and keyword_flag(row["turns"][: i + 1])), None)}


def score_run(out: list[dict]) -> dict:
    ok = [o for o in out if not o["error"]]
    result = {"all": metrics([(o["fraud"], o["verdict"] == "scam") for o in ok]), "errors": len(out) - len(ok)}
    for split in FILES:
        part = [o for o in ok if o["split"] == split]
        result[split] = metrics([(o["fraud"], o["verdict"] == "scam") for o in part])
    result["recall_by_domain"] = {
        d: f"{sum(1 for o in ok if o['domain'] == d and o['fraud'] and o['verdict'] == 'scam')}/"
           f"{sum(1 for o in ok if o['domain'] == d and o['fraud'])}"
        for d in sorted({o["domain"] for o in ok})
    }
    plausible = [o["type"] in PLAUSIBLE[o["domain"]] for o in ok
                 if o["fraud"] and o["verdict"] == "scam" and o["domain"] in PLAUSIBLE]
    result["plausible_type_rate"] = round(sum(plausible) / len(plausible), 3) if plausible else None
    result["legit_outcomes"] = {v: sum(1 for o in ok if not o["fraud"] and o["verdict"] == v)
                                for v in ("scam", "legitimate", "undetermined")}
    return result


def mean_spread(runs: list[dict], part: str, key: str) -> dict:
    values = [r[part][key] for r in runs if r[part].get(key) is not None]
    if not values:
        return {"mean": None, "min": None, "max": None}
    return {"mean": round(statistics.mean(values), 3), "min": min(values), "max": max(values)}


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--per-domain", type=int, default=20, help="fraud calls per TEST domain (10 domains)")
    parser.add_argument("--cross-per-domain", type=int, default=20, help="fraud calls per CROSS-DOMAIN type (5)")
    parser.add_argument("--stream-fraud-per-domain", type=int, default=2)
    parser.add_argument("--stream-legit", type=int, default=62, help="non-fraud calls to stream (all = 62)")
    parser.add_argument("--concurrency", type=int, default=6)
    parser.add_argument("--seed", type=int, default=11)
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    rows = load_rows()
    rng = random.Random(args.seed)
    legit = [r for r in rows if not r["fraud"]]
    sample, stream_sample = list(legit), []
    for domain in sorted({r["domain"] for r in rows}):
        pool = [r for r in rows if r["fraud"] and r["domain"] == domain]
        rng.shuffle(pool)
        k = args.cross_per_domain if pool[0]["split"] == "cross_domain" else args.per_domain
        sample += pool[:k]
        stream_sample += pool[k : k + args.stream_fraud_per_domain]
    legit_stream = list(legit)
    rng.shuffle(legit_stream)
    stream_sample += legit_stream[: args.stream_legit]
    print(f"{len(rows)} calls loaded ({sum(not r['fraud'] for r in rows)} non-fraud); static sample {len(sample)} "
          f"({len(legit)} non-fraud), streaming sample {len(stream_sample)}", flush=True)

    baseline_full = {"all": metrics([(r["fraud"], keyword_flag(r["turns"])) for r in rows])}
    for split in FILES:
        baseline_full[split] = metrics([(r["fraud"], keyword_flag(r["turns"])) for r in rows if r["split"] == split])
    baseline_sample = metrics([(r["fraud"], keyword_flag(r["turns"])) for r in sample])
    print("keyword baseline, all calls:", {k: baseline_full["all"][k] for k in ("recall", "specificity", "f1")}, flush=True)

    scorer = Scorer(args.concurrency)
    runs = []
    for i in range(args.runs):
        started = time.monotonic()
        out = await asyncio.gather(*[scorer.whole_call(r) for r in sample])
        scored = score_run(out)
        runs.append({"metrics": scored, "predictions": out})
        m = scored["all"]
        print(f"run {i + 1} ({time.monotonic() - started:.0f}s): recall {m['recall']} specificity {m['specificity']} "
              f"precision {m['precision']} f1 {m['f1']} errors {scored['errors']} | non-fraud {scored['legit_outcomes']}",
              flush=True)

    started = time.monotonic()
    stream = await asyncio.gather(*[scorer.streaming(r) for r in stream_sample])
    fraud_stream = [s for s in stream if s["fraud"]]
    legit_streamed = [s for s in stream if not s["fraud"]]
    detected = [s for s in fraud_stream if s["flagged_at"] is not None]
    summary_stream = {
        "fraud_calls": len(fraud_stream),
        "fraud_flagged": len(detected),
        "median_seconds_to_flag": median([s["flagged_at"] for s in detected]),
        "median_share_of_call_at_flag": median([100 * s["flagged_at"] / s["call_end"] for s in detected if s["call_end"]]),
        "keyword_flagged": sum(1 for s in fraud_stream if s["keyword_at"] is not None),
        "keyword_median_seconds": median([s["keyword_at"] for s in fraud_stream if s["keyword_at"] is not None]),
        "dataset_first_yes_median_seconds": median([s["dataset_first_yes"] for s in fraud_stream if s["dataset_first_yes"] is not None]),
        "flagged_before_dataset_label": sum(1 for s in detected if s["dataset_first_yes"] is not None and s["flagged_at"] <= s["dataset_first_yes"]),
        "call_length_median_seconds": median([s["call_end"] for s in fraud_stream]),
        "non_fraud_calls": len(legit_streamed),
        "non_fraud_false_alarms": sum(1 for s in legit_streamed if s["flagged_at"] is not None),
        "keyword_non_fraud_false_alarms": sum(1 for s in legit_streamed if s["keyword_at"] is not None),
    }
    print(f"streaming ({time.monotonic() - started:.0f}s):", summary_stream, flush=True)

    sample_desc = {
        "static": len(sample), "static_fraud": sum(r["fraud"] for r in sample), "static_non_fraud": len(legit),
        "per_test_domain": args.per_domain, "per_cross_domain_type": args.cross_per_domain,
        "streaming": len(stream_sample), "seed": args.seed,
    }
    summary = {
        "dataset": "ICFD-31k (synthetic; evaluation only): full test split (4,500 calls) and cross-domain split (1,000 calls)",
        "population": {"calls": len(rows), "non_fraud": len(legit),
                       **{split: {"calls": sum(r["split"] == split for r in rows),
                                  "non_fraud": sum(r["split"] == split and not r["fraud"] for r in rows)} for split in FILES}},
        "sample": sample_desc,
        "keyword_baseline_all_calls": baseline_full,
        "keyword_baseline_sample": baseline_sample,
        "classifier_runs": [r["metrics"] for r in runs],
        "classifier_mean": {part: {k: mean_spread([r["metrics"] for r in runs], part, k)
                                   for k in ("recall", "specificity", "precision", "f1", "balanced_accuracy", "mcc")}
                            for part in ("all", *FILES)},
        "classifier_ci95_run1": {part: {k: runs[0]["metrics"][part][k] for k in ("recall_ci95", "specificity_ci95", "precision_ci95")}
                                 for part in ("all", *FILES)} if runs else {},
        "streaming": summary_stream,
        "classifier_latency_seconds": {"p50": analysis.percentile(scorer.latencies, 50),
                                       "p90": analysis.percentile(scorer.latencies, 90),
                                       "requests": scorer.requests, "failed_after_retries": scorer.failed},
        "caveats": [
            "ICFD-31k is synthetic (LLM-generated); numbers say nothing about real-world accuracy.",
            "Non-fraud calls are rare in ICFD (62 of 5,500), and most are reverse scenarios where the customer, not the "
            "agent, is the suspicious party; the specificity interval is therefore wide.",
            "Fraud calls are a stratified random sample (seed recorded); the keyword baseline is run on every call.",
            "Undetermined counts as not flagged. Plausible scam type uses our own domain-to-type mapping.",
        ],
    }
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "detection.json").write_text(
        json.dumps({"summary": summary, "runs": runs, "streaming": stream}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("classifier_mean", "classifier_ci95_run1", "classifier_latency_seconds")},
                     indent=1), flush=True)
    print("saved", RESULTS / "detection.json")


if __name__ == "__main__":
    asyncio.run(main())
