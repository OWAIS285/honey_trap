"""How repetitive is the decoy? Runs the same scammer script through the persona many times and counts habits.

    python eval/variety_eval.py --runs 8                # current persona
    python eval/variety_eval.py --runs 8 --legacy       # the pre-variation persona, read from git history

Text mode only (Flash), so it measures wording and structure, not the voice. Needs Application Default Credentials.
"""

import argparse
import asyncio
import importlib.util
import json
import pathlib
import re
import statistics
import subprocess
import sys
import tempfile
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

from google.genai import types  # noqa: E402

import analysis  # noqa: E402
import config  # noqa: E402
from clients import flash, text_client  # noqa: E402
from persona import OPENING_CUE, PERSONA_TOOLS, CallProfile, build_persona_text, turn_note  # noqa: E402
from sim_call import LINES  # noqa: E402

LEGACY_REV = "838fdbc"  # last commit before the persona was made dynamic
FILLERS = {"arre", "arey", "hmm", "haan", "achha", "accha", "ji", "oh", "ah", "uh", "umm"}


def legacy_prompt() -> str:
    source = subprocess.run(
        ["git", "show", f"{LEGACY_REV}:backend/persona.py"], cwd=ROOT, capture_output=True, text=True, check=True, encoding="utf-8"
    ).stdout
    path = pathlib.Path(tempfile.gettempdir()) / "persona_legacy.py"
    path.write_text(source, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("persona_legacy", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.PERSONA_TEXT


async def one_reply(contents: list[types.Content], cfg: types.GenerateContentConfig) -> str:
    for _ in range(4):
        try:
            response = await flash(text_client(), contents=contents, cfg=cfg, attempts=5)
        except Exception:  # noqa: BLE001 - a lost reply is simply skipped
            return ""
        if not response.candidates:
            return ""
        contents.append(response.candidates[0].content)
        calls = response.function_calls or []
        if not calls:
            return (response.text or "").strip()
        contents.append(
            types.Content(role="user", parts=[types.Part.from_function_response(name=c.name, response={"result": "ok"}) for c in calls])
        )
    return ""


async def conversation(legacy: str | None, lines: list[str]) -> list[str]:
    profile = CallProfile()
    prompt = legacy or build_persona_text(profile)
    contents = [types.Content(role="user", parts=[types.Part(text=OPENING_CUE)])]
    replies: list[str] = []
    for step in range(len(lines) + 1):
        system = prompt if legacy else prompt + turn_note(replies)
        cfg = types.GenerateContentConfig(
            system_instruction=system,
            tools=PERSONA_TOOLS,
            thinking_config=analysis._thinking(),
            temperature=None if legacy else config.PERSONA_TEMPERATURE,
        )
        reply = await one_reply(contents, cfg)
        replies.append(reply)
        if step < len(lines):
            contents.append(types.Content(role="user", parts=[types.Part(text=lines[step])]))
    return replies


def first_word(text: str) -> str:
    words = re.findall(r"[\w']+", text.lower())
    return words[0] if words else ""


def metrics(conversations: list[list[str]]) -> dict:
    replies = [r for convo in conversations for r in convo if r]
    openers = Counter(first_word(r) for r in replies)
    lengths = [len(r.split()) for r in replies]
    total = max(1, len(replies))
    return {
        "replies": len(replies),
        "distinct_opening_words": f"{len(openers)} ({round(100 * len(openers) / total)}% of replies)",
        "most_common_opener": f"{openers.most_common(1)[0][0]!r} in {round(100 * openers.most_common(1)[0][1] / total)}% of replies" if openers else "",
        "start_with_a_filler": f"{round(100 * sum(first_word(r) in FILLERS for r in replies) / total)}%",
        "contain_arre": f"{round(100 * sum('arre' in r.lower() or 'arey' in r.lower() for r in replies) / total)}%",
        "contain_sahi_hai": f"{round(100 * sum('sahi hai' in r.lower() for r in replies) / total)}%",
        "end_with_a_question": f"{round(100 * sum(r.rstrip().endswith('?') for r in replies) / total)}%",
        "words_per_reply": f"mean {statistics.mean(lengths):.1f}, stdev {statistics.pstdev(lengths):.1f}, min {min(lengths)}, max {max(lengths)}",
    }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=8)
    parser.add_argument("--legacy", action="store_true")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    prompt = legacy_prompt() if args.legacy else None
    results = await asyncio.gather(*(conversation(prompt, LINES["english"]) for _ in range(args.runs)))
    label = "legacy" if args.legacy else "current"
    scores = metrics(results)
    print(f"{label} persona, {args.runs} calls x {len(LINES['english']) + 1} replies")
    for key, value in scores.items():
        print(f"  {key:22} {value}")
    print("first call:")
    for reply in results[0]:
        print(f"  - {reply}")
    out = ROOT / "eval" / "results" / f"variety-{label}.json"
    out.write_text(json.dumps({"persona": label, "calls": args.runs, "metrics": scores, "first_call": results[0]}, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
