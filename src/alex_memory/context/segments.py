"""Derived, time-bounded project segments for Telegram conversations."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

from ..utils import utc_now


class ConversationSegmenter:
    """Materialize task-anchored project periods without assigning a whole chat."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def rebuild_chat(self, chat_id: int) -> int:
        """Rebuild derived segments from dated project-linked task evidence.

        The source task's extracted message date wins over task creation time.
        Consecutive anchors for the same project become one period; a later return
        to that project becomes a distinct period. Only derived rows are replaced.
        """
        rows = self.conn.execute(
            """SELECT t.task_id,t.related_project_id,COALESCE(i.source_date,t.created_at),
                      i.source_message_id,t.source_item_id
               FROM tasks AS t LEFT JOIN ai_items AS i ON i.item_id=t.source_item_id
               WHERE t.source_chat_id=? AND t.related_project_id IS NOT NULL
               ORDER BY COALESCE(i.source_date,t.created_at),t.task_id""",
            (chat_id,),
        ).fetchall()
        anchors = [
            (
                int(project_id),
                str(occurred_at),
                f"message:{message_id}"
                if message_id is not None
                else f"item:{source_item_id}"
                if source_item_id is not None
                else f"task:{task_id}",
            )
            for task_id, project_id, occurred_at, message_id, source_item_id in rows
        ]
        periods: list[tuple[int, str, str, set[str]]] = []
        for project_id, occurred_at, anchor_key in anchors:
            if (
                periods
                and periods[-1][0] == project_id
                and _within_active_period(periods[-1][2], occurred_at)
            ):
                current_project, started_at, _, anchor_keys = periods[-1]
                periods[-1] = (
                    current_project,
                    started_at,
                    occurred_at,
                    anchor_keys | {anchor_key},
                )
            else:
                periods.append((project_id, occurred_at, occurred_at, {anchor_key}))
        now = utc_now()
        self.conn.execute(
            "DELETE FROM conversation_segments WHERE chat_id=? AND source='task_anchors'",
            (chat_id,),
        )
        for index, (project_id, started_at, last_at, anchor_keys) in enumerate(periods):
            next_start = periods[index + 1][1] if index + 1 < len(periods) else None
            ended_at = _segment_end(last_at, next_start)
            self.conn.execute(
                """INSERT INTO conversation_segments(
                       chat_id,project_id,started_at,ended_at,anchor_count,confidence,
                       source,created_at,updated_at
                   ) VALUES (?,?,?,?,?,?,'task_anchors',?,?)""",
                (
                    chat_id,
                    project_id,
                    started_at,
                    ended_at,
                    len(anchor_keys),
                    0.95 if len(anchor_keys) >= 2 else 0.75,
                    now,
                    now,
                ),
            )
        return len(periods)

    def rebuild_chats(self, chat_ids: set[int]) -> int:
        return sum(self.rebuild_chat(chat_id) for chat_id in sorted(chat_ids))


def active_segment_project(
    conn: sqlite3.Connection, chat_id: int, occurred_at: str | None
) -> int | None:
    if not occurred_at:
        return None
    row = conn.execute(
        """SELECT project_id FROM conversation_segments
           WHERE chat_id=? AND started_at<=? AND (ended_at IS NULL OR ended_at>?)
           ORDER BY confidence DESC,anchor_count DESC,started_at DESC LIMIT 1""",
        (chat_id, occurred_at, occurred_at),
    ).fetchone()
    return int(row[0]) if row else None


def _segment_end(last_at: str, next_start: str | None) -> str | None:
    """Bound an inactive period instead of treating a historic chat topic as eternal."""
    try:
        expiry = (
            datetime.fromisoformat(last_at.replace("Z", "+00:00")) + timedelta(days=90)
        ).isoformat()
    except ValueError:
        return next_start
    if next_start is None:
        return expiry
    return min(expiry, next_start)


def _within_active_period(previous_at: str, occurred_at: str) -> bool:
    """Keep a project period contiguous only across the documented 90-day bound."""
    try:
        previous = datetime.fromisoformat(previous_at.replace("Z", "+00:00"))
        current = datetime.fromisoformat(occurred_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    return current <= previous + timedelta(days=90)
