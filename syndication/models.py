"""SQLAlchemy models for the syndication-service state store.

All tables are separate from hop-core's user/org tables (no FKs into
hop-core) to keep the syndication schema self-contained.  The ``org_id``
column on SyncConfig is a string reference; integrity is enforced at the
application layer via hop-core's organisation APIs.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, Text, Boolean, ForeignKey
from sqlalchemy.orm import relationship

from hop_core.db import Base


def _new_id() -> str:
    return str(uuid.uuid4())


class SyncConfig(Base):
    """Represents a configured sync between one source and one target."""

    __tablename__ = "syncs"

    id = Column(String(36), primary_key=True, default=_new_id)
    org_id = Column(String(36), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    adapter_id = Column(String(64), nullable=False)   # e.g. "deploy"
    connector_id = Column(String(64), nullable=False) # e.g. "salesforce"
    deployment_id = Column(String(255), nullable=True)
    # Soft reference to hop-core's credentials table (no FK — different domain).
    credential_id = Column(String(36), nullable=True)
    cron_expression = Column(String(128), nullable=True)  # None = manual-only sync
    mapping_json = Column(Text, nullable=False, default="{}")
    is_active = Column(Boolean, nullable=False, default=True)
    high_water_mark = Column(String(64), nullable=True)  # ISO 8601 cursor

    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    runs = relationship("SyncRun", back_populates="sync", cascade="all, delete-orphan")
    records = relationship("SyncRecord", back_populates="sync", cascade="all, delete-orphan")

    @property
    def mapping(self) -> dict:
        try:
            return json.loads(self.mapping_json or "{}")
        except (ValueError, TypeError):
            return {}


class SyncRun(Base):
    """A single execution record for a SyncConfig."""

    __tablename__ = "sync_runs"

    id = Column(String(36), primary_key=True)           # caller-supplied run_id
    sync_id = Column(String(36), ForeignKey("syncs.id"), nullable=False, index=True)
    status = Column(String(32), nullable=False, default="running")
    # running → success | failed
    started_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime, nullable=True)
    changed_count = Column(Integer, nullable=True)
    removed_count = Column(Integer, nullable=True)
    links_fixed = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    warning_messages = Column(Text, nullable=True)  # JSON-serialised list[str]

    sync = relationship("SyncConfig", back_populates="runs")


class SyncRecord(Base):
    """Tracks the target-system article ID for each synced source page.

    The ``source_uuid`` is the ``sys.uuid`` from the Deploy API and is the
    stable cross-run key.  The ``target_article_id`` is whatever the target
    connector returns from ``upsert_article()``.
    """

    __tablename__ = "sync_records"

    id = Column(String(36), primary_key=True, default=_new_id)
    sync_id = Column(String(36), ForeignKey("syncs.id"), nullable=False, index=True)
    source_uuid = Column(String(36), nullable=False)
    target_article_id = Column(String(255), nullable=False)
    status = Column(String(32), nullable=False, default="active")  # active | archived
    last_synced_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    sync = relationship("SyncConfig", back_populates="records")

    __table_args__ = (
        # one row per (sync_id, source_uuid)
        {"sqlite_autoincrement": False},
    )
