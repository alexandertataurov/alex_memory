"""Persist explicit, enforceable per-chat analysis policy."""

from __future__ import annotations

import sqlite3

from .utils import utc_now


_ALIASES = {
    "auto": "auto",
    "full": "include",
    "include": "include",
    "archive_only": "classify_only",
    "classify_only": "classify_only",
    "news_only": "news_only",
    "ignore": "exclude",
    "exclude": "exclude",
}


def set_chat_policy(
    conn: sqlite3.Connection, chat_id: int, mode: str, reason: str = ""
) -> None:
    """Save a user-facing alias as the canonical routing mode."""
    normalized_mode = _ALIASES.get(mode.strip().lower())
    if normalized_mode is None:
        raise ValueError("invalid AI chat policy")
    conn.execute(
        """INSERT INTO chat_ai_policy(chat_id,mode,reason,updated_at)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(chat_id) DO UPDATE SET
               mode=excluded.mode,reason=excluded.reason,updated_at=excluded.updated_at""",
        (chat_id, normalized_mode, reason, utc_now()),
    )
