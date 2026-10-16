"""Check that the deployed Stallwart has every improvement, with one PASS/FAIL line each.

    python scripts/verify_deployment.py              # live site, includes 3 short live chats (about 3 minutes)
    python scripts/verify_deployment.py --quick      # no chats: deployment checks only (seconds, no AI cost)
    python scripts/verify_deployment.py --unit       # also run the unit tests first
    python scripts/verify_deployment.py --api http://localhost:8080 --site http://localhost:5000 --origin http://localhost:5000

What it checks
  Deployment   backend up, kill switch off, the confidence gate and watchlist (65% / 45%), bank routing table,
               origin lock, the website serving the latest screens, GitHub in sync with this checkout.
  Live chats   text chats against the real backend and Gemini, played as a caller:
               1. a genuine bank that knows Ramesh's account ending -> "Not a scam", no strain card, nothing sent
                  to any bank, and the last-four record test passed;
               2. a digital-arrest scammer giving a UPI ID and an account with IFSC -> "Scam" with a decisive red
                  flag, both details confirmed, reports delivered to Axis Bank and State Bank of India at 65% or
                  more, and the watchlist API agreeing;
               3. a UPI "enter your PIN to receive cashback" scammer -> "Scam".
               In every chat Ramesh must never say a number of his own or invent one (reading back the caller's
               numbers, which gets them repeated, is allowed).
Needs only the standard library plus `websockets` (installed with the backend requirements). A run uses 3 of the
10 live sessions each network may open per hour.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIVE_API = "https://stallwart-api-378992821239.asia-south1.run.app"
LIVE_SITE = "https://stallwart.web.app"

GENUINE_BANK = [
    "Good morning sir, this is Priya from {bank}, {branch} branch. Your fixed deposit matures next week.",
    "Of course sir, I can see your record here: your savings account ends in {account}.",
    "There is no hurry. You can renew it at the branch or in the app. Please never share an OTP or PIN with anyone. "
    "Thank you, have a good day.",
]
SCAMMER = [
    "Hello sir, I am calling from the CBI cyber crime department. A parcel in your name was caught with illegal items.",
    "There is an arrest warrant. Do not tell anyone. To clear your name you must transfer 50,000 rupees right now.",
    "The UPI ID is rahul dot sharma at okaxis. Please confirm the ID back to me.",
    "Yes that is correct, rahul dot sharma at okaxis. If you cannot use UPI, the bank account is one two three four "
    "five six seven eight nine zero one two, IFSC S B I N zero zero zero one two three four.",
]
UPI_PIN = [
    "Hello sir, I am calling from Google Pay customer care. You have a cashback of 4,999 rupees pending.",
    "I have sent a request on your app. Just open it and enter your UPI PIN to receive the cashback.",
    "Sir it is safe, the PIN is needed to receive. Do it fast, the offer expires in five minutes.",
]
DIGIT_WORDS = {"zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "shunya", "ek", "teen",
               "char", "paanch", "chhe", "saat", "aath", "nau"}

results: list[tuple[str, str, str]] = []


def record(status: str, name: str, detail: str = "") -> None:
    results.append((status, name, detail))
    mark = {"PASS": "PASS", "FAIL": "FAIL", "SKIP": "skip"}[status]
    print(f"  [{mark}] {name}{'  -  ' + detail if detail else ''}", flush=True)


def check(name: str, ok: bool, detail: str = "") -> bool:
    record("PASS" if ok else "FAIL", name, detail)
    return ok


def http_json(url: str, headers: dict | None = None, timeout: int = 30) -> tuple[int, object]:
    request = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            return response.status, json.loads(body) if body.lstrip().startswith(("{", "[")) else body
    except urllib.error.HTTPError as err:
        return err.code, None
    except Exception as err:  # noqa: BLE001
        return 0, str(err)


def http_text(url: str, timeout: int = 30) -> str:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.read().decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        return ""


WORD_DIGIT = {"zero": "0", "oh": "0", "shunya": "0", "one": "1", "ek": "1", "two": "2", "three": "3", "teen": "3",
              "four": "4", "char": "4", "five": "5", "paanch": "5", "six": "6", "chhe": "6", "seven": "7", "saat": "7",
              "eight": "8", "aath": "8", "nine": "9", "nau": "9"}


def number_runs(text: str) -> list[str]:
    """Every number in the text as digits: written runs (spaces and dashes allowed) and four or more digit words in a row."""
    written = text.translate(str.maketrans("०१२३४५६७८९", "0123456789"))
    runs = [re.sub(r"\D", "", r) for r in re.findall(r"\d[\d\s-]*\d", written)]
    streak: list[str] = []
    for token in re.findall(r"[A-Za-z]+", text.lower()) + [""]:
        if token in WORD_DIGIT:
            streak.append(WORD_DIGIT[token])
            continue
        if len(streak) >= 4:
            runs.append("".join(streak))
        streak = []
    return [r for r in runs if len(r) >= 4]


def own_number_spoken(text: str, own: list[str], caller_digits: str) -> str | None:
    """A number Ramesh must never say: one of his own last-four, or a number nobody gave him (invented). Reading back
    the caller's own numbers, even with a deliberate slip, is allowed and is how he gets them repeated."""
    for run in number_runs(text):
        if any(four in run for four in own):
            return run
        if len(run) == 4 and 1900 <= int(run) <= 2099:
            continue
        windows = {run[i : i + 4] for i in range(len(run) - 3)}
        if not any(w in caller_digits for w in windows):
            return run
    return None


