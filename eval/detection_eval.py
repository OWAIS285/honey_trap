"""Scam detection on ICFD-31k (synthetic Indian call transcripts): the product's classifier vs a keyword baseline.

ICFD-31k is licensed for defensive research and evaluation only. It is used here to measure the classifier and never
to build or tune the decoy persona or the family-drill scripts. Run `python eval/fetch_icfd.py` first.

    python eval/detection_eval.py --runs 3 --static-per-domain 28 --stream-per-domain 8

What is measured (all on the SYNTHETIC test split, which is 99.5% fraud, so specificity rests on only 12 legitimate calls):
  1. static: is the whole call flagged as a scam (verdict == scam from the deterministic rule over Gemini's quoted
     red flags; undetermined counts as not flagged)?
  2. plausible type: does the predicted scam type fit the call's ICFD domain (mapping below is ours)?
  3. streaming: after how many seconds of the call does the classifier flag it, compared with the dataset's own
     chunk labels?
"""

import argparse
import ast
import asyncio
import json
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
DATA = HERE / "datasets" / "test-00000-of-00002.jsonl"
RESULTS = HERE / "results"

PLAUSIBLE = {
    "bank_payment_fraud": {"bank_kyc_block", "loan_app", "investment_trading", "fake_customer_care", "digital_arrest", "other_scam"},
    "utility_bill_service": {"electricity_bill", "telecom_trai_sim_block", "fake_customer_care", "other_scam"},
    "job_employment": {"task_job", "other_scam"},
    "loan_shark_harassment": {"loan_app", "other_scam"},
    "ecommerce_marketplace": {"fake_customer_care", "other_scam", "bank_kyc_block", "lottery_prize"},
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
    for line in DATA.read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        turns = [
            {"speaker": "caller" if t["speaker"].lower().startswith("agent") else "persona", "text": t["text"], "t": t.get("timestamp_end", 0)}
            for t in parse(r["transcript"])
        ]
        chunks = parse(r.get("chunk_level_analysis")) or []
        first_yes = next((c["timestamp"] for c in chunks if str(c.get("verdict_at_chunk")).upper() == "YES"), None)
        rows.append(
            {
                "id": parse(r["release_metadata"])["conversation_uid"],
                "domain": parse(r["release_metadata"])["domain"],
                "fraud": r["final_verdict"] == "YES",
                "turns": turns,
                "gt_first_yes": first_yes,
            }
        )
    return rows


def keyword_flag(turns: list[dict]) -> bool:
    text = " ".join(t["text"] for t in turns if t["speaker"] == "caller")
    return sum(1 for rx in KEYWORD_RE if rx.search(text)) >= 2


def metrics(pairs: list[tuple[bool, bool]]) -> dict:
    """pairs of (truth_is_fraud, predicted_fraud)."""
    tp = sum(1 for t, p in pairs if t and p)
    fp = sum(1 for t, p in pairs if not t and p)
    tn = sum(1 for t, p in pairs if not t and not p)
    fn = sum(1 for t, p in pairs if t and not p)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return {
        "n": len(pairs), "tp": tp, "fp": fp, "tn": tn, "fn": fn,
        "accuracy": round((tp + tn) / len(pairs), 3) if pairs else 0,
        "precision": round(precision, 3), "recall": round(recall, 3),
        "f1": round(2 * precision * recall / (precision + recall), 3) if precision + recall else 0.0,
        "specificity": round(tn / (tn + fp), 3) if tn + fp else None,
    }


async def classify(turns: list[dict], sem: asyncio.Semaphore, latencies: list[float]):
    async with sem:
        started = time.monotonic()
        result = await analysis.verify(text_client(), turns)
        if result is not None:
            latencies.append(time.monotonic() - started)
        return result


async def static_run(sample: list[dict], sem: asyncio.Semaphore, latencies: list[float]) -> list[dict]:
    results = await asyncio.gather(*[classify(r["turns"], sem, latencies) for r in sample])
    return [
        {"id": r["id"], "domain": r["domain"], "fraud": r["fraud"], "error": res is None,
         "verdict": res.verdict if res else None,
         "type": analysis.verdict_label(res.verdict, res.scam_type) if res else None,
         "confidence": res.confidence if res else None}
        for r, res in zip(sample, results)
    ]


async def streaming_run(sample: list[dict], sem: asyncio.Semaphore, latencies: list[float]) -> list[dict]:
    async def one(row: dict) -> dict:
        end = row["turns"][-1]["t"] if row["turns"] else 0
        found = None
        kw_found = None
        state = analysis.VerdictState()
        for i, turn in enumerate(row["turns"]):
            if turn["speaker"] != "caller":
                continue
            prefix = row["turns"][: i + 1]
            if kw_found is None and keyword_flag(prefix):
                kw_found = turn["t"]
            if found is None:
                res = await classify(prefix, sem, latencies)
                if res:
                    state.merge(res)
                if state.summary(sum(1 for t in prefix if t["speaker"] == "caller"))["verdict"] == "scam":
                    found = turn["t"]
            if found is not None and kw_found is not None:
                break
        return {"id": row["id"], "domain": row["domain"], "call_end": end, "ours": found, "keyword": kw_found, "dataset_first_yes": row["gt_first_yes"]}

    return await asyncio.gather(*[one(r) for r in sample])


def median(values: list[float]):
    return round(statistics.median(values), 1) if values else None


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--static-per-domain", type=int, default=28)
    parser.add_argument("--stream-per-domain", type=int, default=8)
    parser.add_argument("--concurrency", type=int, default=3)
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    rows = load_rows()
    rng = random.Random(11)
    negatives = [r for r in rows if not r["fraud"]]
    positives = [r for r in rows if r["fraud"]]
    sample: list[dict] = list(negatives)
    stream_sample: list[dict] = []
    for domain in PLAUSIBLE:
        pool = [r for r in positives if r["domain"] == domain]
        rng.shuffle(pool)
        sample += pool[: args.static_per_domain]
        stream_sample += pool[args.static_per_domain : args.static_per_domain + args.stream_per_domain]
    print(f"static sample {len(sample)} ({len(negatives)} legitimate), streaming sample {len(stream_sample)}")

    sem = asyncio.Semaphore(args.concurrency)
    latencies: list[float] = []

    baseline = metrics([(r["fraud"], keyword_flag(r["turns"])) for r in sample])
    print("keyword baseline", baseline)

    runs = []
    for i in range(args.runs):
        out = await static_run(sample, sem, latencies)
        ok = [o for o in out if not o["error"]]
        m = metrics([(o["fraud"], o["verdict"] == "scam") for o in ok])
        plausible = [o["type"] in PLAUSIBLE[o["domain"]] for o in ok if o["fraud"] and o["verdict"] == "scam"]
        m["errors"] = len(out) - len(ok)
        m["undetermined"] = sum(1 for o in ok if o["verdict"] == "undetermined")
        m["plausible_type_rate"] = round(sum(plausible) / len(plausible), 3) if plausible else None
        runs.append({"metrics": m, "predictions": out})
        print(f"run {i + 1}", m)

    stream = await streaming_run(stream_sample, sem, latencies)
    detected = [s for s in stream if s["ours"] is not None]
    summary_stream = {
        "n": len(stream),
        "ours_detected": len(detected),
        "keyword_detected": sum(1 for s in stream if s["keyword"] is not None),
        "ours_median_seconds": median([s["ours"] for s in detected]),
        "keyword_median_seconds": median([s["keyword"] for s in stream if s["keyword"] is not None]),
        "dataset_first_yes_median_seconds": median([s["dataset_first_yes"] for s in stream if s["dataset_first_yes"] is not None]),
        "call_length_median_seconds": median([s["call_end"] for s in stream]),
    }
    print("streaming", summary_stream)

    f1s = [r["metrics"]["f1"] for r in runs]
    recalls = [r["metrics"]["recall"] for r in runs]
    summary = {
        "dataset": "ICFD-31k test split, shard 0 (synthetic; evaluation only)",
        "sample": {"static": len(sample), "legitimate_calls": len(negatives), "streaming": len(stream_sample)},
        "keyword_baseline": baseline,
        "classifier_runs": [r["metrics"] for r in runs],
        "classifier_f1_mean": round(statistics.mean(f1s), 3) if f1s else None,
        "classifier_recall_mean": round(statistics.mean(recalls), 3) if recalls else None,
        "streaming": summary_stream,
        "classifier_latency_seconds": {"p50": analysis.percentile(latencies, 50), "p90": analysis.percentile(latencies, 90), "calls": len(latencies)},
        "caveats": [
            "ICFD-31k is synthetic; numbers say nothing about real-world accuracy.",
            "The test split has only 12 legitimate calls in this shard, so specificity is very uncertain.",
            "The domain to scam-type mapping used for plausible_type_rate is our own judgement.",
        ],
    }
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "detection.json").write_text(json.dumps({"summary": summary, "runs": runs, "streaming": stream}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    asyncio.run(main())
