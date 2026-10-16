"""Turn eval/results/*.json into markdown tables and put them into README.md (between the EVAL markers).

    python eval/make_report.py
"""

import json
import pathlib
import statistics

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
RESULTS = HERE / "results"
REPLAYS = [ROOT / "frontend" / "public" / "replay" / name for name in ("replay-en.json", "replay-hi.json")]


def load(name: str):
    path = RESULTS / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def pct(value) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def _ci(pair) -> str:
    return f"{pair[0] * 100:.0f}-{pair[1] * 100:.0f}%" if pair else "n/a"


def detection_section(data) -> str:
    if not data:
        return ""
    s = data["summary"]
    if "classifier_mean" not in s:
        return ""
    sample, pop, runs = s["sample"], s["population"], s["classifier_runs"]
    mean, ci = s["classifier_mean"], s["classifier_ci95_run1"]
    kw = s["keyword_baseline_all_calls"]

    def row(label, part, kw_part):
        m = mean[part]
        k = kw[kw_part]
        return [
            f"| {label}: Stallwart (mean of {len(runs)} runs) | {pct(m['recall']['mean'])} ({_ci(ci[part]['recall_ci95'])}) | "
            f"{pct(m['specificity']['mean'])} ({_ci(ci[part]['specificity_ci95'])}) | {pct(m['precision']['mean'])} | "
            f"{pct(m['f1']['mean'])} | {pct(m['balanced_accuracy']['mean'])} | {m['mcc']['mean']} |",
            f"| {label}: keyword baseline (every call) | {pct(k['recall'])} | {pct(k['specificity'])} | {pct(k['precision'])} | "
            f"{pct(k['f1'])} | {pct(k['balanced_accuracy'])} | {k['mcc']} |",
        ]

    lines = [
        "### Scam detection on ICFD-31k (synthetic, IJCAI-ECAI 2026)",
        "",
        f"ICFD-31k test split ({pop['test']['calls']:,} calls, {pop['test']['non_fraud']} non-fraud) and cross-domain split "
        f"({pop['cross_domain']['calls']:,} calls of 5 fraud types never seen in training, {pop['cross_domain']['non_fraud']} non-fraud). "
        f"Stallwart was scored on every non-fraud call ({sample['static_non_fraud']}) and a stratified random sample of "
        f"{sample['static_fraud']} fraud calls ({sample['per_test_domain']} per test domain, {sample['per_cross_domain_type']} per "
        f"cross-domain type, seed {sample['seed']}), {len(runs)} runs; the keyword baseline was run on all "
        f"{pop['calls']:,} calls. The classifier reads each call the way the live product does (16-turn windows, quoted red "
        "flags accumulate, the verdict rule decides; undetermined counts as not flagged). No ICFD data was used to build or "
        "tune it. Brackets: 95% Wilson interval from run 1.",
        "",
        "| Split and method | Recall (fraud caught) | Specificity (non-fraud cleared) | Precision | F1 | Balanced accuracy | MCC |",
        "|---|---|---|---|---|---|---|",
        *row("Test + cross-domain", "all", "all"),
        *row("Test", "test", "test"),
        *row("Cross-domain (unseen types)", "cross_domain", "cross_domain"),
        "",
        f"F1 range over runs (all): {pct(mean['all']['f1']['min'])} to {pct(mean['all']['f1']['max'])}. "
        f"Plausible scam type for the test domain (our own mapping): {pct(runs[0].get('plausible_type_rate'))}. "
        f"Recall by domain, run 1: " + ", ".join(f"{d} {v}" for d, v in runs[0]["recall_by_domain"].items()) + ".",
        "",
        "Published ICFD-31k baselines (authors' release notes, test split, static task): fine-tuned RoBERTa F1 99.6%, "
        "zero-shot Gemma-2 F1 35.8%. Stallwart is not trained on ICFD at all, so the fair comparison is the zero-shot row.",
        "",
    ]
    st = s["streaming"]
    lat = s["classifier_latency_seconds"]
    lines += [
        f"Streaming (re-checked after every caller turn, as on a live call): {st['fraud_calls']} fraud calls and "
        f"{st['non_fraud_calls']} non-fraud calls.",
        "",
        "| | Fraud calls flagged | Median seconds to flag | Non-fraud calls ever flagged |",
        "|---|---|---|---|",
        f"| Stallwart | {st['fraud_flagged']}/{st['fraud_calls']} | {st['median_seconds_to_flag']} s "
        f"({st['median_share_of_call_at_flag']}% of the call) | {st['non_fraud_false_alarms']}/{st['non_fraud_calls']} |",
        f"| Keyword baseline | {st['keyword_flagged']}/{st['fraud_calls']} | {st['keyword_median_seconds']} s | "
        f"{st['keyword_non_fraud_false_alarms']}/{st['non_fraud_calls']} |",
        f"| ICFD's own first fraud chunk label | n/a | {st['dataset_first_yes_median_seconds']} s | n/a |",
        "",
        f"Median call length {st['call_length_median_seconds']} s. Flagged no later than ICFD's own first fraud label: "
        f"{st['flagged_before_dataset_label']}/{st['fraud_flagged']}. Classifier request latency p50 {lat['p50']:.1f} s, "
        f"p90 {lat['p90']:.1f} s ({lat['requests']} requests, {lat['failed_after_retries']} failed after retries).",
        "",
        "Caveats: " + " ".join(s["caveats"]),
        "",
    ]
    return "\n".join(lines)


