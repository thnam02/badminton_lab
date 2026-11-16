"""CLI for MultiSenseBadminton → coach datasets.

Examples:

    python -m app.labelling.multisense cut \\
        --root ../data/external/multisense \\
        --out ../data/multisense_clips

    python -m app.labelling.multisense import-datasets \\
        --clips ../data/multisense_clips \\
        --count 3 --max-analyse 48
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.labelling.multisense")
    sub = parser.add_subparsers(dest="cmd", required=True)

    cut_p = sub.add_parser("cut", help="Cut one-stroke Side clips + metadata JSON")
    cut_p.add_argument("--root", type=Path, required=True, help="MultiSense root (Documentations + Data Archive Part*)")
    cut_p.add_argument("--out", type=Path, required=True, help="Output folder for clips")

    imp = sub.add_parser(
        "import-datasets",
        help="Analyse cut clips, filter, create datasets (source=MultiSenseBadminton, no due date)",
    )
    imp.add_argument("--clips", type=Path, required=True, help="Folder produced by `cut`")
    imp.add_argument("--count", type=int, default=3)
    imp.add_argument("--max-analyse", type=int, default=48)
    imp.add_argument("--output-dir", type=Path, default=None)

    args = parser.parse_args(argv)
    if args.cmd == "cut":
        from app.labelling.multisense.cut import cut_all

        cut_all(args.root.resolve(), args.out.resolve())
        return 0

    if args.cmd == "import-datasets":
        from app.labelling.database_setup import upgrade_database
        from app.labelling.multisense.pipeline import run_from_clips_dir

        upgrade_database()
        batches, result = run_from_clips_dir(
            args.clips.resolve(),
            count=args.count,
            max_analyse=args.max_analyse,
            output_dir=args.output_dir,
        )
        print("Dropped:", result.counts())
        print("Datasets:", [b.batch_id for b in batches])
        return 0 if batches else 1

    return 1


if __name__ == "__main__":
    sys.exit(main())
