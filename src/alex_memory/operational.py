"""Deterministic operational layer built on top of immutable AI findings.

AI output remains evidence. This module only creates canonical records when a
confidence policy and unambiguous entity match permit it; uncertain work is
placed in ``review_queue`` rather than silently changing a user's task list.
"""

from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from datetime import date
from difflib import SequenceMatcher

from .config import Settings
from .utils import utc_now


TASK_KINDS = {"task", "follow_up", "deadline", "promise_by_me", "promise_to_me"}
DURABLE_KINDS = {"important_fact", "project", "payment", "commitment"}
_INFORMATION_SCOPES = {
    "personal",
    "private_group",
    "business",
    "project",
    "public_information",
    "external_news",
}
_CONTENT_TYPES = {
    "conversation",
    "decision",
    "information",
    "meeting",
    "news",
    "payment",
    "promise",
    "question",
    "request",
    "spam",
    "update",
}


def normalize_alias(value: str | None) -> str:
    """Unicode-safe deterministic identity key; intentionally conservative."""
    value = unicodedata.normalize("NFKC", value or "").casefold().strip()
    value = value.lstrip("@")
    return re.sub(r"\s+", " ", value)


def normalize_task_title(value: str | None) -> str:
    value = normalize_alias(value)
    return re.sub(r"[^\w\s]", "", value, flags=re.UNICODE).strip()


def _source_day(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


class EntityResolver:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def person(
        self,
        name: str | None,
        *,
        telegram_user_id: int | None = None,
        telegram_username: str | None = None,
        source: str = "ai",
        confidence: float = 1.0,
    ) -> int | None:
        if not name and not telegram_user_id and not telegram_username:
            return None
        now = utc_now()
        if telegram_user_id is not None:
            row = self.conn.execute(
                "SELECT person_id FROM people WHERE telegram_user_id = ?",
                (telegram_user_id,),
            ).fetchone()
            if row:
                return int(row[0])
        username_key = normalize_alias(telegram_username)
        if username_key:
            rows = self.conn.execute(
                "SELECT entity_id FROM entity_aliases WHERE entity_type = 'person' AND normalized_alias = ?",
                (username_key,),
            ).fetchall()
            ids = sorted({int(row[0]) for row in rows})
            if len(ids) == 1:
                return ids[0]
            if len(ids) > 1:
                self._ambiguous(
                    "person",
                    username_key,
                    ids,
                    "username alias maps to multiple people",
                )
                return None
        alias = normalize_alias(name)
        if alias:
            rows = self.conn.execute(
                "SELECT entity_id FROM entity_aliases WHERE entity_type = 'person' AND normalized_alias = ?",
                (alias,),
            ).fetchall()
            ids = sorted({int(row[0]) for row in rows})
            if len(ids) == 1:
                return ids[0]
            if len(ids) > 1:
                self._ambiguous("person", alias, ids, "alias maps to multiple people")
                return None
        canonical = (
            name or telegram_username or f"Telegram {telegram_user_id}"
        ).strip()
        cursor = self.conn.execute(
            "INSERT INTO people(canonical_name, telegram_user_id, telegram_username, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (canonical, telegram_user_id, telegram_username, now, now),
        )
        if cursor.lastrowid is None:
            raise RuntimeError("SQLite did not return an ID for the new person")
        person_id = cursor.lastrowid
        self._alias("person", person_id, canonical, source, confidence)
        if telegram_username and normalize_alias(telegram_username) != normalize_alias(
            canonical
        ):
            self._alias("person", person_id, telegram_username, source, confidence)
        return person_id

    def entity(
        self,
        entity_type: str,
        name: str | None,
        *,
        source: str = "ai",
        confidence: float = 1.0,
    ) -> int | None:
        if not name or not normalize_alias(name):
            return None
        if entity_type == "person":
            return self.person(name, source=source, confidence=confidence)
        table, column = (
            ("companies", "company_id")
            if entity_type == "company"
            else ("projects", "project_id")
        )
        key = normalize_alias(name)
        rows = self.conn.execute(
            "SELECT entity_id FROM entity_aliases WHERE entity_type = ? AND normalized_alias = ?",
            (entity_type, key),
        ).fetchall()
        ids = sorted({int(row[0]) for row in rows})
        if len(ids) == 1:
            return ids[0]
        if len(ids) > 1:
            self._ambiguous(entity_type, key, ids, "alias maps to multiple entities")
            return None
        now = utc_now()
        cursor = self.conn.execute(
            f"INSERT INTO {table}(canonical_name, created_at, updated_at) VALUES (?, ?, ?)",
            (name.strip(), now, now),
        )
        if cursor.lastrowid is None:
            raise RuntimeError(f"SQLite did not return an ID for the new {entity_type}")
        entity_id = cursor.lastrowid
        self._alias(entity_type, entity_id, name, source, confidence)
        return entity_id

    def _alias(
        self,
        entity_type: str,
        entity_id: int,
        alias: str,
        source: str,
        confidence: float,
    ) -> None:
        key = normalize_alias(alias)
        if key:
            self.conn.execute(
                "INSERT OR IGNORE INTO entity_aliases(entity_type, entity_id, alias, normalized_alias, source, confidence, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    entity_type,
                    entity_id,
                    alias.strip(),
                    key,
                    source,
                    confidence,
                    utc_now(),
                ),
            )

    def _ambiguous(
        self, entity_type: str, key: str, ids: list[int], reason: str
    ) -> None:
        now = utc_now()
        self.conn.execute(
            "INSERT OR IGNORE INTO entity_merge_candidates(entity_type, normalized_alias, entity_ids_json, reason, created_at) VALUES (?, ?, ?, ?, ?)",
            (entity_type, key, json.dumps(ids), reason, now),
        )
        self.conn.execute(
            "INSERT INTO review_queue(review_type, subject_type, payload_json, confidence, created_at) VALUES ('entity_merge', ?, ?, NULL, ?)",
            (
                entity_type,
                json.dumps({"alias": key, "entity_ids": ids, "reason": reason}),
                now,
            ),
        )


