"""Shared test setup."""

from __future__ import annotations

import pytest

from app.config import settings
from app.labelling.db import get_engine, metadata


@pytest.fixture(autouse=True)
def labelling_database(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch):
    """Every test gets its own empty SQLite labelling database, never the real one."""
    path = tmp_path_factory.mktemp("labelling_db") / "labelling.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{path}")
    engine = get_engine()
    metadata.create_all(engine)
    yield engine
    engine.dispose()
