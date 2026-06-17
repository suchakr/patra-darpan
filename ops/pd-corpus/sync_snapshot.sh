#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="${SOURCE_DIR:-pd-corpus~}"
TARGET="${1:-sccgdrive:pd-corpus/}"

if [[ ! -d "$SOURCE_DIR" ]]; then
  echo "Snapshot directory not found: $SOURCE_DIR" >&2
  echo "Run: uv run python ops/pd-corpus/build_snapshot.py" >&2
  exit 1
fi

rclone sync "$SOURCE_DIR" "$TARGET" --progress