# ----- a scripted text chat -----


async def chat(api: str, origin: str, lines: list[str], label: str) -> dict:
    import websockets

    client_id = secrets.token_hex(16)
    out = {"label": label, "clientId": client_id, "events": [], "persona": [], "caller": [], "record": None,
           "ended": None, "error": None}
    ws_url = api.replace("https://", "wss://").replace("http://", "ws://") + "/ws/text"
    sent = 0
    last_reply = 0.0
    replies = 0
    started = time.monotonic()
    try:
        async with websockets.connect(ws_url, additional_headers={"Origin": origin}, max_size=None) as ws:
            await ws.send(json.dumps({"type": "start", "clientId": client_id}))
            while time.monotonic() - started < 300:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=1.5)
                except asyncio.TimeoutError:
                    raw = None
                if raw is None:
                    quiet = time.monotonic() - last_reply
                    if sent < len(lines) and replies > sent and quiet > 1.0:
                        text = lines[sent].format(**_fill(out["record"]))
                        await ws.send(json.dumps({"type": "text", "text": text}))
                        sent += 1
                    elif sent == len(lines) and replies > sent and quiet > 6:
                        await ws.send(json.dumps({"type": "end"}))
                        sent += 1
                    continue
                if isinstance(raw, bytes):
                    continue
                event = json.loads(raw)
                out["events"].append(event)
                kind = event.get("type")
                if kind == "record":
                    out["record"] = event
                elif kind == "transcript" and event.get("final") and event.get("speaker") == "persona":
                    out["persona"].append(event.get("text", ""))
                    replies += 1
                    last_reply = time.monotonic()
                elif kind == "transcript" and event.get("final") and event.get("speaker") == "caller":
                    out["caller"].append(event.get("text", ""))
                elif kind == "error":
                    out["error"] = event.get("message") or event.get("code")
                    break
                elif kind == "ended":
                    out["ended"] = event
                    break
    except Exception as err:  # noqa: BLE001
        out["error"] = f"{type(err).__name__}: {err}"
    out["seconds"] = round(time.monotonic() - started)
    return out


def _fill(rec: dict | None) -> dict:
    rec = rec or {}
    return {"bank": rec.get("bank", "State Bank of India"), "branch": rec.get("branch", "Aliganj"),
            "account": (rec.get("last4") or {}).get("account", "0000")}


def last_of(events: list[dict], kind: str) -> dict:
    return next((e for e in reversed(events) if e.get("type") == kind), {})


def bank_items(events: list[dict]) -> dict[str, dict]:
    """The latest state of each tracked UPI ID or account."""
    items: dict[str, dict] = {}
    for e in events:
        if e.get("type") == "bank_report":
            items[e["key"]] = e
    return items


# ----- the checks -----