def benchmarks_section(data) -> str:
    if not data:
        return ""
    s = data["summary"]
    lines = [
        "### Three more public benchmarks (synthetic, Hugging Face)",
        "",
        "Same classifier, same verdict rule, no tuning on any of these sets. Undetermined counts as not flagged; the "
        "keyword baseline is the same deterministic filter as above.",
        "",
        "| Benchmark | Items (scam / non-scam) | Method | Recall (scam caught) | Specificity (non-scam cleared) | Precision | F1 |",
        "|---|---|---|---|---|---|---|",
    ]
    for key, b in s["sets"].items():
        m, k, r1 = b["mean"], b["keyword_baseline"], b["run1"]
        lines += [
            f"| {b['name']} | {b['items']} ({b['scam']} / {b['non_scam']}) | Stallwart ({b['runs']} run{'s' if b['runs'] > 1 else ''}) | "
            f"{pct(m['recall'])} ({_ci(r1['recall_ci95'])}) | {pct(m['specificity'])} ({_ci(r1['specificity_ci95'])}) | "
            f"{pct(m['precision'])} | {pct(m['f1'])} |",
            f"| | | Keyword baseline | {pct(k['recall'])} | {pct(k['specificity'])} | {pct(k['precision'])} | {pct(k['f1'])} |",
        ]
    lines.append("")
    for key, b in s["sets"].items():
        detail = b["run1"].get("correct_by_language") or b["run1"]["correct_by_type"]
        label = "by language" if "correct_by_language" in b["run1"] else "by call type"
        lines.append(f"- {b['name']}, correct {label}: " + ", ".join(f"{k} {v}" for k, v in detail.items()) + ".")
    lat = s["classifier_latency_seconds"]
    lines += ["", f"Requests: {lat['requests']}, {lat['failed_after_retries']} failed after retries (excluded).", "",
              "Caveats: " + " ".join(s["caveats"]), ""]
    return "\n".join(lines)


def extraction_section(data) -> str:
    if not data:
        return ""
    core, hard = data["core"], data["hard"]
    return "\n".join(
        [
            "### Spoken-detail extraction (deterministic layer)",
            "",
            "Planted test: random, fictional identifiers rendered the way callers say them (English, Hinglish, Devanagari digits, "
            "'double', 'dot', 'at the rate', 'oh' for zero), run through the normaliser and validators that follow speech-to-text. "
            "It does **not** measure the speech recogniser. The core set matches the forms the normaliser was designed for, so a perfect score is expected; "
            "the hard set probes forms outside the first design (Devanagari letter names, spoken underscore and dash, 'triple').",
            "",
            "| Set | Cases | Correct | Accuracy | By type |",
            "|---|---|---|---|---|",
            f"| Core | {core['tests']} | {core['correct']} | {pct(core['accuracy'])} | {core['by_type']} |",
            f"| Hard | {hard['tests']} | {hard['correct']} | {pct(hard['accuracy'])} | {hard['by_type']} |",
            "",
        ]
    )


def redteam_section(data) -> str:
    if not data:
        return ""
    s = data["summary"]
    lines = [
        f"### Persona red-team ({s['prompts']} hostile prompts)",
        "",
        f"Prompts: {s['prompts']}, scored: {s['scored']}, failed requests: {s['errors']}. Passed all safety checks: **{s['passed']}/{s['scored']} ({pct(s['pass_rate'])})**. "
        "Checks: no run of four or more digits in the reply, written or spoken (regex; the persona never says any number of its own, not even the last four digits it uses to test a caller); no AI or trap reveal, no prompt or tool leak, no abuse or threat, no real-looking personal data, "
        "stays in character (judged by a second Gemini Flash call, not by a human). Single run, one reply per prompt.",
        "",
        "| Category | Passed |",
        "|---|---|",
    ]
    lines += [f"| {k} | {v} |" for k, v in s["by_category"].items()]
    if s["failures"]:
        lines += ["", "Failures:", ""]
        for f in s["failures"]:
            lines.append(f"- `{f['category']}` ({', '.join(f['problems'])}): {f['prompt'][:90]}")
    lines.append("")
    return "\n".join(lines)


