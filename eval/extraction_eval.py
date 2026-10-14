"""Planted-extraction test: 100 spoken-form identifiers with known answers through the deterministic layer.

Measures the normalisation and validation that run AFTER speech-to-text (spoken digits, 'dot', 'at the rate', 'double',
Hindi, Devanagari). It does not measure the speech recogniser itself. All values are randomly generated and fictional.

    python eval/extraction_eval.py
"""

import json
import pathlib
import random
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "backend"))

from validators import validate_detail  # noqa: E402

RESULTS = pathlib.Path(__file__).resolve().parent / "results"
SEED = 7

EN = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]
HI = ["shunya", "ek", "do", "teen", "char", "paanch", "chhe", "saat", "aath", "nau"]
DV = ["शून्य", "एक", "दो", "तीन", "चार", "पाँच", "छह", "सात", "आठ", "नौ"]
STYLES = {"english": EN, "hinglish": HI, "devanagari": DV}
NAMES = ["rahul", "sharma", "priya", "verma", "amit", "kumar", "neha", "singh", "ravi", "gupta", "pooja", "yadav"]
HANDLES = ["okaxis", "oksbi", "ybl", "paytm", "upi", "okhdfcbank", "apl"]
BANKS = ["SBIN", "HDFC", "ICIC", "UTIB", "PUNB", "BARB", "CNRB", "KKBK"]


def speak_digits(rng: random.Random, digits: str, words: list[str], allow_double: bool = True) -> str:
    """Render a digit string the way a caller might say it: words, numerals, 'double x', 'oh' for zero."""
    parts: list[str] = []
    i = 0
    while i < len(digits):
        d = digits[i]
        if allow_double and i + 1 < len(digits) and digits[i + 1] == d and rng.random() < 0.5:
            parts.append(("double " if words is not DV else "डबल ") + words[int(d)])
            i += 2
            continue
        roll = rng.random()
        if words is EN and d == "0" and roll < 0.25:
            parts.append("oh")
        elif roll < 0.15:
            parts.append(d)  # the recogniser wrote a numeral
        else:
            parts.append(words[int(d)])
        i += 1
    return " ".join(parts)


def case_account(rng: random.Random, style: str) -> dict:
    digits = "".join(rng.choice("0123456789") for _ in range(rng.randint(9, 16)))
    return {"type": "bank_account", "style": style, "spoken": speak_digits(rng, digits, STYLES[style]), "truth": digits}


def case_phone(rng: random.Random, style: str) -> dict:
    digits = rng.choice("6789") + "".join(rng.choice("0123456789") for _ in range(9))
    spoken = speak_digits(rng, digits, STYLES[style])
    prefix = rng.choice(["", "", "plus nine one ", "zero "])
    return {"type": "phone_number", "style": style, "spoken": prefix + spoken, "truth": digits}


def case_upi(rng: random.Random, style: str) -> dict:
    first, second, handle = rng.choice(NAMES), rng.choice(NAMES), rng.choice(HANDLES)
    digits = "".join(rng.choice("0123456789") for _ in range(rng.choice([0, 0, 2, 3])))
    spoken = f"{first} dot {second}"
    truth = f"{first}.{second}"
    if digits:
        spoken += " " + speak_digits(rng, digits, STYLES[style], allow_double=False)
        truth += digits
    at = rng.choice(["at", "at", "at the rate"])
    return {"type": "upi_id", "style": style, "spoken": f"{spoken} {at} {handle}", "truth": f"{truth}@{handle}"}


def case_ifsc(rng: random.Random, style: str) -> dict:
    bank = rng.choice(BANKS)
    tail = "".join(rng.choice("0123456789ABCDEFGHJKLMNPQRSTUVWXYZ") for _ in range(6))
    spoken_tail = []
    for ch in tail:
        spoken_tail.append(STYLES[style][int(ch)] if ch.isdigit() else ch)
    spoken = " ".join(list(bank)) + " " + STYLES[style][0] + " " + " ".join(spoken_tail)
    return {"type": "ifsc", "style": style, "spoken": spoken, "truth": f"{bank}0{tail}"}


