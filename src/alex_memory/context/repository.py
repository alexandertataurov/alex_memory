"""Temporal facts, events and relationship storage with provenance."""

from __future__ import annotations

import json
import sqlite3

from ..utils import utc_now


def add_event(
    conn: sqlite3.Connection,
    *,
    event_type: str,
    title: str,
    description: str,
    occurred_at: str | None,
    person_id: int | None = None,
    company_id: int | None = None,
    project_id: int | None = None,
    task_id: int | None = None,
    source_chat_id: int | None = None,
    source_message_id: int | None = None,
    source_ai_item_id: int | None = None,
    confidence: float = 0.5,
) -> int:
    if source_ai_item_id is not None:
        existing = conn.execute(
            "SELECT event_id FROM context_events WHERE source_ai_item_id=? AND event_type=?",
            (source_ai_item_id, event_type),
        ).fetchone()
        if existing:
            return int(existing[0])
    cursor = conn.execute(
        """INSERT INTO context_events(event_type,title,description,occurred_at,observed_at,person_id,company_id,project_id,task_id,source_type,source_chat_id,source_message_id,source_ai_item_id,confidence,created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'ai_item', ?, ?, ?, ?, ?)""",
        (
            event_type,
            title,
            description,
            occurred_at,
            utc_now(),
            person_id,
            company_id,
            project_id,
            task_id,
            source_chat_id,
            source_message_id,
            source_ai_item_id,
            confidence,
            utc_now(),
        ),
    )
    if cursor.lastrowid is None:
        raise RuntimeError("SQLite did not return an ID for the new context event")
    return cursor.lastrowid


def set_temporal_fact(
    conn: sqlite3.Connection,
    *,
    subject_type: str,
    subject_id: int,
    predicate: str,
    value: dict,
    valid_from: str,
    confidence: float,
    source_chat_id: int | None = None,
    source_message_id: int | None = None,
    source_ai_item_id: int | None = None,
) -> int:
    """Close a changed current fact; never overwrite historical state."""
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False)
    current = conn.execute(
        "SELECT fact_id,value_json FROM context_facts WHERE subject_type=? AND subject_id=? AND predicate=? AND is_current=1 ORDER BY fact_id DESC LIMIT 1",
        (subject_type, subject_id, predicate),
    ).fetchone()
    if current and current[1] == encoded:
        return int(current[0])
    now = utc_now()
    # State predicates are expected to evolve; identity/relationship facts
    # conflict instead of silently replacing the earlier observation.
    if current and not predicate.endswith(("_status", "_state", "_progress")):
        if source_ai_item_id is not None:
            existing_conflict = conn.execute(
                """SELECT conflict_id FROM context_conflicts
                   WHERE existing_fact_id=? AND new_observation_id=?
                     AND conflict_type='value_conflict'""",
                (current[0], source_ai_item_id),
            ).fetchone()
            if existing_conflict:
                return int(current[0])
        cursor = conn.execute(
            "INSERT INTO context_conflicts(subject_type,subject_id,predicate,existing_fact_id,new_observation_id,conflict_type,status,created_at) VALUES (?, ?, ?, ?, ?, 'value_conflict', 'pending', ?)",
            (subject_type, subject_id, predicate, current[0], source_ai_item_id, now),
        )
        if cursor.lastrowid is None:
            raise RuntimeError("SQLite did not return an ID for the temporal conflict")
        conn.execute(
            """INSERT INTO context_conflict_observations(
                   conflict_id,value_json,valid_from,confidence,source_chat_id,
                   source_message_id,source_ai_item_id,created_at
               ) VALUES (?,?,?,?,?,?,?,?)""",
            (
                cursor.lastrowid,
                encoded,
                valid_from,
                confidence,
                source_chat_id,
                source_message_id,
                source_ai_item_id,
                now,
            ),
        )
        return int(current[0])
    cursor = conn.execute(
        """INSERT INTO context_facts(subject_type,subject_id,predicate,value_json,valid_from,observed_at,is_current,confidence,source_type,source_chat_id,source_message_id,source_ai_item_id,created_at,updated_at)
           VALUES (?, ?, ?, ?, ?, ?, 1, ?, 'ai_item', ?, ?, ?, ?, ?)""",
        (
            subject_type,
            subject_id,
            predicate,
            encoded,
            valid_from,
            now,
            confidence,
            source_chat_id,
            source_message_id,
            source_ai_item_id,
            now,
            now,
        ),
    )
    if cursor.lastrowid is None:
        raise RuntimeError("SQLite did not return an ID for the new temporal fact")
    fact_id = cursor.lastrowid
    if current:
        conn.execute(
            "UPDATE context_facts SET valid_to=?,is_current=0,superseded_by_fact_id=?,updated_at=? WHERE fact_id=?",
            (valid_from, fact_id, now, current[0]),
        )
    return fact_id


