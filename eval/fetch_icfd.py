"""Download the ICFD-31k test conversations (defensive-research licence: evaluation only, never used in the product).

    python eval/fetch_icfd.py
"""

import json
import pathlib
import urllib.request

import zstandard

BASE = "https://huggingface.co/datasets/rishia2220/icfd-31k/resolve/main/source_conversations/"
FILES = ["test-00000-of-00002.jsonl.zst"]
DEST = pathlib.Path(__file__).resolve().parent / "datasets"


def main() -> None:
    DEST.mkdir(exist_ok=True)
    for name in FILES:
        target = DEST / name.replace(".zst", "")
        if target.exists():
            print("have", target.name)
            continue
        with urllib.request.urlopen(BASE + name, timeout=120) as response:
            raw = response.read()
        with zstandard.ZstdDecompressor().stream_reader(raw) as reader:
            target.write_bytes(reader.read())
        print("saved", target.name, target.stat().st_size, "bytes")
    first = json.loads((DEST / FILES[0].replace(".zst", "")).read_text(encoding="utf-8").splitlines()[0])
    print({k: (str(v)[:90]) for k, v in first.items()})


if __name__ == "__main__":
    main()

