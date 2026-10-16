"""Stallwart's scam classifier on three more public benchmarks (all synthetic, all public on Hugging Face).

    python eval/benchmarks_eval.py --runs 1

  BothBosu/scam-dialogue (Apache-2.0): test split, 320 English phone calls, 160 scam (SSN, refund, tech support,
      reward) and 160 non-scam (delivery, insurance, telemarketing, wrong number). Llama-3-70B generated.
  BothBosu/multi-agent-scam-conversation (Apache-2.0): test split, 320 English calls between two AI agents with 8
      receiver personalities, 160 scam and 160 non-scam (appointment, delivery, insurance, wrong number).
  Ridham115/indian-scam-sms-synthetic-audited (CC-BY-4.0): SMS, not calls. A balanced random sample of
      --sms-per-language messages per language in Stallwart's languages (English, Hindi, Hinglish), half scam.
      Each message is treated as one line from the sender.

The classifier, the verdict rule and the 16-turn windows are exactly those of the live product (see detection_eval).
A call counts as flagged only when the verdict is scam; undetermined counts as not flagged. The keyword baseline from
detection_eval runs on every item. Datasets are downloaded into eval/datasets/ (git-ignored).
"""

import argparse
import asyncio
import csv
import io
import json
import pathlib
import random
import re
import statistics
import sys
import time
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "backend"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import analysis  # noqa: E402
from detection_eval import Scorer, keyword_flag, metrics  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
DATASETS = HERE / "datasets"
RESULTS = HERE / "results"
SOURCES = {
    "scam_dialogue": ("bothbosu_scam_dialogue_test.csv",
                      "https://huggingface.co/datasets/BothBosu/scam-dialogue/resolve/main/scam-dialogue_test.csv"),
    "multi_agent": ("bothbosu_multi_agent_test.csv",
                    "https://huggingface.co/datasets/BothBosu/multi-agent-scam-conversation/resolve/main/agent_conversation_test.csv"),
    "indian_sms": ("indian_scam_sms_audited.csv",
                   "https://huggingface.co/datasets/Ridham115/indian-scam-sms-synthetic-audited/resolve/main/data/synthetic_audited.csv"),
}
NAMES = {
    "scam_dialogue": "BothBosu scam-dialogue (test split, English calls)",
    "multi_agent": "BothBosu multi-agent-scam-conversation (test split, English calls)",
    "indian_sms": "Indian scam SMS, audited (English, Hindi, Hinglish messages)",
}
SPEAKERS = {"caller": "caller", "suspect": "caller", "receiver": "persona", "innocent": "persona"}
_TURN = re.compile(r"\b(caller|receiver|suspect|innocent)\s*:", re.IGNORECASE)


def read_csv(key: str) -> list[dict]:
    csv.field_size_limit(10**8)
    name, url = SOURCES[key]
    path = DATASETS / name
    if not path.exists():
        DATASETS.mkdir(exist_ok=True)
        path.write_bytes(urllib.request.urlopen(url, timeout=120).read())
    return list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8"))))


def to_turns(dialogue: str) -> list[dict]:
    parts = _TURN.split(dialogue)
    turns = []
    for speaker, text in zip(parts[1::2], parts[2::2]):
        text = " ".join(text.split())
        if text:
            turns.append({"speaker": SPEAKERS[speaker.lower()], "text": text, "t": 0})
    return turns