def direct_chat_person(conn: sqlite3.Connection, chat_id: int) -> int | None:
    """Return the deterministic Telegram peer for one direct conversation."""
    chat = conn.execute(
        "SELECT title,username,chat_type FROM chats WHERE chat_id=?", (chat_id,)
    ).fetchone()
    if chat is None or chat[2] != "user":
        return None
    title, username, _chat_type = chat
    existing = conn.execute(
        "SELECT person_id FROM people WHERE telegram_user_id=?", (chat_id,)
    ).fetchone()
    if existing is not None:
        return int(existing[0])
    username_key = normalize_alias(username)
    if username_key:
        matches = conn.execute(
            """SELECT DISTINCT p.person_id,p.telegram_user_id FROM people AS p
               LEFT JOIN entity_aliases AS a ON a.entity_type='person'
                   AND a.entity_id=p.person_id
               WHERE p.telegram_username IN (?, ?)
                  OR (a.normalized_alias=? AND a.alias LIKE '@%')""",
            (username_key, f"@{username_key}", username_key),
        ).fetchall()
        unclaimed = [row for row in matches if row[1] is None]
        if len(matches) == len(unclaimed) == 1:
            person_id = int(unclaimed[0][0])
            conn.execute(
                """UPDATE people SET telegram_user_id=?,telegram_username=?,updated_at=?
                   WHERE person_id=?""",
                (chat_id, username_key, utc_now(), person_id),
            )
            return person_id

    canonical = str(title or username or f"Telegram {chat_id}").strip()
    now = utc_now()
    cursor = conn.execute(
        """INSERT INTO people(canonical_name,telegram_user_id,telegram_username,created_at,updated_at)
           VALUES (?,?,?,?,?)""",
        (canonical, chat_id, username_key or None, now, now),
    )
    if cursor.lastrowid is None:
        raise RuntimeError("SQLite did not return an ID for the direct-chat person")
    person_id = int(cursor.lastrowid)
    resolver = EntityResolver(conn)
    resolver._alias("person", person_id, canonical, "telegram_direct_chat", 1.0)
    if username_key and username_key != normalize_alias(canonical):
        resolver._alias("person", person_id, username_key, "telegram_direct_chat", 1.0)

    title_key = normalize_alias(title)
    if title_key:
        candidates = {
            person_id,
            *(
                int(row[0])
                for row in conn.execute(
                    """SELECT entity_id FROM entity_aliases
                       WHERE entity_type='person' AND normalized_alias=?""",
                    (title_key,),
                ).fetchall()
            ),
        }
        if len(candidates) > 1:
            resolver._ambiguous(
                "person",
                title_key,
                sorted(candidates),
                "direct-chat title requires manual identity review",
            )
    return person_id


def backfill_direct_chat_identities(
    conn: sqlite3.Connection, settings: Settings, *, limit: int
) -> int:
    """Materialize at most ``limit`` deterministic direct-chat identities."""
    if limit < 1:
        raise ValueError("Direct-chat identity backfill limit must be positive")
    rows = conn.execute(
        """SELECT c.chat_id FROM chats AS c
           WHERE c.chat_type='user' AND NOT EXISTS (
               SELECT 1 FROM people AS p WHERE p.telegram_user_id=c.chat_id
           )
           ORDER BY c.updated_at,c.chat_id LIMIT ?""",
        (limit,),
    ).fetchall()
    if not rows:
        return 0
    from .context import ConversationContextService

    service = ConversationContextService(conn, settings)
    for (chat_id,) in rows:
        person_id = direct_chat_person(conn, int(chat_id))
        if person_id is not None:
            service.refresh_person(person_id, int(chat_id))
    return len(rows)


@dataclass(frozen=True, slots=True)
class ProjectResolution:
    project_id: int | None
    confidence: float
    reasons: tuple[str, ...]
    alternatives: tuple[int, ...]


def resolve_task_project(
    conn: sqlite3.Connection,
    *,
    chat_id: int,
    message_id: int | None,
    occurred_at: str | None,
    title: str,
    details: str,
    person_id: int | None,
    company_id: int | None,
    message_projects: set[int],
    batch_projects: set[int],
) -> ProjectResolution:
    """Rank bounded deterministic project evidence for one task-like item."""
    candidates: dict[int, tuple[float, list[str]]] = {}

    def add(project_id: int, confidence: float, reason: str) -> None:
        current = candidates.get(project_id)
        if current is None or confidence > current[0]:
            candidates[project_id] = (confidence, [reason])
        elif reason not in current[1]:
            current[1].append(reason)

    for project_id in message_projects:
        add(project_id, 1.0, "same_message")
    text = normalize_alias(f"{title} {details}")
    for project_id, alias in conn.execute(
        """SELECT a.entity_id,a.normalized_alias FROM entity_aliases AS a
           WHERE a.entity_type='project' AND length(a.normalized_alias)>=4"""
    ):
        if str(alias) in text:
            add(int(project_id), 0.96, "project_name")
    if occurred_at:
        from .context.segments import active_segment_project

        segment_project = active_segment_project(conn, chat_id, occurred_at)
        if segment_project is not None:
            add(segment_project, 0.90, "active_segment")
    for entity_type, entity_id in (("person", person_id), ("company", company_id)):
        if entity_id is None:
            continue
        rows = conn.execute(
            """SELECT CASE WHEN from_type='project' THEN from_id ELSE to_id END
               FROM relationships
               WHERE is_current=1 AND ((from_type=? AND from_id=? AND to_type='project')
                 OR (to_type=? AND to_id=? AND from_type='project'))""",
            (entity_type, entity_id, entity_type, entity_id),
        ).fetchall()
        for (project_id,) in rows:
            add(int(project_id), 0.82, f"{entity_type}_relationship")
    if len(batch_projects) == 1:
        add(next(iter(batch_projects)), 0.75, "single_batch_project")
    if not candidates:
        return ProjectResolution(None, 0.0, (), ())
    ranked = sorted(candidates.items(), key=lambda item: (-item[1][0], item[0]))
    project_id, (confidence, reasons) = ranked[0]
    alternatives = tuple(candidate for candidate, _ in ranked[1:])
    if alternatives and candidates[alternatives[0]][0] >= confidence - 0.05:
        return ProjectResolution(
            None, confidence, tuple(reasons), (project_id, *alternatives)
        )
    return ProjectResolution(project_id, confidence, tuple(reasons), alternatives)


