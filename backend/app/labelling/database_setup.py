"""Create / migrate the labelling database and import older file-based data."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError

from app.config import settings
from app.labelling import db
from app.labelling.batches import Batch, BatchStore, labelling_dir
from app.labelling.jobs import JobStore
from app.labelling.labels import LabelStore

BACKEND_DIR = Path(__file__).resolve().parents[2]


def alembic_config(url: str | None = None) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url or settings.database_url)
    cfg.attributes["configure_logger"] = False
    return cfg


def ensure_database_exists(url: str | None = None) -> bool:
    """Create the Postgres database if it is missing; True if it was created."""
    url_obj = make_url(url or settings.database_url)
    if url_obj.get_backend_name() != "postgresql":
        return False
    try:
        with create_engine(url_obj).connect():
            return False
    except OperationalError as exc:
        if "does not exist" not in str(exc):
            raise
    admin = create_engine(url_obj.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{url_obj.database}"'))
    admin.dispose()
    return True


def upgrade_database(url: str | None = None) -> None:
    command.upgrade(alembic_config(url), "head")


def import_files(output_dir: Path | None = None) -> dict[str, Any]:
    """Load JSON batches, labels and jobs into the database, register kept videos,
    then move the JSON files into a dated backup folder. Safe to run twice."""
    root = labelling_dir(output_dir)
    batch_store, label_store, job_store = (
        BatchStore(output_dir),
        LabelStore(output_dir),
        JobStore(output_dir),
    )
    counts = {"batches": 0, "labels": 0, "jobs": 0, "videos": 0, "skipped": 0}
    imported: list[Path] = []
    source_names: dict[str, str] = {}

    for path in sorted((root / "batches").glob("*.json")):
        batch = Batch.from_dict(json.loads(path.read_text(encoding="utf-8")))
        for clip in batch.clips:
            source_names[clip.analysis_id] = clip.source_file
        try:
            batch_store.get(batch.batch_id)
            counts["skipped"] += 1
        except FileNotFoundError:
            batch_store.save(batch)
            counts["batches"] += 1
        imported.append(path)

    for path in sorted((root / "labels").glob("*/*.json")):
        label = json.loads(path.read_text(encoding="utf-8"))
        if label_store.get(label["analysis_id"], label["coach"]) is None:
            label_store.write(label)
            counts["labels"] += 1
        else:
            counts["skipped"] += 1
        imported.append(path)

    for path in sorted((root / "jobs").glob("*.json")):
        job = json.loads(path.read_text(encoding="utf-8"))
        try:
            job_store.get(job["job_id"])
            counts["skipped"] += 1
        except FileNotFoundError:
            job_store.save(job)
            counts["jobs"] += 1
        for clip in job.get("clips") or []:
            if clip.get("analysis_id"):
                source_names.setdefault(clip["analysis_id"], clip["source_file"])
        imported.append(path)

    with batch_store.engine.connect() as conn:
        known = set(conn.execute(select(db.videos.c.path)).scalars())
    for path in sorted((root / "videos").glob("*")):
        rel = path.relative_to(root.parent).as_posix()
        if not path.is_file() or rel in known:
            continue
        batch_store.register_video(
            path, rel, analysis_id=path.stem, original_filename=source_names.get(path.stem, "")
        )
        counts["videos"] += 1

    backup = None
    if imported:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = root / f"_imported_json_{stamp}"
        for path in imported:
            dest = backup / path.relative_to(root)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(path), dest)
        for folder in ("batches", "labels"):
            shutil.rmtree(root / folder, ignore_errors=True)
    return {**counts, "backup": str(backup) if backup else None}
