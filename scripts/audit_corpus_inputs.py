from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from lib.audit_corpus_inputs import (
    AVAILABLE_CHECKS,
    build_arg_parser,
    run_audit,
    write_audit_json,
    write_audit_markdown,
)


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    if args.list_checks:
        for check_name in sorted(AVAILABLE_CHECKS.keys()):
            print(check_name)
        return

    data = run_audit(selected_checks=args.check)
    md_path = write_audit_markdown(data, args.md_out)
    json_path = write_audit_json(data, args.json_out)
    print(f"Wrote {md_path}")
    print(f"Wrote {json_path}")


if __name__ == "__main__":
    main()