class TaskReconciler:
    def __init__(self, conn: sqlite3.Connection, settings: Settings):
        self.conn, self.settings = conn, settings

    def process_item(
        self,
        item: sqlite3.Row | tuple,
        person_id: int | None,
        company_id: int | None,
        project_id: int | None,
        *,
        source_claim_id: int | None = None,
        source_at: str | None = None,
        force: bool = False,
    ) -> int | None:
        item_id, kind, title, details, status, owner, due_date, confidence, chat_id = (
            item[:9]
        )
        if kind not in TASK_KINDS:
            return None
        payload = {
            "item_id": item_id,
            "kind": kind,
            "title": title,
            "status": status,
            "owner": owner,
            "due_date": due_date,
        }
        terminal = status in {"done", "canceled"}
        required = (
            max(self.settings.ai_auto_accept_confidence, 0.95)
            if terminal
            else self.settings.ai_auto_accept_confidence
        )
        if not force and float(confidence) < required:
            if float(confidence) >= self.settings.ai_review_confidence:
                self._review("task_change", item_id, payload, float(confidence))
            return None
        normalized = normalize_task_title(title)
        rejected = self.conn.execute(
            "SELECT 1 FROM user_feedback WHERE feedback_type='reject_task' AND json_extract(payload_json, '$.normalized_title')=? LIMIT 1",
            (normalized,),
        ).fetchone()
        if rejected:
            return None
        if not normalized:
            self._review("task_change", item_id, payload, float(confidence))
            return None
        task = self._find_match(
            normalized,
            str(kind),
            source_at,
            int(chat_id),
            person_id,
            company_id,
            project_id,
        )
        now = utc_now()
        if task is None and terminal:
            self._review("task_completion", item_id, payload, float(confidence))
            return None
        if task is None:
            cursor = self.conn.execute(
                """INSERT INTO tasks(title, normalized_title, details, status, owner, related_person_id, related_company_id, related_project_id, source_chat_id, due_date, confidence, source_item_id, source_claim_id, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    title,
                    normalized,
                    details,
                    status if status in {"open", "waiting"} else "open",
                    owner,
                    person_id,
                    company_id,
                    project_id,
                    chat_id,
                    due_date,
                    confidence,
                    item_id,
                    source_claim_id,
                    now,
                    now,
                ),
            )
            if cursor.lastrowid is None:
                raise RuntimeError("SQLite did not return an ID for the new task")
            self._event(cursor.lastrowid, "created", "ai", item_id, payload)
            return int(cursor.lastrowid)
        task_id, manual_locked = int(task[0]), bool(task[1])
        if manual_locked:
            self._review(
                "task_change",
                item_id,
                {**payload, "task_id": task_id, "reason": "manual status lock"},
                float(confidence),
            )
            return task_id
        next_status = (
            status if status in {"open", "waiting", "done", "canceled"} else "open"
        )
        self.conn.execute(
            """UPDATE tasks SET title=?,details=?,status=?,due_date=COALESCE(?,due_date),
               related_person_id=COALESCE(related_person_id,?),
               related_company_id=COALESCE(related_company_id,?),
               related_project_id=COALESCE(related_project_id,?),confidence=?,
               source_item_id=?,source_claim_id=COALESCE(?,source_claim_id),updated_at=?
               WHERE task_id=?""",
            (
                title,
                details,
                next_status,
                due_date,
                person_id,
                company_id,
                project_id,
                confidence,
                item_id,
                source_claim_id,
                now,
                task_id,
            ),
        )
        self._event(
            task_id,
            "completed"
            if next_status == "done"
            else "canceled"
            if next_status == "canceled"
            else "updated",
            "ai",
            item_id,
            payload,
        )
        return task_id

    def queue_project_review(
        self, task_id: int, item_id: int, resolution: ProjectResolution, chat_id: int
    ) -> bool:
        if resolution.project_id is None:
            return False
        exists = self.conn.execute(
            """SELECT 1 FROM review_queue WHERE review_type='graph_task_link'
               AND subject_id=? AND status='pending'
               AND json_extract(payload_json,'$.candidate_project_id')=? LIMIT 1""",
            (task_id, resolution.project_id),
        ).fetchone()
        if exists is not None:
            return False
        self.conn.execute(
            """INSERT INTO review_queue(review_type,subject_type,subject_id,payload_json,
               confidence,created_at) VALUES ('graph_task_link','task',?,?,?,?)""",
            (
                task_id,
                json.dumps(
                    {
                        "item_id": item_id,
                        "chat_id": chat_id,
                        "candidate_project_id": resolution.project_id,
                        "reasons": list(resolution.reasons),
                        "alternatives": list(resolution.alternatives),
                    }
                ),
                resolution.confidence,
                utc_now(),
            ),
        )
        return True

    def _find_match(
        self,
        title: str,
        kind: str,
        source_at: str | None,
        chat_id: int,
        person_id: int | None,
        company_id: int | None,
        project_id: int | None,
    ) -> sqlite3.Row | tuple | None:
        anchors = [
            ("tasks.related_person_id", person_id),
            ("tasks.related_company_id", company_id),
            ("tasks.related_project_id", project_id),
        ]
        known = [(column, value) for column, value in anchors if value is not None]
        predicates = ["tasks.source_chat_id=?", "tasks.status IN ('open','waiting')"]
        params: list[object] = [chat_id]
        if known:
            predicates.append(
                "("
                + " OR ".join(f"{column}=?" for column, _ in known)
                + " OR tasks.normalized_title=?)"
            )
            params.extend(value for _, value in known)
            params.append(title)
            threshold = 0.78
        else:
            predicates.append("tasks.normalized_title=?")
            params.append(title)
            threshold = 0.92
        rows = self.conn.execute(
            f"""SELECT task_id,manual_status_locked,normalized_title,
                       related_person_id,related_company_id,related_project_id,
                       source_item.kind,
                       COALESCE(source_item.source_date,tasks.created_at)
                FROM tasks
                LEFT JOIN ai_items AS source_item
                  ON source_item.item_id=tasks.source_item_id
                WHERE {" AND ".join(predicates)}
                ORDER BY tasks.updated_at DESC,tasks.task_id DESC LIMIT 50""",
            params,
        ).fetchall()
        incoming_day = _source_day(source_at)
        candidates: list[tuple[float, float, sqlite3.Row | tuple]] = []
        for row in rows:
            candidate_anchors = row[3:6]
            anchor_matches = sum(
                value is not None and value == candidate_anchors[index]
                for index, (_, value) in enumerate(anchors)
            )
            has_conflict = any(
                value is not None
                and candidate_anchors[index] is not None
                and value != candidate_anchors[index]
                for index, (_, value) in enumerate(anchors)
            )
            if has_conflict:
                continue
            similarity = SequenceMatcher(None, title, row[2]).ratio()
            candidate_threshold = threshold
            if known and anchor_matches == 0:
                # A known incoming anchor does not make a sparse historical row
                # an identity match. Only an exact normalized title can bridge it.
                candidate_threshold = 1.0
            if similarity >= candidate_threshold:
                candidate_day = _source_day(row[7])
                is_exact_title = similarity == 1.0
                if not is_exact_title and (
                    row[6] != kind
                    or incoming_day is None
                    or candidate_day is None
                    or abs((incoming_day - candidate_day).days) > 180
                ):
                    continue
                candidates.append((anchor_matches, similarity, row))
        if not candidates:
            return None
        return max(candidates, key=lambda candidate: candidate[:2])[2]

    def _event(
        self, task_id: int, event_type: str, source: str, item_id: int, payload: dict
    ) -> None:
        self.conn.execute(
            """INSERT INTO task_events(task_id, event_type, source, source_item_id, payload_json, created_at)
               SELECT ?, ?, ?, ?, ?, ?
               WHERE NOT EXISTS (
                   SELECT 1 FROM task_events
                   WHERE task_id=? AND event_type=? AND source=? AND source_item_id=?
               )""",
            (
                task_id,
                event_type,
                source,
                item_id,
                json.dumps(payload),
                utc_now(),
                task_id,
                event_type,
                source,
                item_id,
            ),
        )

    def _review(
        self, review_type: str, subject_id: int, payload: dict, confidence: float
    ) -> None:
        self.conn.execute(
            "INSERT INTO review_queue(review_type, subject_type, subject_id, payload_json, confidence, created_at) VALUES (?, 'ai_item', ?, ?, ?, ?)",
            (review_type, subject_id, json.dumps(payload), confidence, utc_now()),
        )


def backfill_task_project_links(
    conn: sqlite3.Connection,
    settings: Settings,
    *,
    limit: int,
    task_ids: tuple[int, ...] | None = None,
) -> tuple[int, int]:
    """Repair at most ``limit`` unlinked tasks from bounded accepted evidence."""
    if limit < 1:
        raise ValueError("Task-project repair limit must be positive")
    if task_ids is not None and (not task_ids or len(task_ids) > limit):
        raise ValueError("Task-project repair IDs must be non-empty and within limit")
    where = "t.related_project_id IS NULL AND t.source_chat_id IS NOT NULL"
    params: tuple[int, ...] = (limit,)
    if task_ids is not None:
        placeholders = ",".join("?" for _ in task_ids)
        where += f" AND t.task_id IN ({placeholders})"
        params = task_ids
    rows = conn.execute(
        """SELECT t.task_id,t.title,t.details,t.source_chat_id,i.batch_id,
                  i.source_message_id,i.source_date,t.related_person_id,t.related_company_id
           FROM tasks AS t JOIN ai_items AS i ON i.item_id=t.source_item_id
           WHERE """
        + where
        + " ORDER BY t.task_id"
        + (" LIMIT ?" if task_ids is None else ""),
        params,
    ).fetchall()
    reconciler = TaskReconciler(conn, settings)
    linked = reviewed = 0
    affected_chats: set[int] = set()
    for (
        task_id,
        title,
        details,
        chat_id,
        batch_id,
        message_id,
        occurred_at,
        person_id,
        company_id,
    ) in rows:
        batch_projects = {
            int(row[0])
            for row in conn.execute(
                "SELECT project_id FROM ai_items WHERE batch_id=? AND project_id IS NOT NULL",
                (batch_id,),
            ).fetchall()
        }
        message_projects = {
            int(row[0])
            for row in conn.execute(
                """SELECT project_id FROM ai_items WHERE batch_id=?
                   AND source_message_id=? AND project_id IS NOT NULL""",
                (batch_id, message_id),
            ).fetchall()
        }
        resolution = resolve_task_project(
            conn,
            chat_id=int(chat_id),
            message_id=message_id,
            occurred_at=occurred_at,
            title=str(title),
            details=str(details or ""),
            person_id=person_id,
            company_id=company_id,
            message_projects=message_projects,
            batch_projects=batch_projects,
        )
        if (
            resolution.project_id is not None
            and resolution.confidence >= settings.ai_auto_accept_confidence
        ):
            changed = conn.execute(
                "UPDATE tasks SET related_project_id=?,updated_at=? WHERE task_id=? AND related_project_id IS NULL",
                (resolution.project_id, utc_now(), task_id),
            ).rowcount
            if changed:
                linked += 1
                affected_chats.add(int(chat_id))
        elif resolution.project_id is not None:
            reviewed += int(
                reconciler.queue_project_review(
                    int(task_id), 0, resolution, int(chat_id)
                )
            )
    if affected_chats:
        from .context.segments import ConversationSegmenter

        ConversationSegmenter(conn).rebuild_chats(affected_chats)
    return linked, reviewed


def _project_ai_batch(
    conn: sqlite3.Connection, batch_id: int, settings: Settings
) -> None:
    """Post-save pipeline: evidence -> entities -> tasks -> layered memory."""
    batch = conn.execute(
        "SELECT chat_id, job_id, summary, provider, model, created_at FROM ai_batches WHERE batch_id = ?",
        (batch_id,),
    ).fetchone()
    if not batch:
        return
    chat_id, job_id, summary, provider, model, created_at = batch
    dates = conn.execute(
        "SELECT MIN(date), MAX(date) FROM messages WHERE chat_id = ? AND message_id IN (SELECT message_id FROM ai_message_state WHERE batch_id = ?)",
        (chat_id, batch_id),
    ).fetchone()
    now = utc_now()
    conn.execute(
        """INSERT INTO memory_chunks(chat_id, batch_id, job_id, date_from, date_to, summary, provider, model, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(batch_id) DO UPDATE SET summary=excluded.summary, updated_at=excluded.updated_at""",
        (
            chat_id,
            batch_id,
            job_id,
            dates[0],
            dates[1],
            summary or "No durable facts extracted.",
            provider,
            model,
            now,
            now,
        ),
    )
    resolver, reconciler = EntityResolver(conn), TaskReconciler(conn, settings)
    # Preserve the direct-chat identity anchor even when an item names someone
    # else; it is source-backed chat metadata, not model inference.
    direct_chat_person(conn, int(chat_id))
    rows = conn.execute(
        """SELECT item_id, kind, title, details, status, owner, due_date, confidence,
                  source_chat_id, person, company, project_name, source_message_id,
                  source_date, source_claim_id
           FROM ai_items WHERE batch_id = ?""",
        (batch_id,),
    ).fetchall()
    from .context.service import ContextService
    from .context.graph import SemanticGraphProjector

    context_service = ContextService(conn, settings)
    graph_projector = SemanticGraphProjector(conn)
    project_items: dict[int, int] = {}
    message_projects: dict[int, set[int]] = {}
    for item_id, kind, title, *_rest in rows:
        if kind != "project":
            continue
        project_id = resolver.entity("project", title)
        if project_id is None:
            continue
        project_items[int(item_id)] = project_id
        message_id = _rest[9]
        if message_id is not None:
            message_projects.setdefault(int(message_id), set()).add(project_id)
    batch_projects = set(project_items.values())
    for row in rows:
        (
            item_id,
            kind,
            title,
            details,
            status,
            owner,
            due,
            confidence,
            source_chat,
            person,
            company,
            project_name,
            source_message_id,
            source_date,
            source_claim_id,
        ) = row
        person_id = resolver.entity("person", person, confidence=confidence)
        company_id = resolver.entity("company", company, confidence=confidence)
        project_id = project_items.get(int(item_id)) or resolver.entity(
            "project", project_name, confidence=confidence
        )
        resolution = ProjectResolution(None, 0.0, (), ())
        if kind in TASK_KINDS and project_id is None:
            resolution = resolve_task_project(
                conn,
                chat_id=int(source_chat),
                message_id=source_message_id,
                occurred_at=source_date,
                title=str(title),
                details=str(details or ""),
                person_id=person_id,
                company_id=company_id,
                message_projects=message_projects.get(int(source_message_id), set())
                if source_message_id is not None
                else set(),
                batch_projects=batch_projects,
            )
            if resolution.project_id is not None and (
                resolution.confidence >= settings.ai_auto_accept_confidence
            ):
                project_id = resolution.project_id
        conn.execute(
            "UPDATE ai_items SET person_id=?, company_id=?, project_id=? WHERE item_id=?",
            (person_id, company_id, project_id, item_id),
        )
        task_id = reconciler.process_item(
            row[:9],
            person_id,
            company_id,
            project_id,
            source_claim_id=source_claim_id,
            source_at=source_date,
        )
        if (
            task_id is not None
            and project_id is None
            and resolution.project_id is not None
        ):
            reconciler.queue_project_review(
                task_id, int(item_id), resolution, int(source_chat)
            )
        context_service.process_ai_item(
            row[:9] + (source_message_id, source_date),
            person_id,
            company_id,
            project_id,
        )
        if source_claim_id is not None:
            for table in ("context_events", "context_facts"):
                conn.execute(
                    f"UPDATE {table} SET source_claim_id=? "
                    "WHERE source_ai_item_id=? AND source_claim_id IS NULL",
                    (source_claim_id, item_id),
                )
        graph_projector.project_item(
            claim_id=source_claim_id,
            item_id=int(item_id),
            source_at=source_date,
            person_id=person_id,
            company_id=company_id,
            project_id=project_id,
            task_id=task_id,
        )
        if (
            kind in DURABLE_KINDS
            and float(confidence) >= settings.ai_auto_accept_confidence
        ):
            for entity_type, entity_id in (
                ("person", person_id),
                ("company", company_id),
                ("project", project_id),
            ):
                if entity_id:
                    conn.execute(
                        "INSERT INTO entity_memory(entity_type, entity_id, memory_key, summary, source_item_id, confidence, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(entity_type, entity_id, memory_key) DO UPDATE SET summary=excluded.summary, source_item_id=excluded.source_item_id, confidence=excluded.confidence, updated_at=excluded.updated_at",
                        (
                            entity_type,
                            entity_id,
                            normalize_task_title(title)[:160],
                            f"{title}: {details}"[:2000],
                            item_id,
                            confidence,
                            now,
                        ),
                    )
    context_service.process_batch_temporal(batch_id)


def process_ai_batch(
    conn: sqlite3.Connection, batch_id: int, settings: Settings
) -> bool:
    """Project one saved batch transactionally, without re-calling a provider."""
    now = utc_now()
    with conn:
        claim = conn.execute(
            """UPDATE ai_batches SET projection_status='running',
                   projection_attempt_count=projection_attempt_count+1,
                   projection_started_at=?,projection_error=NULL
               WHERE batch_id=? AND projection_status IN ('pending','failed')""",
            (now, batch_id),
        )
    if not claim.rowcount:
        return bool(
            conn.execute(
                "SELECT 1 FROM ai_batches WHERE batch_id=? AND projection_status='completed'",
                (batch_id,),
            ).fetchone()
        )
    try:
        with conn:
            _project_ai_batch(conn, batch_id, settings)
            batch = conn.execute(
                "SELECT chat_id FROM ai_batches WHERE batch_id=?", (batch_id,)
            ).fetchone()
            if batch is None:
                raise RuntimeError("saved AI batch disappeared before projection")
            scopes: set[tuple[str, int]] = {("conversation", int(batch[0]))}
            chat_person_id = direct_chat_person(conn, int(batch[0]))
            if chat_person_id is not None:
                scopes.add(("person", chat_person_id))
            item_scopes = conn.execute(
                "SELECT person_id,company_id,project_id FROM ai_items WHERE batch_id=?",
                (batch_id,),
            ).fetchall()
            if item_scopes:
                scopes.add(("global", 0))
            for person_id, company_id, project_id in item_scopes:
                for scope, value in (
                    ("person", person_id),
                    ("company", company_id),
                    ("project", project_id),
                ):
                    if value is not None:
                        scopes.add((scope, int(value)))
            for (task_id,) in conn.execute(
                """SELECT task_id FROM tasks WHERE source_item_id IN
                   (SELECT item_id FROM ai_items WHERE batch_id=?)""",
                (batch_id,),
            ):
                scopes.add(("task", int(task_id)))
            from .context.refresh import enqueue_context_invalidations

            enqueue_context_invalidations(conn, batch_id, scopes)
            conn.execute(
                "UPDATE ai_message_state SET canonicalized_at=? WHERE batch_id=?",
                (utc_now(), batch_id),
            )
            conn.execute(
                """UPDATE ai_batches SET projection_status='completed',projected_at=?,
                   projection_error=NULL WHERE batch_id=?""",
                (utc_now(), batch_id),
            )
        return True
    except Exception as error:
        with conn:
            conn.execute(
                "UPDATE ai_batches SET projection_status='failed',projection_error=? WHERE batch_id=?",
                (f"{type(error).__name__}: {error}"[:2000], batch_id),
            )
        return False


def _refresh_summaries(
    conn: sqlite3.Connection, chat_id: int, date_value: str | None
) -> None:
    if not date_value:
        return
    day = date_value[:10]
    rows = conn.execute(
        "SELECT summary FROM memory_chunks WHERE chat_id=? AND substr(COALESCE(date_from, created_at),1,10)=? ORDER BY chunk_id",
        (chat_id, day),
    ).fetchall()
    text = _consolidate([row[0] for row in rows])
    now = utc_now()
    conn.execute(
        "INSERT INTO chat_daily_summaries(chat_id, summary_date, summary, chunk_count, updated_at) VALUES (?, ?, ?, ?, ?) ON CONFLICT(chat_id, summary_date) DO UPDATE SET summary=excluded.summary, chunk_count=excluded.chunk_count, updated_at=excluded.updated_at",
        (chat_id, day, text, len(rows), now),
    )
    month = day[:7]
    rows = conn.execute(
        "SELECT summary FROM chat_daily_summaries WHERE chat_id=? AND substr(summary_date,1,7)=? ORDER BY summary_date",
        (chat_id, month),
    ).fetchall()
    text = _consolidate([row[0] for row in rows])
    conn.execute(
        "INSERT INTO chat_monthly_summaries(chat_id, summary_month, summary, day_count, updated_at) VALUES (?, ?, ?, ?, ?) ON CONFLICT(chat_id, summary_month) DO UPDATE SET summary=excluded.summary, day_count=excluded.day_count, updated_at=excluded.updated_at",
        (chat_id, month, text, len(rows), now),
    )


def _consolidate(values: list[str]) -> str:
    unique: list[str] = []
    for value in values:
        clean = " ".join((value or "").split())
        if clean and clean not in unique:
            unique.append(clean)
    return " ".join(unique[-8:])[:4000] or "No durable activity recorded."


def generate_daily_brief(
    conn: sqlite3.Connection,
    brief_date: str | None = None,
    settings: Settings | None = None,
) -> dict:
    brief_date = brief_date or date.today().isoformat()
    created = conn.execute(
        """SELECT t.task_id, t.title, t.status, t.due_date
           FROM tasks AS t
           WHERE substr(
               COALESCE(
                   (
                       SELECT m.date
                       FROM task_events AS e
                       JOIN ai_items AS i ON i.item_id = e.source_item_id
                       JOIN messages AS m
                         ON m.chat_id = i.source_chat_id
                        AND m.message_id = i.source_message_id
                       WHERE e.task_id = t.task_id
                         AND e.event_type = 'created'
                       ORDER BY e.event_id
                       LIMIT 1
                   ),
                   t.created_at
               ),
               1,
               10
           ) = ?
           ORDER BY t.task_id DESC""",
        (brief_date,),
    ).fetchall()
    updated = conn.execute(
        "SELECT DISTINCT t.task_id, t.title, t.status, t.due_date FROM tasks t JOIN task_events e ON e.task_id=t.task_id WHERE substr(e.created_at,1,10)=? AND e.event_type <> 'created' ORDER BY t.task_id DESC",
        (brief_date,),
    ).fetchall()
    open_tasks = conn.execute(
        "SELECT task_id, title, status, due_date FROM tasks WHERE status IN ('open','waiting') ORDER BY CASE WHEN due_date IS NULL THEN 1 ELSE 0 END, due_date, task_id DESC LIMIT 30"
    ).fetchall()
    facts = conn.execute(
        "SELECT title, details FROM ai_items WHERE kind IN ('important_fact','payment') AND substr(created_at,1,10)=? ORDER BY item_id DESC LIMIT 12",
        (brief_date,),
    ).fetchall()
    follow_ups = conn.execute(
        "SELECT title,priority,due_at FROM follow_ups WHERE status='open' ORDER BY CASE priority WHEN 'critical' THEN 0 WHEN 'high' THEN 1 ELSE 2 END, due_at LIMIT 15"
    ).fetchall()
    stale = conn.execute(
        "SELECT canonical_name,status,health_score,last_activity_at FROM projects WHERE status IN ('stale','critical') ORDER BY health_score LIMIT 12"
    ).fetchall()
    data = {
        "date": brief_date,
        "new_tasks": _task_dicts(created),
        "updates": _task_dicts(updated),
        "open_tasks": _task_dicts(open_tasks),
        "facts": [{"title": r[0], "details": r[1]} for r in facts],
        "follow_ups": [
            {"title": r[0], "details": f"{r[1]} · due {r[2] or 'now'}"}
            for r in follow_ups
        ],
        "stale_projects": [
            {
                "title": r[0],
                "details": f"{r[1]} · health {r[2] if r[2] is not None else '—'} · last {r[3] or 'unknown'}",
            }
            for r in stale
        ],
    }
    if settings is not None:
        from .context import ContextService

        global_context = ContextService(conn, settings).get_global_context()
        data["global_context"] = global_context.global_state
        data["context_diagnostics"] = global_context.diagnostics
        data["people_attention"] = [
            {
                "title": item["name"],
                "details": f"{item['open_loops']} open or waiting conversation loop(s)",
            }
            for item in global_context.global_state.get(
                "people_requiring_attention", []
            )
        ]
    now = utc_now()
    conn.execute(
        "INSERT INTO daily_briefs(brief_date, data_json, created_at, updated_at) VALUES (?, ?, ?, ?) ON CONFLICT(brief_date) DO UPDATE SET data_json=excluded.data_json, updated_at=excluded.updated_at",
        (brief_date, json.dumps(data, ensure_ascii=False), now, now),
    )
    return data


def load_daily_brief(
    conn: sqlite3.Connection, brief_date: str | None = None
) -> dict | None:
    """Read one persisted Daily Brief without refreshing its derived payload."""
    brief_date = brief_date or date.today().isoformat()
    row = conn.execute(
        "SELECT * FROM daily_briefs WHERE brief_date=?", (brief_date,)
    ).fetchone()
    if row is None:
        return None
    try:
        payload = json.loads(row[1])
    except (TypeError, json.JSONDecodeError) as error:
        raise ValueError(
            f"Daily Brief for {brief_date} has invalid payload."
        ) from error
    if not isinstance(payload, dict):
        raise ValueError(f"Daily Brief for {brief_date} has invalid payload.")
    return payload


def _task_dicts(rows: list[tuple]) -> list[dict]:
    return [
        {"task_id": r[0], "title": r[1], "status": r[2], "due_date": r[3]} for r in rows
    ]


def manually_update_task(conn: sqlite3.Connection, task_id: int, status: str) -> bool:
    """User actions are authoritative and prevent later AI state flips."""
    if status not in {"open", "waiting", "done", "canceled"}:
        raise ValueError("status must be open, waiting, done, or canceled")
    row = conn.execute(
        "SELECT status,manual_status_locked FROM tasks WHERE task_id = ?", (task_id,)
    ).fetchone()
    if not row:
        return False
    if row[0] == status and row[1]:
        return True
    now = utc_now()
    conn.execute(
        "UPDATE tasks SET status=?, manual_updated_at=?, manual_status_locked=1, updated_at=? WHERE task_id=?",
        (status, now, now, task_id),
    )
    conn.execute(
        "INSERT INTO task_events(task_id, event_type, source, payload_json, created_at) VALUES (?, 'manual_update', 'manual', ?, ?)",
        (task_id, json.dumps({"status": status}), now),
    )
    return True


def review_actions(review_type: str) -> tuple[str, ...]:
    """Return only decisions which have a deterministic local effect."""
    if review_type == "message_classification":
        return ("accept", "edit", "reject", "ignore")
    return ("accept", "reject", "ignore")


def resolve_review_item(
    conn: sqlite3.Connection,
    review_id: int,
    action: str,
    *,
    edited_payload: dict | None = None,
    settings: Settings | None = None,
) -> None:
    """Persist a generic review decision and durable feedback for automation."""
    row = conn.execute(
        "SELECT review_type,subject_type,subject_id,payload_json FROM review_queue WHERE review_id=? AND status='pending'",
        (review_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"Pending review item {review_id} was not found.")
    review_type, subject_type, subject_id, payload_json = row
    if action not in review_actions(str(review_type)):
        raise ValueError(f"{action!r} is not available for {review_type}.")
    try:
        payload = json.loads(payload_json)
    except (TypeError, json.JSONDecodeError) as error:
        raise ValueError(
            "Review payload is invalid and cannot be decided safely."
        ) from error
    if edited_payload is not None:
        payload["manual_edit"] = edited_payload
    now = utc_now()
    with conn:
        if action == "accept" and review_type == "graph_link":
            item_id = payload.get("source_item_id")
            project_id = payload.get("candidate_project_id")
            if not isinstance(item_id, int) or not isinstance(project_id, int):
                raise ValueError("Graph-link review lacks a valid item and project.")
            conn.execute(
                "UPDATE ai_items SET project_id=? WHERE item_id=?",
                (project_id, item_id),
            )
            item = conn.execute(
                """SELECT person_id,company_id,source_chat_id,source_message_id,
                           source_date
                   FROM ai_items WHERE item_id=?""",
                (item_id,),
            ).fetchone()
            if item is not None:
                from .context.graph import SemanticGraphProjector
                from .context.repository import ensure_relationship

                person_id, company_id, chat_id, message_id, source_date = item
                projector = SemanticGraphProjector(conn)
                valid_from = str(source_date or now)
                for entity_type, entity_id in (
                    ("person", person_id),
                    ("company", company_id),
                ):
                    if entity_id is None:
                        continue
                    ensure_relationship(
                        conn,
                        entity_type,
                        int(entity_id),
                        "project",
                        project_id,
                        "involved_in",
                        1.0,
                        chat_id,
                        message_id,
                        valid_from,
                    )
                    projector.project_manual_relationship(
                        from_type=entity_type,
                        from_id=int(entity_id),
                        to_type="project",
                        to_id=project_id,
                        relationship_type="involved_in",
                        valid_from=valid_from,
                    )
        if action == "accept" and review_type in {
            "graph_task_link",
            "graph_event_link",
            "graph_fact_link",
        }:
            project_id = payload.get("candidate_project_id")
            if not isinstance(project_id, int):
                raise ValueError("Graph repair review lacks a candidate project.")
            from .context.repository import ensure_relationship

            if review_type == "graph_task_link":
                conn.execute(
                    "UPDATE tasks SET related_project_id=?,updated_at=? WHERE task_id=?",
                    (project_id, now, subject_id),
                )
                ensure_relationship(
                    conn,
                    "task",
                    int(subject_id),
                    "project",
                    project_id,
                    "supports",
                    1.0,
                    payload.get("chat_id"),
                )
            elif review_type == "graph_event_link":
                conn.execute(
                    "UPDATE context_events SET project_id=? WHERE event_id=?",
                    (project_id, subject_id),
                )
                ensure_relationship(
                    conn,
                    "event",
                    int(subject_id),
                    "project",
                    project_id,
                    "relates_to",
                    1.0,
                    payload.get("chat_id"),
                )
            else:
                fact = conn.execute(
                    "SELECT subject_type,subject_id FROM context_facts WHERE fact_id=?",
                    (subject_id,),
                ).fetchone()
                if fact is None:
                    raise ValueError("The context fact for this review is unavailable.")
                ensure_relationship(
                    conn,
                    str(fact[0]),
                    int(fact[1]),
                    "project",
                    project_id,
                    "context_fact_about",
                    1.0,
                    payload.get("chat_id"),
                )
        if action == "accept" and review_type == "entity_merge":
            if edited_payload is None:
                raise ValueError("Choose the canonical entity to keep before merging.")
            keep_entity_id = edited_payload.get("keep_entity_id")
            entity_ids = payload.get("entity_ids")
            if (
                not isinstance(keep_entity_id, int)
                or not isinstance(entity_ids, list)
                or not all(isinstance(value, int) for value in entity_ids)
                or keep_entity_id not in entity_ids
            ):
                raise ValueError(
                    "The selected canonical entity is not a merge candidate."
                )
            _merge_entities(
                conn,
                str(subject_type),
                keep_entity_id,
                [value for value in entity_ids if value != keep_entity_id],
            )
            conn.execute(
                """UPDATE entity_merge_candidates SET status='resolved',resolved_at=?
                   WHERE entity_type=? AND normalized_alias=? AND status='pending'""",
                (now, subject_type, payload.get("alias")),
            )
        if action == "accept" and review_type in {"task_change", "task_completion"}:
            if settings is None:
                raise ValueError("Task-review acceptance requires runtime settings.")
            item_id = payload.get("item_id")
            if not isinstance(item_id, int):
                raise ValueError("Task review lacks a source AI item.")
            item = conn.execute(
                """SELECT item_id,kind,title,details,status,owner,due_date,confidence,
                           source_chat_id,person_id,company_id,project_id,source_date
                   FROM ai_items WHERE item_id=?""",
                (item_id,),
            ).fetchone()
            if item is None:
                raise ValueError(
                    "The source AI item for this task review is unavailable."
                )
            TaskReconciler(conn, settings).process_item(
                item[:9],
                item[9],
                item[10],
                item[11],
                source_at=item[12],
                force=True,
            )
        if action in {"accept", "edit"} and review_type == "message_classification":
            chat_id, message_id = payload.get("chat_id"), payload.get("message_id")
            if (
                isinstance(chat_id, int)
                and isinstance(message_id, int)
                and edited_payload
            ):
                scope = edited_payload.get("information_scope")
                content_type = edited_payload.get("content_type")
                if scope is not None and scope not in _INFORMATION_SCOPES:
                    raise ValueError("The information scope is not supported.")
                if content_type is not None and content_type not in _CONTENT_TYPES:
                    raise ValueError("The content type is not supported.")
                if isinstance(scope, str) or isinstance(content_type, str):
                    from .classification import CLASSIFICATION_VERSION

                    conn.execute(
                        """UPDATE message_classifications
                           SET information_scope=COALESCE(?, information_scope),
                               content_scope=COALESCE(?, content_scope),
                               content_type=COALESCE(?, content_type),
                               classification_version=?, context_stale=0
                           WHERE chat_id=? AND message_id=?""",
                        (
                            scope,
                            scope,
                            content_type,
                            CLASSIFICATION_VERSION,
                            chat_id,
                            message_id,
                        ),
                    )
        status = "approved" if action in {"accept", "edit"} else "rejected"
        conn.execute(
            "UPDATE review_queue SET status=?,resolved_at=? WHERE review_id=?",
            (status, now, review_id),
        )
        conn.execute(
            """INSERT INTO user_feedback(feedback_type,entity_type,entity_id,payload_json,source,created_at)
               VALUES (?,?,?,?,?,?)""",
            (
                f"review:{review_type}",
                subject_type,
                subject_id,
                json.dumps(
                    {"review_id": review_id, "action": action, "payload": payload},
                    sort_keys=True,
                ),
                "manual_review",
                now,
            ),
        )


def _merge_entities(
    conn: sqlite3.Connection,
    entity_type: str,
    keep_entity_id: int,
    discard_entity_ids: list[int],
) -> None:
    """Apply a manual identity correction without touching raw evidence."""
    tables = {
        "person": ("people", "person_id"),
        "company": ("companies", "company_id"),
        "project": ("projects", "project_id"),
    }
    if entity_type not in tables:
        raise ValueError(f"Unsupported entity type for merge: {entity_type!r}.")
    table, id_column = tables[entity_type]
    exists = conn.execute(
        f"SELECT 1 FROM {table} WHERE {id_column}=?", (keep_entity_id,)
    ).fetchone()
    if exists is None:
        raise ValueError("The canonical entity selected to keep no longer exists.")

    references = {
        "person": [
            ("ai_items", "person_id"),
            ("tasks", "related_person_id"),
            ("context_events", "person_id"),
            ("follow_ups", "person_id"),
            ("conversation_context_links", "person_id"),
        ],
        "company": [
            ("ai_items", "company_id"),
            ("tasks", "related_company_id"),
            ("context_events", "company_id"),
            ("follow_ups", "company_id"),
        ],
        "project": [
            ("ai_items", "project_id"),
            ("tasks", "related_project_id"),
            ("context_events", "project_id"),
            ("follow_ups", "project_id"),
            ("conversation_contact_segments", "primary_project_id"),
            ("current_conversation_context", "primary_project_id"),
            ("conversation_open_loops", "project_id"),
        ],
    }
    for discard_entity_id in discard_entity_ids:
        found = conn.execute(
            f"SELECT 1 FROM {table} WHERE {id_column}=?", (discard_entity_id,)
        ).fetchone()
        if found is None:
            raise ValueError("A merge candidate no longer exists.")
        for reference_table, column in references[entity_type]:
            conn.execute(
                f"UPDATE {reference_table} SET {column}=? WHERE {column}=?",
                (keep_entity_id, discard_entity_id),
            )
        conn.execute(
            """UPDATE OR IGNORE entity_aliases SET entity_id=?
               WHERE entity_type=? AND entity_id=?""",
            (keep_entity_id, entity_type, discard_entity_id),
        )
        conn.execute(
            "DELETE FROM entity_aliases WHERE entity_type=? AND entity_id=?",
            (entity_type, discard_entity_id),
        )
        for reference_table, type_column, id_column_name in (
            ("entity_memory", "entity_type", "entity_id"),
            ("context_facts", "subject_type", "subject_id"),
            ("context_summary_versions", "entity_type", "entity_id"),
            ("user_feedback", "entity_type", "entity_id"),
            ("notification_outbox", "entity_type", "entity_id"),
        ):
            conn.execute(
                f"""UPDATE OR IGNORE {reference_table} SET {id_column_name}=?
                    WHERE {type_column}=? AND {id_column_name}=?""",
                (keep_entity_id, entity_type, discard_entity_id),
            )
        for relationship_table in ("relationships", "entity_relationships"):
            conn.execute(
                f"""UPDATE OR IGNORE {relationship_table} SET from_id=?
                    WHERE from_type=? AND from_id=?""",
                (keep_entity_id, entity_type, discard_entity_id),
            )
            conn.execute(
                f"""UPDATE OR IGNORE {relationship_table} SET to_id=?
                    WHERE to_type=? AND to_id=?""",
                (keep_entity_id, entity_type, discard_entity_id),
            )
            conn.execute(
                f"""DELETE FROM {relationship_table}
                    WHERE (from_type=? AND from_id=?) OR (to_type=? AND to_id=?)""",
                (entity_type, discard_entity_id, entity_type, discard_entity_id),
            )
        conn.execute(
            "DELETE FROM entity_memory WHERE entity_type=? AND entity_id=?",
            (entity_type, discard_entity_id),
        )
        if entity_type == "person":
            conn.execute(
                """UPDATE OR IGNORE person_context_state SET person_id=?
                   WHERE person_id=?""",
                (keep_entity_id, discard_entity_id),
            )
            conn.execute(
                "DELETE FROM person_context_state WHERE person_id=?",
                (discard_entity_id,),
            )
            for contact_table in (
                "conversation_contact_segments",
                "current_conversation_context",
                "person_project_context",
                "conversation_open_loops",
            ):
                conn.execute(
                    f"UPDATE OR IGNORE {contact_table} SET person_id=? WHERE person_id=?",
                    (keep_entity_id, discard_entity_id),
                )
                conn.execute(
                    f"DELETE FROM {contact_table} WHERE person_id=?",
                    (discard_entity_id,),
                )
        if entity_type == "project":
            conn.execute(
                "UPDATE OR IGNORE person_project_context SET project_id=? WHERE project_id=?",
                (keep_entity_id, discard_entity_id),
            )
            conn.execute(
                "DELETE FROM person_project_context WHERE project_id=?",
                (discard_entity_id,),
            )
        conn.execute(
            f"UPDATE {table} SET status='merged',updated_at=? WHERE {id_column}=?",
            (utc_now(), discard_entity_id),
        )
