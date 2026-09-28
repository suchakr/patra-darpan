#!/usr/bin/env python3
"""Wait until the configured Qdrant HTTP endpoint responds."""

from __future__ import annotations

import argparse
import os
import time

import requests


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=os.getenv("QDRANT_URL", "http://qdrant:6333"))
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--interval", type=float, default=2.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    url = args.url.rstrip("/")
    deadline = time.monotonic() + args.timeout
    last_error: Exception | None = None

    while time.monotonic() < deadline:
        try:
            response = requests.get(f"{url}/collections", timeout=2)
            response.raise_for_status()
            print(f"Qdrant ready: {url}")
            return 0
        except (OSError, requests.RequestException) as exc:
            last_error = exc
            time.sleep(args.interval)

    raise SystemExit(f"Qdrant did not become ready at {url}: {last_error}")


if __name__ == "__main__":
    raise SystemExit(main())
