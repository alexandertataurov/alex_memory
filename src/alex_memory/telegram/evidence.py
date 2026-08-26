"""Telegram adapter for the source-neutral evidence contract."""

from __future__ import annotations

import sqlite3

from ..evidence import EvidenceRecord


class TelegramEvidenceSource:
    source_name = "telegram"
    source_account_id = "default"

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def get(self, conversation_id: str, source_item_id: str) -> EvidenceRecord | None:
        row = self.conn.execute(
            """SELECT m.chat_id,m.message_id,m.sender_id,m.date,m.text,m.edited_at,m.deleted_at,
                      m.is_deleted,c.title
               FROM messages m LEFT JOIN chats c ON c.chat_id=m.chat_id
               WHERE m.chat_id=? AND m.message_id=?""",
            (int(conversation_id), int(source_item_id)),
        ).fetchone()
        if row is None:
            return None
        observed_at = row[5] or row[6] or row[3] or "unknown"
        return EvidenceRecord(
            source_name=self.source_name,
            source_account_id=self.source_account_id,
            conversation_id=str(row[0]),
            source_item_id=str(row[1]),
            observed_at=str(observed_at),
            content=row[4],
            author_id=str(row[2]) if row[2] is not None else None,
            occurred_at=row[3],
            raw_locator={"chat_id": int(row[0]), "message_id": int(row[1])},
            metadata={"chat_title": row[8]},
            edited_at=row[5],
            deleted_at=row[6],
            is_deleted=bool(row[7]),
        )