def list_temporal_conflicts(conn: sqlite3.Connection, limit: int = 60) -> list[dict]:
    """Return pending conflicts with both values and their source references."""
    rows = conn.execute(
        """SELECT c.conflict_id,c.subject_type,c.subject_id,c.predicate,c.created_at,
                  f.fact_id,f.value_json,f.valid_from,f.confidence,f.source_chat_id,f.source_message_id,
                  o.value_json,o.valid_from,o.confidence,o.source_chat_id,o.source_message_id,o.source_ai_item_id
           FROM context_conflicts AS c
           JOIN context_facts AS f ON f.fact_id=c.existing_fact_id
           LEFT JOIN context_conflict_observations AS o ON o.conflict_id=c.conflict_id
           WHERE c.status='pending' ORDER BY c.created_at DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    return [
        {
            "conflict_id": row[0],
            "subject_type": row[1],
            "subject_id": row[2],
            "predicate": row[3],
            "created_at": row[4],
            "existing_fact_id": row[5],
            "existing_value": json.loads(row[6]),
            "existing_valid_from": row[7],
            "existing_confidence": row[8],
            "existing_source_chat_id": row[9],
            "existing_source_message_id": row[10],
            "observation_value": json.loads(row[11]) if row[11] else None,
            "observation_valid_from": row[12],
            "observation_confidence": row[13],
            "observation_source_chat_id": row[14],
            "observation_source_message_id": row[15],
            "observation_ai_item_id": row[16],
        }
        for row in rows
    ]


def resolve_temporal_conflict(
    conn: sqlite3.Connection,
    conflict_id: int,
    decision: str,
    note: str = "",
    *,
    manual_value: dict | None = None,
    manual_valid_from: str | None = None,
) -> int | None:
    """Record a manual decision and, if accepted, preserve both fact intervals."""
    if decision not in {"keep_existing", "accept_observation", "ignore"}:
        raise ValueError("Decision must keep_existing, accept_observation, or ignore.")
    row = conn.execute(
        """SELECT c.subject_type,c.subject_id,c.predicate,c.existing_fact_id,
                  f.valid_from,o.value_json,o.valid_from,o.confidence,o.source_chat_id,
                  o.source_message_id,o.source_ai_item_id
           FROM context_conflicts c JOIN context_facts f ON f.fact_id=c.existing_fact_id
           LEFT JOIN context_conflict_observations o ON o.conflict_id=c.conflict_id
           WHERE c.conflict_id=? AND c.status='pending'""",
        (conflict_id,),
    ).fetchone()
    if row is None:
        raise ValueError("Temporal conflict is not pending or does not exist.")
    if (
        decision == "accept_observation"
        and (row[5] is None or row[6] is None)
        and manual_value is None
    ):
        raise ValueError(
            "This legacy conflict has no stored proposed observation; provide a manual value."
        )
    now = utc_now()
    resulting_fact_id: int | None = None
    status = "ignored" if decision == "ignore" else "resolved"
    with conn:
        if decision == "accept_observation":
            if manual_value is not None:
                value_json = json.dumps(
                    manual_value, sort_keys=True, ensure_ascii=False
                )
                valid_from = manual_valid_from or now
                confidence = 1.0
                source_type = "manual"
                source_chat_id = source_message_id = source_ai_item_id = None
            else:
                value_json = row[5]
                valid_from = row[6]
                confidence = row[7]
                source_type = "ai_item"
                source_chat_id, source_message_id, source_ai_item_id = row[8:11]
            is_current = int(valid_from >= row[4])
            cursor = conn.execute(
                """INSERT INTO context_facts(subject_type,subject_id,predicate,value_json,valid_from,valid_to,
                       observed_at,is_current,confidence,source_type,source_chat_id,source_message_id,
                       source_ai_item_id,created_at,updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    *row[:3],
                    value_json,
                    valid_from,
                    None if is_current else row[4],
                    now,
                    is_current,
                    confidence,
                    source_type,
                    source_chat_id,
                    source_message_id,
                    source_ai_item_id,
                    now,
                    now,
                ),
            )
            if cursor.lastrowid is None:
                raise RuntimeError("SQLite did not return an ID for the accepted fact")
            resulting_fact_id = int(cursor.lastrowid)
            if is_current:
                conn.execute(
                    "UPDATE context_facts SET valid_to=?,is_current=0,superseded_by_fact_id=?,updated_at=? WHERE fact_id=?",
                    (valid_from, resulting_fact_id, now, row[3]),
                )
        conn.execute(
            "UPDATE context_conflicts SET status=?,resolution_json=?,resolved_at=? WHERE conflict_id=?",
            (
                status,
                json.dumps({"decision": decision, "note": note}),
                now,
                conflict_id,
            ),
        )
        conn.execute(
            "INSERT INTO context_conflict_decisions(conflict_id,decision,resulting_fact_id,note,decided_at) VALUES (?,?,?,?,?)",
            (conflict_id, decision, resulting_fact_id, note or None, now),
        )
    return resulting_fact_id