def load(key: str, sms_per_language: int, rng: random.Random) -> list[dict]:
    rows = read_csv(key)
    if key == "indian_sms":
        items = []
        for lang in ("en", "hi", "hinglish"):
            for label in ("scam", "safe"):
                pool = [r for r in rows if r["language"] == lang and r["label"] == label]
                rng.shuffle(pool)
                items += [{"id": r["row_id"], "fraud": label == "scam", "group": r["scam_type"] if label == "scam" else "safe",
                           "lang": lang, "turns": [{"speaker": "caller", "text": r["text"], "t": 0}]}
                          for r in pool[: sms_per_language // 2]]
        return items
    label = "labels" if "labels" in rows[0] else "label"
    return [{"id": f"{key}-{i}", "fraud": r[label] == "1", "group": r["type"], "lang": "en", "turns": to_turns(r["dialogue"])}
            for i, r in enumerate(rows)]


def breakdown(items: list[dict], flagged: dict[str, bool], field: str) -> dict:
    out = {}
    for value in sorted({i[field] for i in items}):
        group = [i for i in items if i[field] == value and i["id"] in flagged]
        right = sum(1 for i in group if flagged[i["id"]] == i["fraud"])
        out[value] = f"{right}/{len(group)}"
    return out


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--sets", default="scam_dialogue,multi_agent,indian_sms")
    parser.add_argument("--sms-per-language", type=int, default=100)
    parser.add_argument("--limit", type=int, default=0, help="first N items per set (smoke test; results not saved)")
    parser.add_argument("--concurrency", type=int, default=6)
    parser.add_argument("--seed", type=int, default=11)
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    rng = random.Random(args.seed)
    scorer = Scorer(args.concurrency)
    report = {}
    for key in [k.strip() for k in args.sets.split(",") if k.strip()]:
        items = load(key, args.sms_per_language, rng)
        if args.limit:
            items = items[: args.limit]
        baseline = metrics([(i["fraud"], keyword_flag(i["turns"])) for i in items])
        runs = []
        for run in range(args.runs):
            started = time.monotonic()
            rows = [{**i, "split": key, "domain": i["group"]} for i in items]
            out = await asyncio.gather(*[scorer.whole_call(r) for r in rows])
            ok = [o for o in out if not o["error"]]
            flagged = {o["id"]: o["verdict"] == "scam" for o in ok}
            m = metrics([(o["fraud"], flagged[o["id"]]) for o in ok])
            m["errors"] = len(out) - len(ok)
            m["non_scam_outcomes"] = {v: sum(1 for o in ok if not o["fraud"] and o["verdict"] == v)
                                      for v in ("scam", "legitimate", "undetermined")}
            m["correct_by_type"] = breakdown(items, flagged, "group")
            if key == "indian_sms":
                m["correct_by_language"] = breakdown(items, flagged, "lang")
            runs.append({"metrics": m, "predictions": out})
            print(f"{key} run {run + 1} ({time.monotonic() - started:.0f}s): recall {m['recall']} specificity "
                  f"{m['specificity']} precision {m['precision']} f1 {m['f1']} errors {m['errors']}", flush=True)
        means = {k: round(statistics.mean(r["metrics"][k] for r in runs), 3)
                 for k in ("recall", "specificity", "precision", "f1", "balanced_accuracy", "mcc")}
        report[key] = {
            "name": NAMES[key], "items": len(items), "scam": sum(i["fraud"] for i in items),
            "non_scam": sum(not i["fraud"] for i in items), "runs": len(runs), "mean": means,
            "f1_range": [min(r["metrics"]["f1"] for r in runs), max(r["metrics"]["f1"] for r in runs)],
            "run1": {k: v for k, v in runs[0]["metrics"].items()}, "keyword_baseline": baseline,
            "detail": runs,
        }
        print(f"{key} keyword baseline: recall {baseline['recall']} specificity {baseline['specificity']} f1 {baseline['f1']}",
              flush=True)

    summary = {
        "sets": {k: {kk: vv for kk, vv in v.items() if kk != "detail"} for k, v in report.items()},
        "classifier_latency_seconds": {"p50": analysis.percentile(scorer.latencies, 50),
                                       "p90": analysis.percentile(scorer.latencies, 90),
                                       "requests": scorer.requests, "failed_after_retries": scorer.failed},
        "caveats": [
            "All three sets are synthetic (LLM-generated); none measures real-world accuracy.",
            "The BothBosu sets are English and US-centred (SSN, IRS-style scams), so they test generalisation beyond India.",
            "The SMS set is text messages, not calls; each message is judged as a single line from the sender. Its "
            "labels were audited by an AI model with a small human spot check, as its card states.",
            "Undetermined counts as not flagged.",
        ],
    }
    if args.limit:
        print(json.dumps(summary["sets"], indent=1)[:3000])
        print("--limit was used, results not saved")
        return
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "benchmarks.json").write_text(json.dumps({"summary": summary, "detail": {k: v["detail"] for k, v in report.items()}},
                                                        ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1)[:4000])
    print("saved", RESULTS / "benchmarks.json")


if __name__ == "__main__":
    asyncio.run(main())
