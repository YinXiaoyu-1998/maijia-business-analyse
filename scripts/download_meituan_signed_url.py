#!/usr/bin/env python3
"""Download a Meituan export file from an already authorized signed URL."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def download(url: str, output: Path) -> int:
    output.parent.mkdir(parents=True, exist_ok=True)
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urlopen(request, timeout=120) as response:
            data = response.read()
    except HTTPError as exc:
        raise SystemExit(f"HTTP error {exc.code}: {exc.reason}") from exc
    except URLError as exc:
        raise SystemExit(f"Network error: {exc.reason}") from exc

    if not data.startswith(b"PK"):
        preview = data[:120].decode("utf-8", errors="replace")
        raise SystemExit(f"Downloaded content does not look like .xlsx OOXML: {preview!r}")

    output.write_bytes(data)
    return len(data)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="Signed s3plus.sankuai.com export URL")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    written = download(args.url, args.output)
    print(f"saved={args.output}")
    print(f"bytes={written}")


if __name__ == "__main__":
    main()
