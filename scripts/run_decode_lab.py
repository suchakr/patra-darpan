from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from lib.decode_lab.assembler import assemble_run
from lib.decode_lab.runner import build_arg_parser, run_decode_lab


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    if args.assemble_only:
        if not args.run_id:
            parser.error("--assemble-only requires --run-id")
        from lib.config import BUILD_DIR

        run_dir = (args.out_root or BUILD_DIR / "decode-lab") / args.run_id
        if not run_dir.exists():
            parser.error(f"Run directory does not exist: {run_dir}")
        written = assemble_run(run_dir)
        for path in written:
            print(f"Assembled {path}")
        return

    run_dir = run_decode_lab(args)
    print(f"Wrote {run_dir}")

    if args.assemble and args.assemble_lazy:
        written = assemble_run(run_dir)
        for path in written:
            print(f"Assembled {path}")


if __name__ == "__main__":
    main()