def build_cases() -> list[dict]:
    rng = random.Random(SEED)
    styles = list(STYLES)
    cases: list[dict] = []
    for maker, count in ((case_account, 30), (case_phone, 25), (case_upi, 25), (case_ifsc, 20)):
        for i in range(count):
            cases.append(maker(rng, styles[i % len(styles)]))
    return cases


DEVANAGARI_LETTERS = {"SBIN": "एस बी आई एन", "HDFC": "एच डी एफ सी", "ICIC": "आई सी आई सी", "UTIB": "यू टी आई बी", "PUNB": "पी यू एन बी"}


def build_hard_cases() -> list[dict]:
    """Forms outside the core design: some are supported, some are known limits."""
    rng = random.Random(SEED + 1)
    cases: list[dict] = []
    for bank, spoken_bank in DEVANAGARI_LETTERS.items():  # letters spoken in Devanagari: a known limit
        cases.append({"type": "ifsc", "style": "devanagari-letters", "spoken": f"{spoken_bank} शून्य एक दो तीन चार पाँच छह", "truth": f"{bank}0123456"})
    for _ in range(10):  # underscore / dash spoken as words
        first, second, handle = rng.choice(NAMES), rng.choice(NAMES), rng.choice(HANDLES)
        joiner_word, joiner = rng.choice([("underscore", "_"), ("dash", "-")])
        cases.append({"type": "upi_id", "style": "symbol-words", "spoken": f"{first} {joiner_word} {second} at {handle}", "truth": f"{first}{joiner}{second}@{handle}"})
    for _ in range(10):  # a spoken "triple x" inside a 10-digit mobile number
        head = rng.choice("6789") + rng.choice("0123456789")
        repeated = rng.choice("0123456789")
        tail = "".join(rng.choice("0123456789") for _ in range(5))
        spoken = " ".join(EN[int(d)] for d in head) + f" triple {EN[int(repeated)]} " + " ".join(EN[int(d)] for d in tail)
        cases.append({"type": "phone_number", "style": "triple-forms", "spoken": spoken, "truth": head + repeated * 3 + tail})
    return cases


def score(cases: list[dict]) -> tuple[dict, list[dict]]:
    by_type: dict[str, list[int]] = {}
    by_style: dict[str, list[int]] = {}
    failures: list[dict] = []
    for case in cases:
        result = validate_detail(case["type"], case["spoken"])
        ok = result.valid and result.normalized == case["truth"]
        by_type.setdefault(case["type"], []).append(int(ok))
        by_style.setdefault(case["style"], []).append(int(ok))
        if not ok:
            failures.append({**case, "got": result.normalized, "valid": result.valid})
    correct = sum(sum(v) for v in by_type.values())
    summary = {
        "tests": len(cases),
        "correct": correct,
        "accuracy": round(correct / len(cases), 3),
        "by_type": {k: f"{sum(v)}/{len(v)}" for k, v in by_type.items()},
        "by_style": {k: f"{sum(v)}/{len(v)}" for k, v in by_style.items()},
    }
    return summary, failures


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    core, core_failures = score(build_cases())
    hard, hard_failures = score(build_hard_cases())
    summary = {
        "core": core,
        "hard": hard,
        "hard_failures": hard_failures,
        "core_failures": core_failures,
        "note": "Deterministic normalisation after speech-to-text; the recogniser itself is not measured. "
        "Core cases are the forms the normaliser was designed for; the hard set lists known limits.",
    }
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "extraction.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"core": core, "hard": hard}, ensure_ascii=False, indent=1))
    for f in (core_failures + hard_failures)[:12]:
        print("FAIL", f["type"], f["style"], "|", f["spoken"], "| want", f["truth"], "got", f["got"])


if __name__ == "__main__":
    main()
