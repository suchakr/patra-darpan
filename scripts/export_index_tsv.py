from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from lib.export_index_tsv import export_index_tsv


def main() -> None:
    output_path = export_index_tsv()
    print(f"Exported {output_path}")


if __name__ == "__main__":
    main()
