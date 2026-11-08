"""Create labelling batches.

From a folder of clips (each clip runs through the same /analyze pipeline as
an upload, and the original video is kept):

    python -m app.labelling.cli create --folder ~/clips/side_set_1 \\
        --stroke FOREHAND_CLEAR --handedness RIGHT --camera-view SIDE \\
        --name "Side-view set 1"

From analyses that already exist (no processing):

    python -m app.labelling.cli create --analysis-ids <id> <id> --name "Quick check"

Database (Postgres, settings.database_url / DATABASE_URL):

    python -m app.labelling.cli init-db        # create + migrate
    python -m app.labelling.cli import-files   # move older JSON data in
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Callable
from pathlib import Path

from app.labelling.batches import Batch, BatchClip, BatchStore, new_batch_id

VIDEO_SUFFIXES = (".mp4", ".mov")
FRONTEND_URL = "http://localhost:3000"

# (clip path, stroke, handedness, camera view) -> analysis id
Analyzer = Callable[[Path, str, str, str], str]


def analyze_clip(path: Path, stroke: str, handedness: str, camera_view: str) -> str:
    """Run one clip through the /analyze route exactly as an upload would."""
    from starlette.datastructures import UploadFile

    from app.cv.densepose.compat import apply_pillow_shims

    apply_pillow_shims()  # as app.main does, before any model imports
    from app.routes.analyze import analyze

    with path.open("rb") as fh:
        payload = asyncio.run(
            analyze(
                video=UploadFile(file=fh, filename=path.name),
                muscle_overlay=None,
                mesh_overlay=False,
                shuttle_track=None,
                racket_track=None,
                stroke_type=stroke,
                handedness=handedness,
                camera_view=camera_view,
            )
        )
    return str(payload["analysis_id"])


def find_clips(folder: Path) -> list[Path]:
    return sorted(
        p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_SUFFIXES
    )


def create_batch_from_folder(
    folder: Path,
    *,
    name: str,
    stroke: str,
    handedness: str,
    camera_view: str,
    store: BatchStore | None = None,
    analyzer: Analyzer = analyze_clip,
    log: Callable[[str], None] = print,
) -> tuple[Batch, list[tuple[Path, str]]]:
    store = store or BatchStore()
    clips = find_clips(folder)
    if not clips:
        raise ValueError(f"No .mp4 or .mov clips in {folder}")
    batch = Batch(batch_id=new_batch_id(name), name=name)
    failures: list[tuple[Path, str]] = []
    for i, path in enumerate(clips, start=1):
        log(f"[{i}/{len(clips)}] {path.name} …")
        try:
            analysis_id = analyzer(path, stroke, handedness, camera_view)
        except Exception as exc:  # noqa: BLE001 — keep going; report at the end
            detail = getattr(exc, "detail", None) or str(exc)
            failures.append((path, str(detail)))
            log(f"    failed: {detail}")
            continue
        raw = store.keep_raw_video(path, analysis_id)
        batch.clips.append(
            BatchClip(analysis_id=analysis_id, source_file=path.name, raw_video=raw)
        )
        log(f"    analysis {analysis_id}")
    if not batch.clips:
        raise RuntimeError("Every clip failed; no batch was created.")
    store.save(batch)
    return batch, failures


def create_batch_from_ids(
    analysis_ids: list[str], *, name: str, store: BatchStore | None = None
) -> Batch:
    store = store or BatchStore()
    batch = Batch(
        batch_id=new_batch_id(name),
        name=name,
        clips=[BatchClip(analysis_id=a) for a in analysis_ids],
    )
    store.save(batch)
    return batch


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.labelling.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create", help="Create a labelling batch")
    source = create.add_mutually_exclusive_group(required=True)
    source.add_argument("--folder", type=Path, help="Folder of .mp4/.mov clips to analyse")
    source.add_argument("--analysis-ids", nargs="+", help="Existing analysis ids")
    create.add_argument("--name", required=True, help="Batch name shown to coaches")
    create.add_argument("--stroke", default="FOREHAND_CLEAR")
    create.add_argument("--handedness", default="RIGHT")
    create.add_argument("--camera-view", default="SIDE")
    sub.add_parser("init-db", help="Create the labelling database if needed and apply migrations")
    sub.add_parser(
        "import-files",
        help="Move JSON batches / labels / jobs from outputs/labelling into the database",
    )
    args = parser.parse_args(argv)

    if args.command in ("init-db", "import-files"):
        from app.labelling.database_setup import (
            ensure_database_exists,
            import_files,
            upgrade_database,
        )

        if args.command == "init-db":
            created = ensure_database_exists()
            upgrade_database()
            print(("Created and migrated" if created else "Migrated") + " the labelling database.")
        else:
            result = import_files()
            print(
                f"Imported {result['batches']} batches, {result['labels']} labels, "
                f"{result['jobs']} upload jobs, {result['videos']} videos "
                f"({result['skipped']} already in the database)."
            )
            if result["backup"]:
                print(f"Original JSON files moved to {result['backup']}")
        return 0

    try:
        if args.folder is not None:
            batch, failures = create_batch_from_folder(
                args.folder.expanduser(),
                name=args.name,
                stroke=args.stroke,
                handedness=args.handedness,
                camera_view=args.camera_view,
            )
        else:
            batch, failures = create_batch_from_ids(args.analysis_ids, name=args.name), []
    except (ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"\nBatch '{batch.name}' ({batch.batch_id}) with {len(batch.clips)} clips.")
    for path, detail in failures:
        print(f"  skipped {path.name}: {detail}")
    print(f"Open it at {FRONTEND_URL}/coach/{batch.batch_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
