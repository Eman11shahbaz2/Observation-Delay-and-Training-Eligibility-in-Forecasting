"""Restore official UCI archives and verify the frozen source hashes."""
from pathlib import Path
import hashlib
import json
import urllib.request
import os

ROOT = Path(__file__).resolve().parent

def main():
    sources = json.loads((ROOT / "dataset_sources.json").read_text())
    target = ROOT / "study" / "source_archives"
    target.mkdir(parents=True, exist_ok=True)
    for name, source in sources.items():
        dest = target / (name + "_official.zip")
        if dest.exists():
            if hashlib.sha256(dest.read_bytes()).hexdigest() != source["sha256"]:
                raise RuntimeError("Existing archive has wrong hash: " + name)
            print("Verified " + name)
            continue
        temp = dest.with_suffix(".zip.part")
        try:
            with urllib.request.urlopen(source["url"], timeout=300) as response, temp.open("wb") as output:
                while True:
                    block = response.read(1024 * 1024)
                    if not block:
                        break
                    output.write(block)
            if hashlib.sha256(temp.read_bytes()).hexdigest() != source["sha256"]:
                raise RuntimeError("Official archive differs from frozen source: " + name)
            os.replace(temp, dest)
            print("Downloaded and verified " + name)
        finally:
            temp.unlink(missing_ok=True)

if __name__ == "__main__":
    main()
