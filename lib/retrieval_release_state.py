"""Serialize release activation and compare the active pointer under the lock."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path


def activate_record(release_root: Path, record: dict, *, expected_sha256: str | None = None,
                    expected_release_id: str | None = None) -> None:
    release_root.mkdir(parents=True, exist_ok=True)
    with (release_root / '.activation.lock').open('a') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        active = release_root / 'active-release.json'
        current = active.read_bytes() if active.exists() else b''
        if expected_sha256 is not None and hashlib.sha256(current).hexdigest() != expected_sha256:
            raise RuntimeError('active release changed before activation')
        if expected_release_id is not None and (not current or json.loads(current).get('release_id') != expected_release_id):
            raise RuntimeError('active release changed before activation')
        temporary = release_root / f'.active-release.{os.getpid()}.tmp'
        temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        os.replace(temporary, active)
