"""Run the live classifier over eval/classifier_cases.py: ordinary calls must not be flagged, scams must be.

    python eval/classifier_check.py [--runs 2]
"""

import argparse
import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "backend"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import analysis  # noqa: E402
from classifier_cases import ORDINARY, SCAMS, to_turns  # noqa: E402
from clients import text_client  # noqa: E402


async def judge(name: str, call: list, sem: asyncio.Semaphore):
    async with sem:
        return name, await analysis.verify(text_client(), to_turns(call))


async def main(runs: int) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sem = asyncio.Semaphore(4)
    jobs = [(n, c, False) for n, c in ORDINARY.items()] + [(n, c, True) for n, c in SCAMS.items()]
    rows = []
    for _ in range(runs):
        results = await asyncio.gather(*[judge(n, c, sem) for n, c, _ in jobs])
        rows.extend((n, scam, res) for (n, _, scam), (_, res) in zip(jobs, results))
    false_alarms = missed = errors = 0
    for name, is_scam, res in rows:
        if res is None:
            errors += 1
            print(f"ERROR  {name}")
            continue
        flagged = res.verdict == "scam"
        bad = flagged != is_scam
        false_alarms += bad and not is_scam
        missed += bad and is_scam
        print(f"{'FAIL' if bad else 'ok  '}  {'scam' if is_scam else 'ordinary':8} {name:22} -> {res.verdict} ({res.scam_type}) {res.confidence:.2f}")
    ordinary = sum(1 for _, s, r in rows if not s and r)
    scams = sum(1 for _, s, r in rows if s and r)
    print(f"\nfalse alarms on ordinary calls: {false_alarms}/{ordinary}; scams missed: {missed}/{scams}; errors: {errors}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=2)
    asyncio.run(main(parser.parse_args().runs))
