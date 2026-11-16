"""End-to-end: analyse cut clips, filter, compose datasets, stash hidden labels."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from app.labelling.batches import Batch, BatchClip, BatchStore
from app.labelling.cli import analyze_clip
from app.labelling.datasets import create_dataset
from app.labelling.multisense import CAMERA_VIEW, SOURCE_NAME, STROKE
from app.labelling.multisense.compose import compose_datasets
from app.labelling.multisense.cut import ClipMeta, load_manifest
from app.labelling.multisense.external_labels import save_external_labels
from app.labelling.multisense.filter import FilterResult, filter_analyses

Analyzer = Callable[[Path, str, str, str], str]


def analyse_pool(
    clips: list[ClipMeta],
    clips_dir: Path,
    *,
    analyzer: Analyzer = analyze_clip,
    output_dir: Path | None = None,
    log=print,
) -> list[tuple[ClipMeta, str]]:
    """Run each clip through /analyze; return (meta, analysis_id) pairs that finished."""
    store = BatchStore(output_dir)
    done: list[tuple[ClipMeta, str]] = []
    for i, meta in enumerate(clips, start=1):
        path = clips_dir / meta.participant_id / f"{meta.clip_id}.mp4"
        if not path.is_file():
            log(f"[{i}/{len(clips)}] missing {path}")
            continue
        log(f"[{i}/{len(clips)}] analyse {meta.clip_id} ({meta.handedness}) …")
        try:
            analysis_id = analyzer(path, STROKE, meta.handedness, CAMERA_VIEW)
        except Exception as exc:  # noqa: BLE001
            log(f"    failed: {exc}")
            continue
        store.keep_raw_video(path, analysis_id)
        save_external_labels(analysis_id, meta, output_dir)
        done.append((meta, analysis_id))
        log(f"    -> {analysis_id}")
    return done


def filter_pool(
    pairs: list[tuple[ClipMeta, str]],
    *,
    output_dir: Path,
) -> tuple[list[tuple[ClipMeta, str]], FilterResult]:
    by_id = {aid: meta for meta, aid in pairs}
    result = filter_analyses([aid for _m, aid in pairs], output_dir=output_dir)
    kept = [(by_id[aid], aid) for aid in result.kept if aid in by_id]
    return kept, result


def create_multisense_datasets(
    kept: list[tuple[ClipMeta, str]],
    *,
    count: int = 3,
    output_dir: Path | None = None,
    log=print,
) -> list[Batch]:
    meta_by_id = {m.clip_id: (m, aid) for m, aid in kept}
    picks = compose_datasets([m for m, _aid in kept], count=count)
    batches: list[Batch] = []
    for pick in picks:
        existing = [
            BatchClip(
                analysis_id=meta_by_id[c.clip_id][1],
                source_file=c.clip_id + ".mp4",
            )
            for c in pick.clips
        ]
        batch, _job = create_dataset(
            technique=STROKE,
            due_date=None,
            note="",
            source=SOURCE_NAME,
            existing=existing,
            output_dir=output_dir,
        )
        log(
            f"Created {batch.name} source={batch.source} "
            f"skills={pick.skill_counts} participants={pick.participant_counts}"
        )
        batches.append(batch)
    return batches


def run_from_clips_dir(
    clips_dir: Path,
    *,
    count: int = 3,
    max_analyse: int | None = 48,
    output_dir: Path | None = None,
    analyzer: Analyzer = analyze_clip,
    log=print,
) -> tuple[list[Batch], FilterResult]:
    """Analyse up to ``max_analyse`` clips from a cut manifest, filter, create datasets."""
    pool = load_manifest(clips_dir)
    # Prefer a spread of participants for the analyse budget.
    by_part: dict[str, list[ClipMeta]] = {}
    for c in pool:
        by_part.setdefault(c.participant_id, []).append(c)
    selected: list[ClipMeta] = []
    while max_analyse is None or len(selected) < max_analyse:
        progressed = False
        for pid in sorted(by_part):
            if max_analyse is not None and len(selected) >= max_analyse:
                break
            if by_part[pid]:
                selected.append(by_part[pid].pop(0))
                progressed = True
        if not progressed:
            break
    log(f"Analysing {len(selected)} of {len(pool)} cut clips …")
    from app.config import settings

    out = Path(output_dir or settings.output_dir)
    pairs = analyse_pool(
        selected, clips_dir, analyzer=analyzer, output_dir=out, log=log
    )
    kept, result = filter_pool(pairs, output_dir=out)
    log(f"Kept {len(kept)}; dropped {result.counts()}")
    batches = create_multisense_datasets(kept, count=count, output_dir=out, log=log)
    return batches, result