def ensure_relationship(
    conn: sqlite3.Connection,
    from_type: str,
    from_id: int,
    to_type: str,
    to_id: int,
    relationship_type: str,
    confidence: float,
    source_chat_id: int | None = None,
    source_message_id: int | None = None,
    valid_from: str | None = None,
) -> None:
    existing = conn.execute(
        "SELECT relationship_id FROM relationships WHERE from_type=? AND from_id=? AND to_type=? AND to_id=? AND relationship_type=? AND is_current=1",
        (from_type, from_id, to_type, to_id, relationship_type),
    ).fetchone()
    if existing:
        return
    now = utc_now()
    conn.execute(
        "INSERT INTO relationships(from_type,from_id,to_type,to_id,relationship_type,valid_from,is_current,confidence,source_chat_id,source_message_id,created_at,updated_at) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?)",
        (
            from_type,
            from_id,
            to_type,
            to_id,
            relationship_type,
            valid_from or now,
            confidence,
            source_chat_id,
            source_message_id,
            now,
            now,
        ),
    )


def current_facts(
    conn: sqlite3.Connection,
    subject_type: str,
    subject_id: int,
    as_of: str | None = None,
    limit: int = 50,
) -> list[dict]:
    if as_of:
        rows = conn.execute(
            "SELECT fact_id,predicate,value_json,valid_from,valid_to,confidence,source_chat_id,source_message_id,source_claim_id FROM context_facts WHERE subject_type=? AND subject_id=? AND valid_from<=? AND (valid_to IS NULL OR valid_to>?) ORDER BY valid_from DESC LIMIT ?",
            (subject_type, subject_id, as_of, as_of, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT fact_id,predicate,value_json,valid_from,valid_to,confidence,source_chat_id,source_message_id,source_claim_id FROM context_facts WHERE subject_type=? AND subject_id=? AND is_current=1 ORDER BY valid_from DESC LIMIT ?",
            (subject_type, subject_id, limit),
        ).fetchall()
    return [
        {
            "fact_id": row[0],
            "predicate": row[1],
            "value": json.loads(row[2]),
            "valid_from": row[3],
            "valid_to": row[4],
            "confidence": row[5],
            "source_chat_id": row[6],
            "source_message_id": row[7],
            "source_claim_id": row[8],
        }
        for row in rows
    ]