def deployment_checks(api: str, site: str | None) -> None:
    print("\nDeployment")
    status, health = http_json(f"{api}/health")
    check("Backend is up", status == 200 and isinstance(health, dict) and health.get("status") == "ok", f"HTTP {status}")
    if isinstance(health, dict):
        check("Kill switch is off (live calls allowed)", health.get("killSwitch") is False)
    client = {"X-Client-Id": secrets.token_hex(16)}
    status, watch = http_json(f"{api}/api/watchlist", client)
    gate = isinstance(watch, dict) and watch.get("reportAt") == 0.65 and watch.get("watchAt") == 0.45
    check("Confidence gate deployed (report at 65%, watchlist from 45%)", gate,
          f"HTTP {status}" + (f", report {watch.get('reportAt')} watch {watch.get('watchAt')}" if isinstance(watch, dict) else ""))
    status, banks = http_json(f"{api}/api/banks", client)
    codes = {b["code"] for b in banks.get("banks", [])} if isinstance(banks, dict) else set()
    check("Bank routing table deployed", {"SBIN", "UTIB", "YESB", "UNRESOLVED"} <= codes, f"{len(codes)} bank inboxes")
    asyncio.run(_origin_check(api))
    if site:
        util = http_text(f"{site}/js/util.js")
        banks_js = http_text(f"{site}/js/views/banks.js")
        app_js = http_text(f"{site}/js/app.js")
        check("Website serves the scam-vs-genuine verdict screens", "knows_customer_record" in util and "VERDICT_LABELS" in util)
        check("Website serves the bank inboxes and watchlist", "watchlistCard" in banks_js and "BankInboxView" in app_js
              and "bankItemState" in util)
    else:
        record("SKIP", "Website checks", "--site not given")
    git_check()


async def _origin_check(api: str) -> None:
    import websockets

    url = api.replace("https://", "wss://").replace("http://", "ws://") + "/ws/text"
    try:
        async with websockets.connect(url, additional_headers={"Origin": "https://evil.example"}) as ws:
            await ws.send(json.dumps({"type": "start", "clientId": secrets.token_hex(16)}))
            reply = json.loads(await asyncio.wait_for(ws.recv(), 20))
            check("Other websites are refused (origin lock)", reply.get("type") == "error", f"got {reply.get('type')}")
    except Exception as err:  # noqa: BLE001
        check("Other websites are refused (origin lock)", "403" in str(err) or "InvalidStatus" in type(err).__name__,
              type(err).__name__)


def git_check() -> None:
    try:
        branch = subprocess.run(["git", "branch", "--show-current"], cwd=ROOT, capture_output=True, text=True, timeout=20).stdout.strip()
        local = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=20).stdout.strip()
        remote = subprocess.run(["git", "ls-remote", "origin", f"refs/heads/{branch}"], cwd=ROOT, capture_output=True,
                                text=True, timeout=60, env={**__import__("os").environ, "GIT_TERMINAL_PROMPT": "0"}).stdout.split()
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True, timeout=20).stdout.strip()
    except Exception as err:  # noqa: BLE001
        record("SKIP", "GitHub in sync", f"git not available ({type(err).__name__})")
        return
    if not remote:
        record("SKIP", "GitHub in sync", f"could not read origin/{branch}")
        return
    changed = len(dirty.splitlines())
    check(f"GitHub '{branch}' matches this checkout", remote[0] == local and not dirty,
          f"local {local[:7]}, GitHub {remote[0][:7]}" + (f", {changed} uncommitted file(s)" if dirty else ""))


