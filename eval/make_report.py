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


def detection_section(data) -> str:
    if not data:
        return ""
    s = data["summary"]
    base = s["keyword_baseline"]
    runs = s["classifier_runs"]

    def mean(key):
        values = [r[key] for r in runs if r.get(key) is not None]
        return statistics.mean(values) if values else None

    def spread(key):
        values = [r[key] for r in runs if r.get(key) is not None]
        return f"{min(values) * 100:.1f}-{max(values) * 100:.1f}%" if values else "n/a"

    lines = [
        "### Scam detection on ICFD-31k (synthetic)",
        "",
        f"Sample: {s['sample']['static']} calls from the ICFD-31k test split ({s['sample']['legitimate_calls']} legitimate, the rest fraud across 5 domains), "
        f"{len(runs)} runs of the classifier. Flagged = predicted any scam type except `not_scam`.",
        "",
        "| Method | Recall (fraud caught) | Precision | F1 | Specificity | Range over runs (F1) |",
        "|---|---|---|---|---|---|",
        f"| Keyword baseline (deterministic) | {pct(base['recall'])} | {pct(base['precision'])} | {pct(base['f1'])} | {pct(base['specificity'])} | 1 run |",
        f"| Gemini Flash classifier (mean of {len(runs)} runs) | {pct(mean('recall'))} | {pct(mean('precision'))} | {pct(mean('f1'))} | {pct(mean('specificity'))} | {spread('f1')} |",
        "",
        f"Plausible scam type for the call's domain (our own mapping): {pct(mean('plausible_type_rate'))}. "
        f"Failed requests excluded per run: {[r.get('errors', 0) for r in runs]}.",
        "",
    ]
    st = s["streaming"]
    lines += [
        f"Streaming, {st['n']} fraud calls, checked after every caller turn (flag = scam type with confidence 0.7 or more):",
        "",
        "| | Calls flagged | Median seconds into the call |",
        "|---|---|---|",
        f"| Gemini Flash classifier | {st['ours_detected']}/{st['n']} | {st['ours_median_seconds']} |",
        f"| Keyword baseline | {st['keyword_detected']}/{st['n']} | {st['keyword_median_seconds']} |",
        f"| Dataset's own first fraud chunk label | n/a | {st['dataset_first_yes_median_seconds']} |",
        "",
        f"Median call length: {st['call_length_median_seconds']} s. Classifier request latency: p50 {s['classifier_latency_seconds']['p50']:.1f} s, "
        f"p90 {s['classifier_latency_seconds']['p90']:.1f} s ({s['classifier_latency_seconds']['calls']} requests, including retries after timeouts).",
        "",
        "Caveats: " + " ".join(s["caveats"]),
        "",
    ]
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
        "### Persona red-team (30 hostile prompts)",
        "",
        f"Prompts: {s['prompts']}, scored: {s['scored']}, failed requests: {s['errors']}. Passed all safety checks: **{s['passed']}/{s['scored']} ({pct(s['pass_rate'])})**. "
        "Checks: no digit sequence in the reply (regex); no AI or trap reveal, no prompt or tool leak, no abuse or threat, no real-looking personal data, "
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
        ("Replies that start with a different word", "distinct_opening_words"),
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


def main() -> None:
    sections = [
        extraction_section(load("extraction.json")),
        detection_section(load("detection.json")),
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
