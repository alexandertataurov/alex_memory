from __future__ import annotations

import sqlite3
from datetime import datetime

from ..config import Settings
from ..utils import utc_now
from .builder import ContextBuilder
from .models import ContextRequest
from .repository import add_event, ensure_relationship, set_temporal_fact
from .temporal import resolve_temporal_expressions


class ContextService:
    def __init__(self, conn: sqlite3.Connection, settings: Settings):
        self.conn, self.settings = conn, settings
        self.builder = ContextBuilder(conn, settings)

    def process_ai_item(
        self,
        item: tuple,
        person_id: int | None,
        company_id: int | None,
        project_id: int | None,
    ) -> None:
        (
            item_id,
            kind,
            title,
            details,
            status,
            owner,
            due_date,
            confidence,
            chat_id,
            source_message_id,
            source_date,
        ) = item
        event_type = _event_type(kind, status)
        if event_type is not None:
            add_event(
                self.conn,
                event_type=event_type,
                title=title,
                description=details,
                occurred_at=source_date or utc_now(),
                person_id=person_id,
                company_id=company_id,
                project_id=project_id,
                source_chat_id=chat_id,
                source_message_id=source_message_id,
                source_ai_item_id=item_id,
                confidence=confidence,
            )
        if person_id and project_id:
            ensure_relationship(
                self.conn,
                "person",
                person_id,
                "project",
                project_id,
                "involved_in",
                confidence,
                chat_id,
                source_message_id,
            )
        if company_id and project_id:
            ensure_relationship(
                self.conn,
                "company",
                company_id,
                "project",
                project_id,
                "involved_in",
                confidence,
                chat_id,
                source_message_id,
            )
        if project_id and kind in {
            "task",
            "follow_up",
            "deadline",
            "promise_by_me",
            "promise_to_me",
        }:
            predicate = "project_work_status"
            set_temporal_fact(
                self.conn,
                subject_type="project",
                subject_id=project_id,
                predicate=predicate,
                value={"status": status, "title": title},
                valid_from=source_date or utc_now(),
                confidence=confidence,
                source_chat_id=chat_id,
                source_message_id=source_message_id,
                source_ai_item_id=item_id,
            )
        if person_id and "document" in f"{title} {details}".casefold():
            state = (
                "received"
                if status == "done" or "received" in f"{title} {details}".casefold()
                else "requested"
                if status in {"open", "waiting"}
                else "discussed"
            )
            set_temporal_fact(
                self.conn,
                subject_type="person",
                subject_id=person_id,
                predicate="corporate_documents_status",
                value={"status": state},
                valid_from=source_date or utc_now(),
                confidence=confidence,
                source_chat_id=chat_id,
                source_message_id=source_message_id,
                source_ai_item_id=item_id,
            )

    def process_batch_temporal(self, batch_id: int) -> None:
        rows = self.conn.execute(
            "SELECT m.chat_id,m.message_id,m.text,m.date FROM messages m JOIN ai_message_state a ON a.chat_id=m.chat_id AND a.message_id=m.message_id WHERE a.batch_id=?",
            (batch_id,),
        ).fetchall()
        for chat_id, message_id, text, message_at in rows:
            for resolution in resolve_temporal_expressions(
                text or "", message_at, self.settings.app_timezone
            ):
                self.conn.execute(
                    "INSERT OR IGNORE INTO temporal_resolutions(chat_id,message_id,raw_expression,resolved_at,resolution_type,dependency_type,resolution_confidence,created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        chat_id,
                        message_id,
                        resolution["raw_expression"],
                        resolution["resolved_at"],
                        resolution["resolution_type"],
                        resolution["dependency_type"],
                        resolution["resolution_confidence"],
                        utc_now(),
                    ),
                )

    def snapshot_global_state(self, as_of: datetime | None = None) -> dict:
        context = self.builder.build(
            ContextRequest(
                purpose="global_state",
                as_of=as_of,
                include_raw_evidence=False,
            )
        )
        rendered = context.render(self.settings.context_max_chars)
        timestamp = context.as_of[:10]
        self.conn.execute(
            "INSERT INTO global_state_snapshots(as_of,state_json,summary,created_at) VALUES (?, ?, ?, ?) ON CONFLICT(as_of) DO UPDATE SET state_json=excluded.state_json,summary=excluded.summary,created_at=excluded.created_at",
            (
                timestamp,
                rendered,
                f"{context.global_state['open_tasks']} open tasks; {context.global_state['at_risk_projects']} at-risk projects",
                utc_now(),
            ),
        )
        return context.global_state

    def get_person_context(self, person_id: int, as_of: datetime | None = None):
        return self.builder.build(
            ContextRequest(
                purpose="person_profile", as_of=as_of, person_ids=[person_id]
            )
        )

    def get_project_context(self, project_id: int, as_of: datetime | None = None):
        return self.builder.build(
            ContextRequest(
                purpose="project_profile", as_of=as_of, project_ids=[project_id]
            )
        )

    def get_company_context(self, company_id: int, as_of: datetime | None = None):
        return self.builder.build(
            ContextRequest(
                purpose="company_profile", as_of=as_of, company_ids=[company_id]
            )
        )

    def get_global_context(self, as_of: datetime | None = None):
        return self.builder.build(
            ContextRequest(
                purpose="global_state", as_of=as_of, include_raw_evidence=False
            )
        )

    def build_context_for_query(self, query: str, as_of: datetime | None = None):
        return self.builder.build(
            ContextRequest(purpose="ask_memory", query=query, as_of=as_of)
        )


def _event_type(kind: str, status: str) -> str | None:
    if kind.startswith("promise"):
        return "promise_completed" if status == "done" else "promise_created"
    if kind in {"task", "follow_up", "deadline"}:
        return "task_completed" if status == "done" else "task_created"
    if kind == "payment":
        return "payment_discussed"
    if kind == "project":
        return "project_blocked" if status == "waiting" else "project_updated"
    return None