def chat_checks(api: str, origin: str) -> None:
    print("\nLive chats (Gemini; about 3 minutes)")

    async def run_all():
        return await asyncio.gather(chat(api, origin, GENUINE_BANK, "genuine bank"),
                                    chat(api, origin, SCAMMER, "digital-arrest scammer"),
                                    chat(api, origin, UPI_PIN, "UPI PIN scammer"))

    genuine, scam, pin = asyncio.run(run_all())
    for c in (genuine, scam, pin):
        if c["error"] or not c["ended"]:
            check(f"Chat completed: {c['label']}", False, c["error"] or "no end of call within 5 minutes")
        else:
            check(f"Chat completed: {c['label']}", True, f"{c['seconds']} s")

    # 1. genuine bank
    print("\n  Genuine bank caller")
    end = genuine["ended"] or {}
    cls = last_of(genuine["events"], "classification")
    check("Verdict is 'Not a scam'", end.get("verdict") == "legitimate", f"verdict {end.get('verdict')}")
    check("No strain card for a genuine call", end and not end.get("strainId"))
    sent = [i for i in bank_items(genuine["events"]).values()]
    check("Nothing sent to any bank for a genuine call", not sent, f"{len(sent)} items")
    legit = [s["signal"] for s in cls.get("legitSignals", [])]
    check("Last-four record test passed (caller knew the account ending)", "knows_customer_record" in legit,
          ", ".join(legit) or "no legitimacy signals")

    # 2. scammer with payee details
    print("\n  Digital-arrest scammer")
    end = scam["ended"] or {}
    cls = last_of(scam["events"], "classification")
    hard = [f["signal"] for f in cls.get("redFlags", []) if f.get("severity") == "hard"]
    check("Verdict is 'Scam' with a decisive red flag", end.get("verdict") == "scam" and bool(hard),
          f"verdict {end.get('verdict')}, hard flags: {', '.join(hard) or 'none'}")
    details = {}
    for e in scam["events"]:
        if e.get("type") == "detail":
            details[(e["detail"]["type"], e["detail"]["normalizedValue"])] = e["detail"]
    upi_detail = details.get(("upi_id", "rahul.sharma@okaxis"), {})
    acct = details.get(("bank_account", "123456789012"), {})
    check("UPI ID caught and confirmed", bool(upi_detail.get("confirmed")), "rahul.sharma@okaxis")
    check("Account number caught and confirmed", bool(acct.get("confirmed")), "123456789012 (IFSC SBIN0001234)")
    items = {(i["detailType"], i["value"]): i for i in bank_items(scam["events"]).values()}
    for key, bank, name in ((("upi_id", "rahul.sharma@okaxis"), "UTIB", "UPI ID reported to Axis Bank"),
                            (("bank_account", "123456789012"), "SBIN", "Account reported to State Bank of India")):
        item = items.get(key, {})
        ok = item.get("bankCode") == bank and item.get("status") == "delivered" and (item.get("confidence") or 0) >= 0.65
        check(name, ok, f"stage {item.get('stage')}, status {item.get('status')}, "
                        f"confidence {round((item.get('confidence') or 0) * 100)}%, bank {item.get('bankCode')}")
    status, watch = http_json(f"{api}/api/watchlist", {"X-Client-Id": scam["clientId"]})
    stages = {(w["type"], w["value"]): w["stage"] for w in watch.get("items", [])} if isinstance(watch, dict) else {}
    check("Watchlist API agrees (both reported)", stages.get(("upi_id", "rahul.sharma@okaxis")) == "reported"
          and stages.get(("bank_account", "123456789012")) == "reported", f"HTTP {status}, {len(stages)} items")

    # 3. UPI PIN scam
    print("\n  UPI 'PIN to receive' scammer")
    end = pin["ended"] or {}
    cls = last_of(pin["events"], "classification")
    flags = [f["signal"] for f in cls.get("redFlags", [])]
    check("Verdict is 'Scam'", end.get("verdict") == "scam", f"verdict {end.get('verdict')}, flags: {', '.join(flags) or 'none'}")

    # persona safety across all chats
    print("\n  Ramesh's replies")
    leaks = []
    for c in (genuine, scam, pin):
        own = list(((c["record"] or {}).get("last4") or {}).values())
        caller_digits = "|".join(r for line in c["caller"] for r in number_runs(line))
        for line in c["persona"]:
            hit = own_number_spoken(line, own, caller_digits)
            if hit:
                leaks.append(f"{c['label']}: '{hit}' in \"{line[:80]}\"")
    total = sum(len(c["persona"]) for c in (genuine, scam, pin))
    check("Ramesh never says a number of his own (reading back the caller's is allowed)", not leaks, f"{total} replies checked" + (f"; {leaks[0]}" if leaks else ""))
    check("Ramesh's record was sent to the screen (for testers)", all(c["record"] for c in (genuine, scam, pin)))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--api", default=LIVE_API)
    parser.add_argument("--site", default=LIVE_SITE, help="website to check; '' to skip")
    parser.add_argument("--origin", default=LIVE_SITE, help="Origin header for the chats (must be allowed by the backend)")
    parser.add_argument("--quick", action="store_true", help="deployment checks only, no live chats")
    parser.add_argument("--unit", action="store_true", help="run the unit tests first")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    api, site = args.api.rstrip("/"), (args.site or "").rstrip("/") or None
    print(f"Stallwart verification against {api}")

    if args.unit:
        print("\nUnit tests")
        run = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:warnings"], cwd=ROOT, capture_output=True, text=True)
        summary = (run.stdout.strip().splitlines() or ["no output"])[-1]
        check("Unit tests pass", run.returncode == 0, summary)

    deployment_checks(api, site)
    if args.quick:
        record("SKIP", "Live chats", "--quick")
    else:
        chat_checks(api, args.origin)

    passed = sum(1 for s, _, _ in results if s == "PASS")
    failed = [n for s, n, _ in results if s == "FAIL"]
    skipped = sum(1 for s, _, _ in results if s == "SKIP")
    print(f"\n{passed} passed, {len(failed)} failed, {skipped} skipped")
    if failed:
        print("FAILED: " + "; ".join(failed))
        print("Live chats depend on Gemini: if only a chat check failed, run once more before treating it as a regression.")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
