"""Source-neutral evidence contracts and durable storage for future ingestors."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from typing import Protocol

from .utils import utc_now


@dataclass(frozen=True, slots=True)
class EvidenceRecord:
    """An immutable source identity plus the latest observed evidence state."""

    source_name: str
    source_account_id: str
    conversation_id: str
    source_item_id: str
    observed_at: str
    content: str | None = None
    content_type: str = "message"
    author_id: str | None = None
    occurred_at: str | None = None
    raw_locator: dict[str, str | int] = field(default_factory=dict)
    metadata: dict[str, str | int | bool | None] = field(default_factory=dict)
    edited_at: str | None = None
    deleted_at: str | None = None
    is_deleted: bool = False

    @property
    def identity(self) -> tuple[str, str, str, str]:
        return (
            self.source_name,
            self.source_account_id,
            self.conversation_id,
            self.source_item_id,
        )

    def validate(self) -> None:
        if not all(part.strip() for part in self.identity):
            raise ValueError(
                "Evidence source, account, conversation, and item IDs are required."
            )
        if not self.observed_at.strip():
            raise ValueError("Evidence observed_at is required for traceability.")
        if self.is_deleted and not self.deleted_at:
            raise ValueError("Deleted evidence requires deleted_at.")


class EvidenceSource(Protocol):
    """Read a source-specific item as the shared evidence record contract."""

    source_name: str

    def get(
        self, conversation_id: str, source_item_id: str
    ) -> EvidenceRecord | None: ...


class EvidenceRepository:
    """Store non-Telegram evidence while retaining every replacement/deletion state."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def save(self, record: EvidenceRecord) -> int:
        record.validate()
        existing = self.conn.execute(
            """SELECT evidence_id,content,is_deleted FROM source_evidence
               WHERE source_name=? AND source_account_id=? AND conversation_id=? AND source_item_id=?""",
            record.identity,
        ).fetchone()
        now = utc_now()
        payload = self._payload(record)
        if existing is None:
            cursor = self.conn.execute(
                """INSERT INTO source_evidence(
                       source_name,source_account_id,conversation_id,source_item_id,content_type,
                       author_id,occurred_at,observed_at,content,raw_locator_json,metadata_json,
                       edited_at,deleted_at,is_deleted,created_at,updated_at
                   ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    *record.identity,
                    record.content_type,
                    record.author_id,
                    record.occurred_at,
                    record.observed_at,
                    record.content,
                    payload[0],
                    payload[1],
                    record.edited_at,
                    record.deleted_at,
                    int(record.is_deleted),
                    now,
                    now,
                ),
            )
            assert cursor.lastrowid is not None
            evidence_id = int(cursor.lastrowid)
            self._save_version(evidence_id, record.content, now, "initial")
        else:
            evidence_id, previous_content, was_deleted = (
                int(existing[0]),
                existing[1],
                bool(existing[2]),
            )
            reason = "deleted" if record.is_deleted and not was_deleted else "edited"
            if (
                previous_content != record.content
                or bool(record.is_deleted) != was_deleted
            ):
                self._save_version(evidence_id, previous_content, now, reason)
            self.conn.execute(
                """UPDATE source_evidence SET content_type=?,author_id=?,occurred_at=?,observed_at=?,
                       content=?,raw_locator_json=?,metadata_json=?,edited_at=?,deleted_at=?,is_deleted=?,updated_at=?
                   WHERE evidence_id=?""",
                (
                    record.content_type,
                    record.author_id,
                    record.occurred_at,
                    record.observed_at,
                    record.content,
                    payload[0],
                    payload[1],
                    record.edited_at,
                    record.deleted_at,
                    int(record.is_deleted),
                    now,
                    evidence_id,
                ),
            )
        self.conn.commit()
        return evidence_id

    def get(self, identity: tuple[str, str, str, str]) -> EvidenceRecord | None:
        row = self.conn.execute(
            """SELECT source_name,source_account_id,conversation_id,source_item_id,observed_at,
                      content,content_type,author_id,occurred_at,raw_locator_json,metadata_json,
                      edited_at,deleted_at,is_deleted
               FROM source_evidence
               WHERE source_name=? AND source_account_id=? AND conversation_id=? AND source_item_id=?""",
            identity,
        ).fetchone()
        if row is None:
            return None
        return EvidenceRecord(
            source_name=str(row[0]),
            source_account_id=str(row[1]),
            conversation_id=str(row[2]),
            source_item_id=str(row[3]),
            observed_at=str(row[4]),
            content=row[5],
            content_type=str(row[6]),
            author_id=row[7],
            occurred_at=row[8],
            raw_locator=json.loads(row[9]),
            metadata=json.loads(row[10]),
            edited_at=row[11],
            deleted_at=row[12],
            is_deleted=bool(row[13]),
        )

    def versions(self, evidence_id: int) -> list[tuple[str | None, str, str]]:
        return [
            (row[0], str(row[1]), str(row[2]))
            for row in self.conn.execute(
                """SELECT content,captured_at,reason FROM source_evidence_versions
                   WHERE evidence_id=? ORDER BY version_id""",
                (evidence_id,),
            )
        ]

    def _payload(self, record: EvidenceRecord) -> tuple[str, str]:
        return (
            json.dumps(record.raw_locator, sort_keys=True),
            json.dumps(record.metadata, sort_keys=True),
        )

    def _save_version(
        self, evidence_id: int, content: str | None, captured_at: str, reason: str
    ) -> None:
        self.conn.execute(
            "INSERT INTO source_evidence_versions(evidence_id,content,captured_at,reason) VALUES (?,?,?,?)",
            (evidence_id, content, captured_at, reason),
        )
