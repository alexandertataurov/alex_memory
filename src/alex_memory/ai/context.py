"""Bounded background assembly for AI job prompts.

This module owns prompt-only context. Durable job state remains in
``ai.repository`` and canonical context remains in ``context``.
"""

from __future__ import annotations

import sqlite3

from ..config import Settings
from ..models import AIBatch, AIMessage
from .batching import format_ai_context_message


_OPTIONAL_ANALYSIS_CONTEXT_CHARS = 2_000


def add_history_context(
    conn: sqlite3.Connection, batch: AIBatch, settings: Settings
) -> AIBatch:
    """Add a small prior-message window without making it citeable evidence."""
    first_id = min(message.message_id for message in batch.messages)
    rows = conn.execute(
        """SELECT m.chat_id, m.message_id, m.sender_id, m.date, m.text,
                  m.is_outgoing, COALESCE(c.title, CAST(m.chat_id AS TEXT)),
                  COALESCE(c.chat_type, 'unknown')
           FROM messages AS m LEFT JOIN chats AS c ON c.chat_id = m.chat_id
           WHERE m.chat_id = ? AND m.message_id < ? AND TRIM(COALESCE(m.text, '')) <> ''
             AND COALESCE(m.is_deleted, 0) = 0
           ORDER BY m.message_id DESC LIMIT ?""",
        (batch.chat_id, first_id, settings.ai_context_messages),
    ).fetchall()
    if not rows:
        return batch
    parts: list[str] = []
    context_chars = 0
    for row in rows:
        formatted = format_ai_context_message(_message_from_row(row), settings)
        if parts and context_chars + len(formatted) > _OPTIONAL_ANALYSIS_CONTEXT_CHARS:
            break
        parts.append(formatted)
        context_chars += len(formatted)
    prompt = (
        batch.prompt
        + "\n\n<CONTEXT_ONLY>\n"
        + "\n\n".join(reversed(parts))
        + "\n</CONTEXT_ONLY>\nUse context only for interpretation; cite source IDs from the main message window only."
    )
    return AIBatch(batch.chat_id, batch.chat_title, batch.messages, prompt)


def add_contextual_preamble(
    conn: sqlite3.Connection, batch: AIBatch, settings: Settings
) -> AIBatch:
    """Supply compact canonical/contact background before extraction."""
    from ..context import ContextBuilder, ContextRequest, ConversationContextService

    query = " ".join(message.text for message in batch.messages)[-1500:]
    context = ContextBuilder(conn, settings).build(
        ContextRequest(
            purpose="message_analysis",
            query=query,
            chat_id=batch.chat_id,
            include_raw_evidence=True,
        )
    )
    budget = min(
        settings.context_max_chars,
        max(1000, settings.ai_batch_chars),
        _OPTIONAL_ANALYSIS_CONTEXT_CHARS,
    )
    rendered = context.render_for_analysis(budget)
    chat_type = conn.execute(
        "SELECT chat_type FROM chats WHERE chat_id=?", (batch.chat_id,)
    ).fetchone()
    people: set[int]
    if chat_type is not None and chat_type[0] == "user":
        from ..operational import direct_chat_person

        peer_id = direct_chat_person(conn, batch.chat_id)
        people = {peer_id} if peer_id is not None else set()
    else:
        people = _resolved_contact_ids(conn, batch.chat_id)
    if len(people) == 1:
        service = ConversationContextService(conn, settings)
        package = service.build_for_conversation(
            person_id=next(iter(people)),
            conversation_id=batch.chat_id,
            new_messages=batch.messages,
        )
        rendered = service.render_for_analysis(package, budget)
    if not rendered:
        return batch
    prompt = (
        "<MEMORY_CONTEXT>\n"
        + rendered
        + "\n</MEMORY_CONTEXT>\n"
        + "Memory context is background only. Create observations only when supported "
        + "by the NEW <MESSAGE> window below; do not repeat background as new evidence. "
        + "Use it only to resolve references, projects, commitments, and meaning.\n\n"
        + batch.prompt
    )
    return AIBatch(batch.chat_id, batch.chat_title, batch.messages, prompt)


def _resolved_contact_ids(conn: sqlite3.Connection, chat_id: int) -> set[int]:
    return {
        int(row[0])
        for row in conn.execute(
            """SELECT person_id FROM ai_items WHERE source_chat_id=? AND person_id IS NOT NULL
               UNION SELECT related_person_id FROM tasks
               WHERE source_chat_id=? AND related_person_id IS NOT NULL""",
            (chat_id, chat_id),
        ).fetchall()
    }


def _message_from_row(row: tuple) -> AIMessage:
    return AIMessage(
        int(row[0]),
        int(row[1]),
        int(row[2]) if row[2] is not None else None,
        row[3],
        row[4] or "",
        bool(row[5]),
        row[6] or str(row[0]),
        row[7] or "unknown",
    )
