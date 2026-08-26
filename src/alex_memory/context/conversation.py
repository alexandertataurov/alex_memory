"""Bounded contact-conversation queries and AI context packages."""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from ..config import Settings
from .builder import ContextBuilder
from .contact_materializer import ContactContextMaterializer
from .models import ContextRequest


_WORDS = re.compile(r"[\w-]{3,}", flags=re.UNICODE)


class ConversationContextService:
    """Compose contact state into bounded retrieval and extraction context."""

    def __init__(self, conn: sqlite3.Connection, settings: Settings | None):
        self.conn, self.settings = conn, settings
        self.materializer = ContactContextMaterializer(conn)

    def refresh_person(self, person_id: int, chat_id: int | None = None) -> int:
        """Refresh only the materialized conversations connected to this person."""
        return self.materializer.refresh_person(person_id, chat_id)

    def refresh_conversation(self, person_id: int, chat_id: int) -> None:
        self.materializer.refresh_conversation(person_id, chat_id)

    def build_for_conversation(
        self,
        *,
        person_id: int,
        conversation_id: str | int,
        new_messages: Sequence[object] | None = None,
        as_of: datetime | None = None,
    ) -> dict[str, Any]:
        """Build the standard bounded semantic-analysis package for one contact."""
        if self.settings is None:
            raise RuntimeError(
                "Conversation context rendering requires application settings"
            )
        conversation_key = str(conversation_id)
        conversation = self._conversation(person_id, conversation_key)
        if conversation["chat_id"] is None:
            try:
                self.refresh_conversation(person_id, int(conversation_id))
            except ValueError:
                pass
            conversation = self._conversation(person_id, conversation_key)
        if as_of is not None:
            conversation = self._historical_conversation(
                person_id, conversation_key, as_of, conversation
            )
        context = ContextBuilder(self.conn, self.settings).build(
            ContextRequest(
                purpose="message_analysis",
                chat_id=conversation.get("chat_id"),
                person_ids=[person_id],
                project_ids=[conversation["primary_project_id"]]
                if conversation.get("primary_project_id")
                else [],
                as_of=as_of,
                include_raw_evidence=True,
            )
        )
        return {
            "context": context,
            "conversation": conversation,
            "project_contexts": self._project_contexts(person_id),
            "new_message_count": len(new_messages or []),
        }

    def render_for_analysis(self, package: dict[str, Any], max_chars: int) -> str:
        """Render background with no reusable evidence citations."""
        conversation = package["conversation"]
        lines = ["CONTACT CONVERSATION CONTEXT:"]
        if conversation.get("current_state"):
            lines.append("CURRENT STATE: " + conversation["current_state"])
        if conversation.get("topics"):
            lines.append("CURRENT TOPICS: " + ", ".join(conversation["topics"][:8]))
        if conversation.get("open_loops"):
            lines.append("OPEN LOOPS:")
            lines.extend(
                f"- {loop['status']}: {loop['title']} ({loop['owner']})"
                for loop in conversation["open_loops"][:5]
            )
        if conversation.get("recent_summary"):
            lines.append("RECENT CONVERSATION: " + conversation["recent_summary"])
        lines.extend(
            f"PROJECT: {pair['project_name']} ({pair['status']}) — {pair['summary']}"
            for pair in package["project_contexts"][:3]
        )
        rendered = "\n".join(lines)
        base = package["context"].render_for_analysis(
            max(400, max_chars - len(rendered))
        )
        return (rendered + "\n\n" + base)[:max_chars]

    def timeline(
        self, person_id: int, as_of: datetime | None = None
    ) -> list[dict[str, Any]]:
        """Return a deduplicated, source-grounded contact timeline."""
        cutoff = as_of.isoformat() if as_of else "9999-12-31T23:59:59+00:00"
        rows = self.conn.execute(
            """SELECT occurred_at,title,description,source_chat_id,source_message_id,'event',event_id
               FROM context_events WHERE person_id=? AND occurred_at<=?
               UNION ALL
               SELECT updated_at,title,details,source_chat_id,NULL,'task',task_id
               FROM tasks WHERE related_person_id=? AND updated_at<=?
               UNION ALL
               SELECT date,text,'',chat_id,message_id,'message',message_id
               FROM messages WHERE chat_id IN (
                   SELECT chat_id FROM current_conversation_context WHERE person_id=?
               ) AND date<=? AND COALESCE(is_deleted,0)=0
                 AND message_id IN (
                   SELECT message_id FROM message_classifications
                   WHERE chat_id=messages.chat_id AND importance IN ('high','critical')
                 )
               ORDER BY 1 DESC LIMIT 100""",
            (person_id, cutoff, person_id, cutoff, person_id, cutoff),
        ).fetchall()
        seen: set[tuple[str, str]] = set()
        timeline: list[dict[str, Any]] = []
        for (
            occurred_at,
            title,
            details,
            source_chat,
            source_message,
            kind,
            source_id,
        ) in rows:
            key = (str(occurred_at)[:10], _normal(str(title)))
            if key not in seen:
                seen.add(key)
                timeline.append(
                    {
                        "occurred_at": occurred_at,
                        "title": title,
                        "details": details,
                        "kind": kind,
                        "source_chat_id": source_chat,
                        "source_message_id": source_message,
                        "source_id": source_id,
                    }
                )
        return timeline

    def _conversation(self, person_id: int, conversation_id: str) -> dict[str, Any]:
        row = self.conn.execute(
            """SELECT chat_id,primary_project_id,primary_company_id,current_state,topic_json,
                      open_loops_json,recent_summary,last_meaningful_at,context_version,updated_at
               FROM current_conversation_context
               WHERE person_id=? AND source_type='telegram' AND conversation_id=?""",
            (person_id, conversation_id),
        ).fetchone()
        return _conversation_row(row)

    def _historical_conversation(
        self,
        person_id: int,
        conversation_id: str,
        as_of: datetime,
        current: dict[str, Any],
    ) -> dict[str, Any]:
        row = self.conn.execute(
            """SELECT primary_project_id,primary_company_id,topic_json,summary,started_at,ended_at
               FROM conversation_contact_segments WHERE person_id=? AND source_type='telegram'
                 AND conversation_id=? AND started_at<=?
               ORDER BY started_at DESC LIMIT 1""",
            (person_id, conversation_id, as_of.isoformat()),
        ).fetchone()
        if row is None:
            return current
        try:
            topics = json.loads(row[2])
        except (TypeError, json.JSONDecodeError):
            topics = []
        return {
            **current,
            "primary_project_id": row[0],
            "primary_company_id": row[1],
            "topics": topics,
            "current_state": row[3],
            "recent_summary": row[3],
            "last_meaningful_at": row[5] or row[4],
            "open_loops": [],
        }

    def _project_contexts(self, person_id: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """SELECT ppc.project_id,p.canonical_name,ppc.status,ppc.current_summary,
                      ppc.last_activity_at,ppc.confidence
               FROM person_project_context AS ppc JOIN projects AS p ON p.project_id=ppc.project_id
               WHERE ppc.person_id=? ORDER BY ppc.last_activity_at DESC LIMIT 6""",
            (person_id,),
        ).fetchall()
        return [
            {
                "project_id": row[0],
                "project_name": row[1],
                "status": row[2],
                "summary": row[3],
                "last_activity_at": row[4],
                "confidence": row[5],
            }
            for row in rows
        ]


def _conversation_row(row: tuple | None) -> dict[str, Any]:
    if row is None:
        return {
            "chat_id": None,
            "primary_project_id": None,
            "primary_company_id": None,
            "current_state": "",
            "topics": [],
            "open_loops": [],
            "recent_summary": "",
        }
    try:
        topics, loops = json.loads(row[4]), json.loads(row[5])
    except (TypeError, json.JSONDecodeError):
        topics, loops = [], []
    return {
        "chat_id": row[0],
        "primary_project_id": row[1],
        "primary_company_id": row[2],
        "current_state": row[3],
        "topics": topics,
        "open_loops": loops,
        "recent_summary": row[6],
        "last_meaningful_at": row[7],
        "context_version": row[8],
        "updated_at": row[9],
    }


def _normal(text: str) -> str:
    return " ".join(_WORDS.findall(text.casefold()))[:220]
