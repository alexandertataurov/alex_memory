"""Incremental persistence for derived contact conversation state."""

from __future__ import annotations

import json
import re
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta

from ..utils import utc_now


_TOPIC_WORDS = re.compile(r"[\w-]{3,}", flags=re.UNICODE)
_TOPIC_STOP_WORDS = {
    "about",
    "for",
    "from",
    "have",
    "need",
    "that",
    "this",
    "with",
    "will",
    "what",
    "when",
    "where",
    "which",
    "they",
    "them",
    "your",
    "sender",
    "requested",
    "request",
    "details",
    "detail",
    "message",
    "наш",
    "это",
    "что",
    "как",
    "для",
    "или",
    "его",
    "детали",
    "подробности",
    "the",
    "and",
    "are",
}
_QUESTION_LOOP_CURRENT_DAYS = 90


class ContactContextMaterializer:
    """Maintain derived contact rows from accepted state and bounded evidence."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def refresh_person(self, person_id: int, chat_id: int | None = None) -> int:
        chat_ids = {chat_id} if chat_id is not None else set()
        rows = self.conn.execute(
            """SELECT DISTINCT source_chat_id FROM ai_items
               WHERE person_id=? AND source_chat_id IS NOT NULL
               UNION SELECT DISTINCT source_chat_id FROM tasks
               WHERE related_person_id=? AND source_chat_id IS NOT NULL
               UNION SELECT chat_id FROM chats
               WHERE chat_type='user' AND chat_id=(
                   SELECT telegram_user_id FROM people WHERE person_id=?
               )""",
            (person_id, person_id, person_id),
        ).fetchall()
        chat_ids.update(int(row[0]) for row in rows if row[0] is not None)
        for value in sorted(chat_ids):
            self.refresh_conversation(person_id, value)
        self._refresh_person_state(person_id)
        return len(chat_ids)

    def rebuild_people(self, *, limit: int = 200) -> dict[str, int | bool]:
        """Recompute bounded derived contact state from accepted canonical rows."""
        if not 1 <= limit <= 500:
            raise ValueError(
                "Contact materialization rebuild limit must be 1 through 500"
            )
        rows = self.conn.execute(
            """SELECT person_id FROM people WHERE status<>'merged'
               ORDER BY person_id LIMIT ?""",
            (limit + 1,),
        ).fetchall()
        person_ids = [int(row[0]) for row in rows[:limit]]
        conversations = 0
        with self.conn:
            for person_id in person_ids:
                self._clear_derived_person_state(person_id)
                conversations += self.refresh_person(person_id)
        return {
            "people": len(person_ids),
            "conversations": conversations,
            "truncated": len(rows) > limit,
        }

    def _clear_derived_person_state(self, person_id: int) -> None:
        """Remove only rows that this materializer deterministically owns."""
        self.conn.execute(
            "DELETE FROM conversation_contact_segments WHERE person_id=? AND source='accepted_activity'",
            (person_id,),
        )
        self.conn.execute(
            "DELETE FROM current_conversation_context WHERE person_id=?",
            (person_id,),
        )
        self.conn.execute(
            "DELETE FROM person_project_context WHERE person_id=?",
            (person_id,),
        )
        self.conn.execute(
            """DELETE FROM conversation_open_loops WHERE person_id=?
               AND loop_type IN ('task','question')""",
            (person_id,),
        )
        self.conn.execute(
            """UPDATE person_context_state SET last_contact_at=NULL,current_summary='',
                   long_term_summary='' WHERE person_id=?""",
            (person_id,),
        )

    def store_profile_summary(
        self, person_id: int, summary: str, input_hash: str
    ) -> None:
        """Persist a locally validated presentation summary for one person."""
        now = utc_now()
        self.conn.execute(
            """INSERT INTO person_context_state(person_id,profile_summary,profile_summary_updated_at,
                      profile_summary_input_hash,updated_at)
               VALUES (?,?,?,?,?) ON CONFLICT(person_id) DO UPDATE SET
                 profile_summary=excluded.profile_summary,
                 profile_summary_updated_at=excluded.profile_summary_updated_at,
                 profile_summary_input_hash=excluded.profile_summary_input_hash,
                 updated_at=excluded.updated_at""",
            (person_id, summary, now, input_hash, now),
        )

    def merge_person_state(self, keep_person_id: int, discard_person_id: int) -> None:
        """Move derived person state during a canonical person merge."""
        self.conn.execute(
            """UPDATE OR IGNORE person_context_state SET person_id=?
               WHERE person_id=?""",
            (keep_person_id, discard_person_id),
        )
        self.conn.execute(
            "DELETE FROM person_context_state WHERE person_id=?",
            (discard_person_id,),
        )

    def refresh_conversation(self, person_id: int, chat_id: int) -> None:
        records = self._activity_records(person_id, chat_id)
        now = utc_now()
        self._materialize_segments(person_id, chat_id, records, now)
        self._materialize_open_loops(person_id, chat_id, now)
        self._link_recent_question_answers(person_id, chat_id, now)
        loops = self._open_loops(person_id, chat_id)
        self._materialize_person_project_context(person_id, records, now)
        primary_project = _dominant(records, "project_id")
        primary_company = _dominant(records, "company_id")
        facts = self.conn.execute(
            """SELECT predicate,value_json FROM context_facts
               WHERE subject_type='person' AND subject_id=? AND is_current=1
               ORDER BY valid_from DESC LIMIT 4""",
            (person_id,),
        ).fetchall()
        states = [_fact_text(str(predicate), str(value)) for predicate, value in facts]
        task_states = [f"{loop['status']}: {loop['title']}" for loop in loops[:4]]
        last_at = records[-1]["occurred_at"] if records else None
        evidence_through_at = self.conn.execute(
            """SELECT MAX(occurred_at) FROM (
                   SELECT date AS occurred_at FROM messages WHERE chat_id=?
                   UNION ALL
                   SELECT occurred_at FROM source_evidence
                   WHERE source_name='telegram' AND conversation_id=?
               )""",
            (chat_id, str(chat_id)),
        ).fetchone()[0]
        self.conn.execute(
            """INSERT INTO current_conversation_context(
                   person_id,source_type,conversation_id,chat_id,primary_project_id,
                   primary_company_id,current_state,topic_json,open_loops_json,
                   recent_summary,last_meaningful_at,evidence_through_at,context_version,updated_at
               ) VALUES (?, 'telegram', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
               ON CONFLICT(person_id,source_type,conversation_id) DO UPDATE SET
                   primary_project_id=excluded.primary_project_id,
                   primary_company_id=excluded.primary_company_id,
                   current_state=excluded.current_state,topic_json=excluded.topic_json,
                   open_loops_json=excluded.open_loops_json,recent_summary=excluded.recent_summary,
                   last_meaningful_at=excluded.last_meaningful_at,
                   evidence_through_at=excluded.evidence_through_at,
                   context_version=CASE WHEN
                       current_conversation_context.primary_project_id IS NOT excluded.primary_project_id OR
                       current_conversation_context.primary_company_id IS NOT excluded.primary_company_id OR
                       current_conversation_context.current_state IS NOT excluded.current_state OR
                       current_conversation_context.topic_json IS NOT excluded.topic_json OR
                       current_conversation_context.open_loops_json IS NOT excluded.open_loops_json OR
                       current_conversation_context.recent_summary IS NOT excluded.recent_summary OR
                       current_conversation_context.last_meaningful_at IS NOT excluded.last_meaningful_at
                       THEN current_conversation_context.context_version+1
                       ELSE current_conversation_context.context_version END,
                   updated_at=excluded.updated_at
               WHERE current_conversation_context.primary_project_id IS NOT excluded.primary_project_id OR
                     current_conversation_context.primary_company_id IS NOT excluded.primary_company_id OR
                     current_conversation_context.current_state IS NOT excluded.current_state OR
                     current_conversation_context.topic_json IS NOT excluded.topic_json OR
                     current_conversation_context.open_loops_json IS NOT excluded.open_loops_json OR
                     current_conversation_context.recent_summary IS NOT excluded.recent_summary OR
                     current_conversation_context.last_meaningful_at IS NOT excluded.last_meaningful_at OR
                     current_conversation_context.evidence_through_at IS NOT excluded.evidence_through_at""",
            (
                person_id,
                str(chat_id),
                chat_id,
                primary_project,
                primary_company,
                "; ".join(value for value in [*states, *task_states] if value)[:1800],
                json.dumps(_topics(records)),
                json.dumps(loops, ensure_ascii=False),
                _summary(records[-5:]),
                last_at,
                evidence_through_at,
                now,
            ),
        )

    def _activity_records(self, person_id: int, chat_id: int) -> list[dict]:
        rows = self.conn.execute(
            """SELECT COALESCE(i.source_date,t.created_at),t.related_project_id,t.related_company_id,
                      t.title,t.details,t.status,t.owner,t.source_chat_id,
                      COALESCE(i.source_message_id,0),t.confidence
               FROM tasks AS t LEFT JOIN ai_items AS i ON i.item_id=t.source_item_id
               WHERE t.source_chat_id=? AND (
                   t.related_person_id=? OR EXISTS (
                       SELECT 1 FROM chats AS c JOIN people AS p
                           ON p.telegram_user_id=c.chat_id
                       WHERE c.chat_id=t.source_chat_id AND c.chat_type='user'
                         AND p.person_id=?
                   )
               )
               UNION ALL
               SELECT source_date,project_id,company_id,title,details,status,owner,
                      source_chat_id,source_message_id,confidence
               FROM ai_items AS i WHERE i.source_chat_id=? AND (
                   i.person_id=? OR EXISTS (
                       SELECT 1 FROM chats AS c JOIN people AS p
                           ON p.telegram_user_id=c.chat_id
                       WHERE c.chat_id=i.source_chat_id AND c.chat_type='user'
                         AND p.person_id=?
                   )
               )
               ORDER BY 1, 9""",
            (chat_id, person_id, person_id, chat_id, person_id, person_id),
        ).fetchall()
        records: list[dict] = []
        seen: set[tuple[object, ...]] = set()
        for row in rows:
            key = (row[0], row[3], row[8])
            if key in seen or not row[0]:
                continue
            seen.add(key)
            records.append(
                {
                    "occurred_at": str(row[0]),
                    "project_id": row[1],
                    "company_id": row[2],
                    "title": str(row[3] or ""),
                    "details": str(row[4] or ""),
                    "status": str(row[5] or "informational"),
                    "owner": str(row[6] or "unknown"),
                    "chat_id": row[7],
                    "message_id": row[8],
                    "confidence": float(row[9] or 0.5),
                }
            )
        return records

    def _materialize_segments(
        self, person_id: int, chat_id: int, records: list[dict], now: str
    ) -> None:
        self.conn.execute(
            "DELETE FROM conversation_contact_segments WHERE person_id=? AND source_type='telegram' AND conversation_id=? AND source='accepted_activity'",
            (person_id, str(chat_id)),
        )
        groups: list[list[dict]] = []
        for record in records:
            if not groups or _starts_new_segment(groups[-1], record):
                groups.append([record])
            else:
                groups[-1].append(record)
        for group in groups:
            self.conn.execute(
                """INSERT INTO conversation_contact_segments(
                       person_id,source_type,conversation_id,chat_id,primary_project_id,
                       primary_company_id,started_at,ended_at,topic_json,summary,importance,
                       confidence,source,created_at,updated_at
                   ) VALUES (?, 'telegram', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'accepted_activity', ?, ?)""",
                (
                    person_id,
                    str(chat_id),
                    chat_id,
                    _dominant(group, "project_id"),
                    _dominant(group, "company_id"),
                    group[0]["occurred_at"],
                    _segment_end(group),
                    json.dumps(_topics(group)),
                    _summary(group),
                    max(record["confidence"] for record in group),
                    sum(record["confidence"] for record in group) / len(group),
                    now,
                    now,
                ),
            )

    def _materialize_open_loops(self, person_id: int, chat_id: int, now: str) -> None:
        self.conn.execute(
            """DELETE FROM conversation_open_loops AS loop
               WHERE loop.person_id=? AND loop.source_type='telegram'
                 AND loop.conversation_id=? AND loop.loop_type='task'
                 AND NOT EXISTS (
                     SELECT 1 FROM tasks AS t WHERE t.task_id=loop.task_id
                       AND t.source_chat_id=? AND t.status IN ('open','waiting')
                       AND (t.related_person_id=? OR EXISTS (
                           SELECT 1 FROM chats AS c JOIN people AS p
                             ON p.telegram_user_id=c.chat_id
                            WHERE c.chat_id=t.source_chat_id AND c.chat_type='user'
                              AND p.person_id=?
                       ))
                 )""",
            (person_id, str(chat_id), chat_id, person_id, person_id),
        )
        rows = self.conn.execute(
            """SELECT t.task_id,t.title,t.status,t.owner,t.related_project_id,t.source_chat_id,
                      COALESCE(i.source_message_id,0),t.confidence
               FROM tasks AS t LEFT JOIN ai_items AS i ON i.item_id=t.source_item_id
               WHERE t.source_chat_id=? AND (
                   t.related_person_id=? OR EXISTS (
                       SELECT 1 FROM chats AS c JOIN people AS p
                           ON p.telegram_user_id=c.chat_id
                       WHERE c.chat_id=t.source_chat_id AND c.chat_type='user'
                         AND p.person_id=?
                   )
               )
                 AND t.status IN ('open','waiting') ORDER BY t.updated_at DESC LIMIT 24""",
            (chat_id, person_id, person_id),
        ).fetchall()
        for (
            task_id,
            title,
            status,
            owner,
            project_id,
            source_chat,
            source_message,
            confidence,
        ) in rows:
            self.conn.execute(
                """INSERT INTO conversation_open_loops(
                       person_id,project_id,source_type,conversation_id,loop_type,title,owner,status,
                       task_id,source_chat_id,source_message_id,confidence,created_at,updated_at
                   ) VALUES (?, ?, 'telegram', ?, 'task', ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(person_id,source_type,conversation_id,loop_type,title,source_chat_id,source_message_id)
                   DO UPDATE SET project_id=excluded.project_id,owner=excluded.owner,
                       status=excluded.status,task_id=excluded.task_id,
                       confidence=excluded.confidence,updated_at=excluded.updated_at
                   WHERE conversation_open_loops.project_id IS NOT excluded.project_id OR
                         conversation_open_loops.owner IS NOT excluded.owner OR
                         conversation_open_loops.status IS NOT excluded.status OR
                         conversation_open_loops.task_id IS NOT excluded.task_id OR
                         conversation_open_loops.confidence IS NOT excluded.confidence""",
                (
                    person_id,
                    project_id,
                    str(chat_id),
                    title,
                    owner,
                    status,
                    task_id,
                    source_chat,
                    source_message,
                    confidence,
                    now,
                    now,
                ),
            )

    def _open_loops(self, person_id: int, chat_id: int) -> list[dict]:
        rows = self.conn.execute(
            """SELECT loop_id,loop_type,title,owner,status,project_id,source_chat_id,source_message_id,
                      confidence FROM conversation_open_loops
               WHERE person_id=? AND source_type='telegram' AND conversation_id=? AND status IN ('open','waiting')
               ORDER BY updated_at DESC LIMIT 12""",
            (person_id, str(chat_id)),
        ).fetchall()
        return [
            {
                "loop_id": row[0],
                "loop_type": row[1],
                "title": row[2],
                "owner": row[3],
                "status": row[4],
                "project_id": row[5],
                "source_chat_id": row[6],
                "source_message_id": row[7],
                "confidence": row[8],
            }
            for row in rows
        ]

    def _link_recent_question_answers(
        self, person_id: int, chat_id: int, now: str
    ) -> None:
        rows = self.conn.execute(
            """SELECT message_id,date,text,is_outgoing FROM messages WHERE chat_id=?
               AND TRIM(COALESCE(text,''))<>'' AND COALESCE(is_deleted,0)=0
               ORDER BY date DESC,message_id DESC LIMIT 120""",
            (chat_id,),
        ).fetchall()
        chronological = list(reversed(rows))
        for index, (message_id, _, text, is_outgoing) in enumerate(chronological):
            text = str(text or "")
            if not _is_operational_question(text):
                continue
            self.conn.execute(
                """INSERT OR IGNORE INTO conversation_open_loops(
                       person_id,source_type,conversation_id,loop_type,title,owner,status,
                       source_chat_id,source_message_id,confidence,created_at,updated_at
                   ) VALUES (?, 'telegram', ?, 'question', ?, ?, 'waiting', ?, ?, 0.6, ?, ?)""",
                (
                    person_id,
                    str(chat_id),
                    _question_title(text),
                    "other" if is_outgoing else "me",
                    chat_id,
                    message_id,
                    now,
                    now,
                ),
            )
            if index + 1 >= len(chronological):
                continue
            reply_id, _, reply_text, reply_outgoing = chronological[index + 1]
            if bool(reply_outgoing) != bool(is_outgoing) and _supports_question(
                text, str(reply_text or "")
            ):
                self.conn.execute(
                    """INSERT OR IGNORE INTO conversation_context_links(
                           person_id,link_type,from_chat_id,from_message_id,to_chat_id,to_message_id,
                           confidence,source,created_at
                       ) VALUES (?, 'question_answer', ?, ?, ?, ?, 0.7, 'adjacent_substantive_reply', ?)""",
                    (person_id, chat_id, message_id, chat_id, reply_id, now),
                )
                self.conn.execute(
                    """UPDATE conversation_open_loops SET status='resolved',resolved_by_chat_id=?,
                           resolved_by_message_id=?,updated_at=? WHERE person_id=? AND source_type='telegram'
                           AND conversation_id=? AND loop_type='question' AND source_chat_id=?
                           AND source_message_id=? AND status IN ('open','waiting')""",
                    (
                        chat_id,
                        reply_id,
                        now,
                        person_id,
                        str(chat_id),
                        chat_id,
                        message_id,
                    ),
                )
        cutoff = (
            datetime.fromisoformat(now.replace("Z", "+00:00"))
            - timedelta(days=_QUESTION_LOOP_CURRENT_DAYS)
        ).isoformat()
        self.conn.execute(
            """UPDATE conversation_open_loops AS loop SET status='resolved',updated_at=?
               WHERE loop.person_id=? AND loop.source_type='telegram' AND loop.conversation_id=?
                 AND loop.loop_type='question' AND loop.status IN ('open','waiting')
                 AND EXISTS (
                     SELECT 1 FROM messages AS m WHERE m.chat_id=loop.source_chat_id
                       AND m.message_id=loop.source_message_id AND m.date<?
                 )""",
            (now, person_id, str(chat_id), cutoff),
        )

    def _materialize_person_project_context(
        self, person_id: int, records: list[dict], now: str
    ) -> None:
        grouped: dict[int, list[dict]] = defaultdict(list)
        for record in records:
            if record["project_id"] is not None:
                grouped[int(record["project_id"])].append(record)
        for project_id, items in grouped.items():
            open_count = self.conn.execute(
                "SELECT COUNT(*) FROM tasks WHERE related_person_id=? AND related_project_id=? AND status IN ('open','waiting')",
                (person_id, project_id),
            ).fetchone()[0]
            self.conn.execute(
                """INSERT INTO person_project_context(
                       person_id,project_id,status,first_activity_at,last_activity_at,current_summary,
                       long_term_summary,confidence,updated_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(person_id,project_id) DO UPDATE SET status=excluded.status,
                       first_activity_at=MIN(person_project_context.first_activity_at,excluded.first_activity_at),
                       last_activity_at=excluded.last_activity_at,current_summary=excluded.current_summary,
                       long_term_summary=excluded.long_term_summary,confidence=excluded.confidence,
                       updated_at=excluded.updated_at""",
                (
                    person_id,
                    project_id,
                    "active" if open_count else "historical",
                    items[0]["occurred_at"],
                    items[-1]["occurred_at"],
                    _summary(items[-4:]),
                    _summary(items),
                    sum(item["confidence"] for item in items) / len(items),
                    now,
                ),
            )

    def _refresh_person_state(self, person_id: int) -> None:
        now = utc_now()
        rows = self.conn.execute(
            """SELECT current_state,recent_summary,last_meaningful_at FROM current_conversation_context
               WHERE person_id=? ORDER BY last_meaningful_at DESC LIMIT 4""",
            (person_id,),
        ).fetchall()
        projects = ", ".join(
            str(row[0])
            for row in self.conn.execute(
                """SELECT p.canonical_name FROM person_project_context AS ppc
                   JOIN projects AS p ON p.project_id=ppc.project_id WHERE ppc.person_id=?
                   ORDER BY ppc.last_activity_at DESC LIMIT 6""",
                (person_id,),
            )
        )
        known_since = self.conn.execute(
            """SELECT MIN(value) FROM (
                   SELECT MIN(source_date) AS value FROM ai_items WHERE person_id=?
                   UNION ALL SELECT MIN(created_at) FROM tasks WHERE related_person_id=?
               ) WHERE value IS NOT NULL""",
            (person_id, person_id),
        ).fetchone()[0]
        current = " ".join(
            str(row[0] or row[1] or "") for row in rows if row[0] or row[1]
        )[:3000]
        long_term = " ".join(
            part
            for part in (
                f"Known since {str(known_since)[:10]}." if known_since else "",
                f"Projects: {projects}." if projects else "",
            )
            if part
        )[:3000]
        last_contact = max((str(row[2]) for row in rows if row[2]), default=None)
        self.conn.execute(
            """INSERT INTO person_context_state(person_id,last_contact_at,current_summary,long_term_summary,updated_at)
               VALUES (?, ?, ?, ?, ?) ON CONFLICT(person_id) DO UPDATE SET
                   last_contact_at=excluded.last_contact_at,current_summary=excluded.current_summary,
                   long_term_summary=CASE WHEN excluded.long_term_summary<>'' THEN excluded.long_term_summary
                                          ELSE person_context_state.long_term_summary END,
                   updated_at=excluded.updated_at""",
            (person_id, last_contact, current, long_term, now),
        )


def _starts_new_segment(previous: list[dict], current: dict) -> bool:
    last = previous[-1]
    if (
        last["project_id"] is not None
        and current["project_id"] is not None
        and last["project_id"] != current["project_id"]
    ):
        return True
    try:
        before = datetime.fromisoformat(str(last["occurred_at"]).replace("Z", "+00:00"))
        after = datetime.fromisoformat(
            str(current["occurred_at"]).replace("Z", "+00:00")
        )
        return after - before > timedelta(days=90)
    except ValueError:
        return False


def _segment_end(items: list[dict]) -> str | None:
    try:
        last = datetime.fromisoformat(
            str(items[-1]["occurred_at"]).replace("Z", "+00:00")
        )
    except ValueError:
        return None
    return (last + timedelta(days=90)).isoformat()


def _dominant(records: list[dict], key: str) -> int | None:
    values = [int(record[key]) for record in records if record.get(key) is not None]
    return (
        max(
            set(values),
            key=lambda value: (values.count(value), values[::-1].index(value)),
        )
        if values
        else None
    )


def _topics(records: list[dict]) -> list[str]:
    counts: dict[str, int] = defaultdict(int)
    for record in records:
        for word in _TOPIC_WORDS.findall(f"{record['title']} {record['details']}"):
            normalized = word.casefold()
            if normalized not in _TOPIC_STOP_WORDS and not normalized.isdigit():
                counts[normalized] += 1
    return [
        word
        for word, _ in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:10]
    ]


def _summary(records: list[dict]) -> str:
    values: list[str] = []
    for record in records:
        text = " ".join(str(record["title"] or "").split())
        if text and text not in values:
            values.append(text)
    return "; ".join(values[-6:])[:1800]


def _fact_text(predicate: str, value_json: str) -> str:
    try:
        value = json.loads(value_json)
    except json.JSONDecodeError:
        return predicate.replace("_", " ")
    return (
        f"{predicate.replace('_', ' ')}: {value['status']}"
        if isinstance(value, dict) and value.get("status")
        else predicate.replace("_", " ")
    )


def _is_operational_question(text: str) -> bool:
    lowered = text.casefold()
    return "?" in text and any(
        word in lowered
        for word in (
            "rate",
            "price",
            "document",
            "docs",
            "meeting",
            "proceed",
            "contract",
            "payment",
            "send",
            "confirm",
            "ставк",
            "документ",
            "встреч",
            "можем",
        )
    )


def _supports_question(question: str, answer: str) -> bool:
    """Return whether an adjacent reply carries enough evidence to resolve a question."""
    answer_terms = {
        term.casefold()
        for term in _TOPIC_WORDS.findall(answer)
        if not term.isdigit() and term.casefold() not in _TOPIC_STOP_WORDS
    }
    question_terms = {
        term.casefold()
        for term in _TOPIC_WORDS.findall(question)
        if not term.isdigit() and term.casefold() not in _TOPIC_STOP_WORDS
    }
    if len(answer_terms) < 2:
        return False
    has_number = bool(re.search(r"\d+(?:[.,]\d+)?\s*%", answer))
    return has_number or bool(question_terms & answer_terms)


def _question_title(text: str) -> str:
    return " ".join(text.split())[:300]
