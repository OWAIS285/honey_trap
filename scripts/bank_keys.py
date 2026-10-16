"""Print the bank API key for each proxy bank (or the ones named), derived from BANK_SIGNING_SECRET.

    $env:BANK_SIGNING_SECRET = (gcloud secrets versions access latest --secret stallwart-bank-signing-secret)
    python scripts/bank_keys.py UTIB SBIN

Treat the output like a password: anyone with a bank's key can read that bank's reports.
"""

import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "backend"))

import bank_registry  # noqa: E402
import bank_reports  # noqa: E402
import config  # noqa: E402


def main() -> None:
    config.BANK_SIGNING_SECRET = os.getenv("BANK_SIGNING_SECRET", "").strip()
    if not config.BANK_SIGNING_SECRET:
        sys.exit("Set BANK_SIGNING_SECRET first (the same value the backend uses).")
    codes = [c.upper() for c in sys.argv[1:]] or list(bank_registry.BANKS)
    for code in codes:
        if code not in bank_registry.BANKS and code != bank_registry.UNRESOLVED:
            print(f"{code:11} unknown bank code", file=sys.stderr)
            continue
        print(f"{code:11} {bank_reports.bank_api_key(code)}  {bank_registry.bank_name(code)}")


if __name__ == "__main__":
    main()
