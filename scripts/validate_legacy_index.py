from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from lib.validate_legacy_index import validate_legacy_index


def main() -> None:
    report_path = validate_legacy_index()
    print(f"Wrote {report_path}")


if __name__ == "__main__":
    main()