def latency_section() -> str:
    values = [
        e["ms"]
        for path in REPLAYS
        if path.exists()
        for e in json.loads(path.read_text(encoding="utf-8"))["events"]
        if e.get("type") == "latency"
    ]
    if not values:
        return ""
    ordered = sorted(values)
    p90 = ordered[min(len(ordered) - 1, int(0.9 * len(ordered)))]
    return "\n".join(
        [
            "### Voice-to-voice latency (recorded replay call)",
            "",
            f"From the end of the caller's speech (measured in the client) to the first decoy audio: {len(values)} turns, "
            f"p50 {statistics.median(values) / 1000:.1f} s, p90 {p90 / 1000:.1f} s, range {min(values) / 1000:.1f} to {max(values) / 1000:.1f} s. "
            "Only a handful of samples from two calls, from India to a US-central voice model; not a benchmark.",
            "",
        ]
    )


def variety_section(old, new) -> str:
    if not old or not new:
        return ""
    rows = [
        ("Distinct opening words (out of all replies)", "distinct_opening_words"),
        ("Most common opening word", "most_common_opener"),
        ("Replies that open with a filler (arre, hmm, haan...)", "start_with_a_filler"),
        ("Replies containing 'arre'", "contain_arre"),
        ("Replies containing 'sahi hai'", "contain_sahi_hai"),
        ("Replies that end with a question", "end_with_a_question"),
        ("Words per reply", "words_per_reply"),
    ]
    lines = [
        "### Decoy variety (does it sound scripted?)",
        "",
        f"The same four-line English scam script run through the decoy {new['calls']} times (text mode, so wording and structure only, "
        "not the voice), before and after the persona was made dynamic. Lower filler and catchphrase rates and more distinct openings mean less repetition.",
        "",
        "| Measure | Before (fixed persona) | Now (per-call profile + director note) |",
        "|---|---|---|",
    ]
    lines += [f"| {label} | {old['metrics'][key]} | {new['metrics'][key]} |" for label, key in rows]
    lines += ["", "Single run per persona; replies lost to model timeouts are excluded.", ""]
    return "\n".join(lines)


def hard_negative_section(data) -> str:
    if not data:
        return ""
    s = data["summary"]
    names = {"keyword": "Keyword baseline", "legacy": "Previous verifier (topic-based)",
             "current": "Current verifier (quoted behaviour + rule)"}
    lines = [
        "### Scam or genuine? Same topic, both ways",
        "",
        f"{s['dataset']}: {s['legit_calls']} genuine calls (a bank's loan offer, KYC reminder, fraud alert, card upgrade, "
        f"courier, LIC agent, electricity board and more, plus wrong numbers and family) and {s['scam_calls']} scams on "
        "the same topics, in English, Hinglish and Hindi. A genuine call shown as a scam at any point while it is "
        "running counts as a streaming false alarm.",
        "",
        "| Method | Genuine flagged as scam | Genuine cleared | Scams caught | Both calls of a pair right | Streaming false alarms | Runs |",
        "|---|---|---|---|---|---|---|",
    ]
    for key, method in s["methods"].items():
        m = method["mean"]
        lines.append(
            f"| {names.get(key, key)} | {pct(m['false_positive_rate'])} | {pct(m['legit_cleared_rate'])} | "
            f"{pct(m['scam_recall'])} | {pct(m['pair_accuracy'])} | {pct(m.get('stream_false_alarm_rate'))} | {method['runs']} |"
        )
    lat = s["classifier_latency_seconds"]
    if lat.get("p50") is not None:
        lines += ["", f"Classifier request latency: p50 {lat['p50']:.1f} s, p90 {lat['p90']:.1f} s ({lat['calls']} requests)."]
    failed = {k: [r["metrics"]["failed_requests"] for r in v["per_run"]] for k, v in data["detail"].items()}
    lines += ["", f"Requests that failed after retries (excluded from the whole-call columns), per run: {failed}."]
    lines += ["", "Caveats: " + " ".join(s["caveats"]), ""]
    return "\n".join(lines)


def main() -> None:
    sections = [
        extraction_section(load("extraction.json")),
        detection_section(load("detection.json")),
        benchmarks_section(load("benchmarks.json")),
        hard_negative_section(load("hard_negatives.json")),
        redteam_section(load("redteam.json")),
        variety_section(load("variety-legacy.json"), load("variety-current.json")),
        latency_section(),
    ]
    body = "\n".join(s for s in sections if s).strip() + "\n"
    (RESULTS / "summary.md").write_text(body, encoding="utf-8")
    readme = ROOT / "README.md"
    text = readme.read_text(encoding="utf-8")
    start, end = "<!-- EVAL-START -->", "<!-- EVAL-END -->"
    head, rest = text.split(start, 1)
    _, tail = rest.split(end, 1)
    readme.write_text(f"{head}{start}\n{body}{end}{tail}", encoding="utf-8")
    print(body)


if __name__ == "__main__":
    main()
