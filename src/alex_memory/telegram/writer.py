from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import Callable
from typing import Protocol

from ..config import Settings


class WriterState(Protocol):
    messages_saved: int


async def database_writer(
    conn: sqlite3.Connection,
    write_queue: asyncio.Queue,
    state: WriterState,
    settings: Settings,
    on_messages_committed: Callable[[int], None] | None = None,
) -> None:
    pending = 0
    committed_messages = 0

    def commit_pending() -> None:
        nonlocal pending, committed_messages
        conn.commit()
        pending = 0
        if committed_messages:
            state.messages_saved += committed_messages
            if on_messages_committed is not None:
                on_messages_committed(committed_messages)
            committed_messages = 0

    try:
        while True:
            item = await write_queue.get()

            try:
                if item is None:
                    if pending:
                        commit_pending()
                    return

                kind, data = item

                if kind == "chat":
                    _write_chat(conn, data)
                elif kind == "message":
                    if _write_message(conn, data):
                        committed_messages += 1
                elif kind == "message_edit":
                    _write_message_edit(conn, data)
                elif kind == "message_delete":
                    _write_message_delete(conn, data)
                elif kind == "sync_state":
                    _write_sync_state(conn, data)
                else:
                    raise ValueError(f"Unknown write item: {kind}")

                pending += 1
                if pending >= settings.commit_every or write_queue.empty():
                    commit_pending()
                    await asyncio.sleep(0)

            finally:
                write_queue.task_done()
    except BaseException:
        raise


def _write_chat(conn: sqlite3.Connection, data: tuple) -> None:
    conn.execute(
        """
        INSERT INTO chats (
            chat_id, title, username, chat_type, is_bot, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(chat_id) DO UPDATE SET
            title = excluded.title,
            username = excluded.username,
            chat_type = excluded.chat_type,
            is_bot = excluded.is_bot,
            updated_at = excluded.updated_at
        """,
        data,
    )


def _write_message(conn: sqlite3.Connection, data: tuple) -> bool:
    forwarded = data[8] if len(data) > 8 else 0
    forward_source = data[9] if len(data) > 9 else None
    cursor = conn.execute(
        """
        INSERT OR IGNORE INTO messages (
            chat_id,
            message_id,
            sender_id,
            date,
            text,
            reply_to_message_id,
            is_outgoing,
            has_media,
            is_forwarded,
            forward_source
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (*data[:8], forwarded, forward_source),
    )
    inserted = bool(cursor.rowcount)
    if inserted:
        conn.execute(
            "INSERT INTO message_versions(chat_id, message_id, text, captured_at, reason) VALUES (?, ?, ?, datetime('now'), 'initial')",
            (data[0], data[1], data[4]),
        )
    return inserted


def _write_message_edit(conn: sqlite3.Connection, data: tuple) -> None:
    chat_id, message_id, text, edited_at = data
    previous = conn.execute(
        "SELECT text FROM messages WHERE chat_id = ? AND message_id = ?",
        (chat_id, message_id),
    ).fetchone()
    if previous is None:
        return
    if (previous[0] or "") != (text or ""):
        conn.execute(
            "INSERT INTO message_versions(chat_id, message_id, text, captured_at, reason) VALUES (?, ?, ?, ?, 'edited')",
            (chat_id, message_id, previous[0], edited_at),
        )
        _mark_interpretation_stale(conn, chat_id, message_id)
    conn.execute(
        "UPDATE messages SET text=?, edited_at=?, is_deleted=0, deleted_at=NULL WHERE chat_id=? AND message_id=?",
        (text or "", edited_at, chat_id, message_id),
    )


def _write_message_delete(conn: sqlite3.Connection, data: tuple) -> None:
    chat_id, message_id, deleted_at = data
    previous = conn.execute(
        "SELECT text,is_deleted FROM messages WHERE chat_id = ? AND message_id = ?",
        (chat_id, message_id),
    ).fetchone()
    if previous is None or bool(previous[1]):
        return
    conn.execute(
        "INSERT INTO message_versions(chat_id, message_id, text, captured_at, reason) VALUES (?, ?, ?, ?, 'deleted')",
        (chat_id, message_id, previous[0], deleted_at),
    )
    conn.execute(
        "UPDATE messages SET is_deleted=1, deleted_at=? WHERE chat_id=? AND message_id=?",
        (deleted_at, chat_id, message_id),
    )
    _mark_interpretation_stale(conn, chat_id, message_id)


def _mark_interpretation_stale(
    conn: sqlite3.Connection, chat_id: int, message_id: int
) -> None:
    """Invalidate derived interpretation after a committed source mutation."""
    conn.execute(
        "UPDATE ai_message_state SET analysis_stale=1 WHERE chat_id=? AND message_id=?",
        (chat_id, message_id),
    )
    conn.execute(
        "UPDATE message_classifications SET context_stale=1 WHERE chat_id=? AND message_id=?",
        (chat_id, message_id),
    )


def _write_sync_state(conn: sqlite3.Connection, data: tuple) -> None:
    conn.execute(
        """
        INSERT INTO sync_state (
            chat_id,
            bootstrap_complete,
            bootstrap_mode,
            group_total_at_bootstrap,
            last_sync_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(chat_id) DO UPDATE SET
            bootstrap_complete = excluded.bootstrap_complete,
            bootstrap_mode = excluded.bootstrap_mode,
            group_total_at_bootstrap = excluded.group_total_at_bootstrap,
            last_sync_at = excluded.last_sync_at,
            updated_at = excluded.updated_at
        """,
        data,
    )
