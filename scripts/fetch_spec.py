#!/usr/bin/env python3
"""Download AgencyZoom's OpenAPI spec into ``openapi/agencyzoom.yaml``.

The spec belongs to AgencyZoom/Vertafore and is marked proprietary, so this
repository does not redistribute it: the file is git-ignored and fetched from
AgencyZoom's public documentation site on demand. Only its SHA-256 fingerprint
is committed (``openapi/agencyzoom.yaml.sha256``), so we can tell when
AgencyZoom changes its API.

Usage::

    python scripts/fetch_spec.py            # download; fail if it differs from the pinned version
    python scripts/fetch_spec.py --update   # download and pin the new version (after reviewing it)
    python scripts/fetch_spec.py --check    # exit 1 if the live spec differs from the pinned one

Exit codes: 0 = matches the pin (or pin updated), 1 = upstream changed, 2 = download failed.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC_URL = "https://app.agencyzoom.com/openapi/agencyzoom.yaml"
SPEC_PATH = ROOT / "openapi" / "agencyzoom.yaml"
PIN_PATH = ROOT / "openapi" / "agencyzoom.yaml.sha256"


def download(url: str = SPEC_URL, timeout: float = 60) -> bytes:
    request = urllib.request.Request(
        url, headers={"User-Agent": "agencyzoom-python-sdk spec fetch"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data: bytes = response.read()
    if not data.lstrip().startswith(b"openapi:"):
        raise ValueError(f"{url} did not return an OpenAPI YAML document")
    return data


def pinned_digest() -> str | None:
    if not PIN_PATH.exists():
        return None
    return PIN_PATH.read_text("utf-8").split()[0].strip() or None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--update", action="store_true", help="pin the downloaded version")
    mode.add_argument("--check", action="store_true", help="only compare with the pin")
    args = parser.parse_args()

    try:
        data = download()
    except Exception as exc:  # network errors, HTTP errors, unexpected content
        print(f"Could not download the spec from {SPEC_URL}: {exc}", file=sys.stderr)
        return 2

    digest = hashlib.sha256(data).hexdigest()
    pinned = pinned_digest()
    changed = pinned is not None and digest != pinned

    if not args.check:
        SPEC_PATH.parent.mkdir(parents=True, exist_ok=True)
        SPEC_PATH.write_bytes(data)
        print(f"Saved {SPEC_PATH.relative_to(ROOT)} ({len(data):,} bytes, sha256 {digest[:12]}…)")

    if args.update or pinned is None:
        PIN_PATH.write_text(f"{digest}  agencyzoom.yaml\n", "utf-8")
        print(f"Pinned sha256 {digest[:12]}… in {PIN_PATH.relative_to(ROOT)}")
        return 0
    if changed:
        print(
            "AgencyZoom's spec has changed since it was pinned.\n"
            "Review it, then run:  make spec-update && make generate && make test",
            file=sys.stderr,
        )
        return 1
    print("Spec matches the pinned version.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
