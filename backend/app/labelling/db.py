"""Database tables for coach labelling: batches, videos, reviews and upload jobs.

The schema is created and changed only through Alembic migrations
(backend/migrations); ``metadata`` here is the single source of truth they
are generated from.
"""

from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Engine,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    MetaData,
    SmallInteger,
    String,
    Table,
    Text,
    UniqueConstraint,
    create_engine,
    event,
)

from app.config import settings

metadata = MetaData(
    naming_convention={
        "pk": "pk_%(table_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "ix": "ix_%(table_name)s_%(column_0_name)s",
    }
)

ID = String(128)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# A batch is a labelling dataset: "Dataset {number}" of one technique.
batches = Table(
    "labelling_batches",
    metadata,
    Column("batch_id", ID, primary_key=True),
    Column("name", String(200), nullable=False),
    Column("batch_format_version", String(20), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, default=utcnow),
    Column("technique", String(40)),
    Column("number", Integer),
    Column("due_date", Date),
    Column("note", Text, nullable=False, default="", server_default=""),
    UniqueConstraint("technique", "number", name="uq_labelling_batches_technique_number"),
)

batch_clips = Table(
    "labelling_batch_clips",
    metadata,
    Column("batch_id", ID, ForeignKey("labelling_batches.batch_id", ondelete="CASCADE"), primary_key=True),
    Column("position", Integer, primary_key=True),
    Column("analysis_id", ID, nullable=False, index=True),
    Column("source_file", String(500), nullable=False, default=""),
    # Kept original clip, relative to the outputs folder (see labelling_videos).
    Column("raw_video", String(500)),
)

videos = Table(
    "labelling_videos",
    metadata,
    Column("video_id", Integer, primary_key=True, autoincrement=True),
    Column("analysis_id", ID, nullable=False, index=True),
    Column("kind", String(20), nullable=False),
    # Relative to the outputs folder; the file itself stays on disk.
    Column("path", String(500), nullable=False, unique=True),
    Column("original_filename", String(500), nullable=False, default=""),
    Column("size_bytes", BigInteger, nullable=False),
    Column("sha256", String(64), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, default=utcnow),
)

labels = Table(
    "labelling_labels",
    metadata,
    Column("label_id", Integer, primary_key=True, autoincrement=True),
    Column("analysis_id", ID, nullable=False),
    Column("coach_key", String(200), nullable=False),
    Column("coach", String(200), nullable=False),
    Column("batch_id", ID, ForeignKey("labelling_batches.batch_id", ondelete="SET NULL")),
    Column("system_contact_frame", Integer),
    Column("corrected_hit_frame", Integer),
    Column("overall_rating", SmallInteger),
    Column("feedback", Text, nullable=False, default=""),
    # Question id, or "not_listed"; label format 2.0.0+.
    Column("most_important_fix", String(100)),
    Column("general_comment", Text, nullable=False, default="", server_default=""),
    Column("label_format_version", String(20), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("analysis_id", "coach_key", name="uq_labelling_labels_clip_coach"),
    CheckConstraint("overall_rating BETWEEN 1 AND 5", name="overall_rating_range"),
    CheckConstraint("corrected_hit_frame >= 0", name="hit_frame_non_negative"),
)

stat_labels = Table(
    "labelling_stat_labels",
    metadata,
    Column("label_id", Integer, ForeignKey("labelling_labels.label_id", ondelete="CASCADE"), primary_key=True),
    Column("stat_id", String(100), primary_key=True),
    Column("rating", String(20)),
    Column("comment", Text, nullable=False, default=""),
    CheckConstraint(
        "rating IN ('good', 'needs_work', 'looks_wrong', 'cant_see')", name="rating_value"
    ),
)

upload_jobs = Table(
    "labelling_upload_jobs",
    metadata,
    Column("job_id", ID, primary_key=True),
    Column("batch_id", ID, ForeignKey("labelling_batches.batch_id", ondelete="CASCADE"), nullable=False),
    Column("batch_name", String(200), nullable=False),
    Column("stroke_type", String(40), nullable=False),
    Column("handedness", String(20), nullable=False),
    Column("camera_view", String(20), nullable=False),
    Column("status", String(20), nullable=False),
    Column("job_format_version", String(20), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

upload_job_clips = Table(
    "labelling_upload_job_clips",
    metadata,
    Column("job_id", ID, primary_key=True),
    Column("position", Integer, primary_key=True),
    Column("source_file", String(500), nullable=False),
    Column("staged_file", String(500), nullable=False),
    Column("status", String(20), nullable=False),
    Column("analysis_id", ID),
    Column("error", Text),
    # Per-video capture context; older jobs used the job-level values.
    Column("handedness", String(20)),
    Column("camera_view", String(20)),
    ForeignKeyConstraint(["job_id"], ["labelling_upload_jobs.job_id"], ondelete="CASCADE"),
)


@lru_cache(maxsize=8)
def _engine_for(url: str) -> Engine:
    engine = create_engine(url, pool_pre_ping=True)
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine, "connect")
        def _sqlite_foreign_keys(dbapi_conn, _record) -> None:  # noqa: ANN001
            dbapi_conn.execute("PRAGMA foreign_keys=ON")

    return engine


def get_engine() -> Engine:
    """Engine for the configured database (cached per URL)."""
    return _engine_for(settings.database_url)


def iso(value: datetime | str | None) -> str | None:
    """Timestamps leave the database as ISO 8601 strings in UTC."""
    if value is None or isinstance(value, str):
        return value
    if value.tzinfo is None:  # SQLite drops the offset; stored values are UTC
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def parse_ts(value: str | datetime | None) -> datetime:
    if isinstance(value, datetime):
        return value
    if value:
        return datetime.fromisoformat(value)
    return utcnow()
