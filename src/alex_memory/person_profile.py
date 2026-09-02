"""Bounded, read-only composition of evidence-backed canonical person profiles."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from statistics import median


_ENTITY_TABLES = {
    "person": ("people", "person_id"),
    "company": ("companies", "company_id"),
    "project": ("projects", "project_id"),
}


def build_person_profile(conn: sqlite3.Connection, person_id: int) -> dict:
    """Return one bounded profile without writing derived or canonical state."""
    entity = conn.execute(
        """SELECT person_id,canonical_name,telegram_user_id,telegram_username,status,
                  created_at,updated_at FROM people WHERE person_id=?""",
        (person_id,),
    ).fetchone()
    if entity is None:
        return {}
    profile = {
        "entity": entity,
        "identity": _identity_state(conn, person_id, entity),
        "aliases": _aliases(conn, person_id),
        "contact": _contact(conn, person_id),
        "context_freshness": _context_freshness(conn, person_id),
        "topics": _topics(conn, person_id),
        "facts": _facts(conn, person_id),
        "relationships": _relationships(conn, person_id),
        "tasks": _tasks(conn, person_id),
        "follow_ups": _follow_ups(conn, person_id),
        "open_loops": _open_loops(conn, person_id),
        "projects": _projects(conn, person_id),
        "events": _events(conn, person_id),
        "profile_claims": _profile_claims(conn, person_id),
        "segments": _segments(conn, person_id),
        "stats": _communication_stats(conn, person_id),
    }
    _attach_evidence(conn, profile["facts"])
    _attach_evidence(conn, profile["relationships"])
    _attach_evidence(conn, profile["tasks"])
    _attach_evidence(conn, profile["follow_ups"])
    _attach_evidence(conn, profile["open_loops"])
    _attach_evidence(conn, profile["events"])
    _attach_evidence(conn, profile["profile_claims"])
    for project in profile["projects"]:
        project["evidence"] = _project_evidence(conn, person_id, project["project_id"])
    profile["summary_evidence"] = _collect_evidence(profile)[:6]
    profile["private_details"] = [
        item
        for item in profile["profile_claims"]
        if item["assertion_kind"] == "direct"
        and item["category"].startswith(
            ("identity.phone", "identity.email", "identity.birthday", "personal.family")
        )
    ][:8]
    profile["uncertain"] = [
        item
        for item in profile["profile_claims"]
        if item["assertion_kind"] in {"third_party", "inference"}
    ][:16]
    profile["contact_briefing"] = _contact_briefing(profile)
    profile["actions"] = _action_items(profile)
    profile["messages"] = _messages(conn, person_id)
    from .profile_enrichment import profile_scan_status

    profile["scan_status"] = profile_scan_status(conn, person_id)
    return profile


def _identity_state(conn: sqlite3.Connection, person_id: int, entity: tuple) -> dict:
    telegram_user_id = entity[2]
    direct_chat = conn.execute(
        "SELECT 1 FROM chats WHERE chat_id=? AND chat_type='user'",
        (telegram_user_id,),
    ).fetchone()
    pending = conn.execute(
        """SELECT COUNT(*) FROM review_queue WHERE status='pending'
           AND subject_type='person' AND subject_id=?""",
        (person_id,),
    ).fetchone()[0]
    claim_reviews = conn.execute(
        """SELECT COUNT(*) FROM semantic_claim_entity_refs
           WHERE entity_type='person' AND canonical_entity_id=? AND resolution_status='review'""",
        (person_id,),
    ).fetchone()[0]
    return {
        "status": entity[4],
        "direct_chat_owned": bool(direct_chat),
        "pending_reviews": int(pending or 0) + int(claim_reviews or 0),
    }


def _topics(conn: sqlite3.Connection, person_id: int) -> list[str]:
    rows = conn.execute(
        """SELECT topic_json FROM current_conversation_context WHERE person_id=?
           ORDER BY last_meaningful_at DESC LIMIT 4""",
        (person_id,),
    ).fetchall()
    values: list[str] = []
    for (payload,) in rows:
        try:
            topics = json.loads(payload)
        except (TypeError, json.JSONDecodeError):
            topics = []
        for topic in topics:
            normalized = _useful_topic(topic)
            if normalized and normalized not in values:
                values.append(normalized)
    return values[:8]


def profile_summary_package(conn: sqlite3.Connection, person_id: int) -> dict:
    """Return bounded canonical rows and their exact evidence for presentation.

    The package deliberately contains only displayable, evidence-backed records.
    It is not a second memory store: callers may use it to decide whether the
    presentation-only summary is stale, and to supply the model with the same
    canonical context the profile renders.
    """
    profile = build_person_profile(conn, person_id)
    # A summary may describe only confirmed, directly sourced profile state.
    # Third-party claims and inferences remain visible in their own labelled
    # profile section but are never summary inputs.
    summary_profile = dict(profile)
    summary_profile["profile_claims"] = [
        item
        for item in profile.get("profile_claims", [])
        if item.get("assertion_kind") == "direct"
    ]
    sources = _collect_evidence(summary_profile)[:12]
    allowed = {(item["chat_id"], item["message_id"]) for item in sources}
    records: list[dict] = []
    for section in (
        "facts",
        "relationships",
        "tasks",
        "follow_ups",
        "open_loops",
        "projects",
        "events",
        "profile_claims",
    ):
        for record in summary_profile.get(section, []):
            citations = [
                f"[{item['chat_id']}/{item['message_id']}]"
                for item in record.get("evidence", [])
                if (item["chat_id"], item["message_id"]) in allowed
            ]
            if not citations:
                continue
            # Keep the model's state input compact and deterministic. Evidence
            # remains authoritative; this only labels the already-rendered row.
            fields = {
                key: value
                for key, value in record.items()
                if key
                not in {
                    "evidence",
                    "details",
                    "description",
                    "summary",
                    "current_summary",
                }
                and value is not None
                and not key.endswith("_id")
            }
            records.append(
                {
                    "section": section,
                    "fields": fields,
                    "evidence": citations,
                }
            )
    return {"sources": sources, "records": records[:32]}


def profile_summary_sources(conn: sqlite3.Connection, person_id: int) -> list[dict]:
    """Return exact, bounded source messages available to an AI profile summary."""
    return profile_summary_package(conn, person_id)["sources"]


def _collect_evidence(profile: dict) -> list[dict]:
    seen: set[tuple[int, int]] = set()
    result: list[dict] = []
    for collection in (
        profile.get("facts", []),
        profile.get("relationships", []),
        profile.get("tasks", []),
        profile.get("follow_ups", []),
        profile.get("open_loops", []),
        profile.get("projects", []),
        profile.get("events", []),
        profile.get("profile_claims", []),
    ):
        for item in collection:
            for evidence in item.get("evidence", []):
                key = (evidence["chat_id"], evidence["message_id"])
                if key not in seen:
                    seen.add(key)
                    result.append(evidence)
    return result


def _aliases(conn: sqlite3.Connection, person_id: int) -> list[str]:
    return [
        str(row[0])
        for row in conn.execute(
            """SELECT alias FROM entity_aliases WHERE entity_type='person' AND entity_id=?
           ORDER BY normalized_alias LIMIT 16""",
            (person_id,),
        )
    ]


def _contact(conn: sqlite3.Connection, person_id: int) -> dict:
    row = conn.execute(
        """SELECT relationship_type,communication_language,communication_style,
                  typical_response_hours,last_contact_at,current_summary,long_term_summary,
                  profile_summary,profile_summary_updated_at
           FROM person_context_state WHERE person_id=?""",
        (person_id,),
    ).fetchone()
    keys = (
        "relationship_type",
        "communication_language",
        "communication_style",
        "typical_response_hours",
        "last_contact_at",
        "current_summary",
        "long_term_summary",
        "profile_summary",
        "profile_summary_updated_at",
    )
    return dict(zip(keys, row, strict=True)) if row else {}


def _context_freshness(conn: sqlite3.Connection, person_id: int) -> dict:
    """Expose materialized conversation freshness without reading message content."""
    updated_at, evidence_through_at, latest_message = conn.execute(
        """SELECT MAX(context.updated_at),MAX(context.evidence_through_at),MAX(message.date)
           FROM current_conversation_context AS context
           LEFT JOIN messages AS message ON message.chat_id=context.chat_id
           WHERE context.person_id=?""",
        (person_id,),
    ).fetchone()
    materialization_dirty = bool(
        conn.execute(
            """SELECT 1 FROM context_invalidations
               WHERE scope_type='person' AND scope_id=?
                 AND status IN ('pending','running','failed') LIMIT 1""",
            (person_id,),
        ).fetchone()
    )
    semantic_pending = bool(
        conn.execute(
            """SELECT 1 FROM current_conversation_context AS context
               LEFT JOIN ai_message_state AS analysis ON analysis.chat_id=context.chat_id
               LEFT JOIN message_classifications AS classification
                 ON classification.chat_id=context.chat_id
               WHERE context.person_id=?
                 AND (COALESCE(analysis.analysis_stale,0)=1 OR COALESCE(classification.context_stale,0)=1)
               LIMIT 1""",
            (person_id,),
        ).fetchone()
    )
    raw_pending = bool(latest_message) and (
        evidence_through_at is None or str(latest_message) > str(evidence_through_at)
    )
    return {
        "state": (
            "materialization dirty"
            if materialization_dirty
            else "semantic pending"
            if semantic_pending
            else "new raw evidence pending"
            if raw_pending
            else "fresh"
        ),
        "context_updated_at": updated_at,
        "evidence_through_at": evidence_through_at,
    }


def _facts(conn: sqlite3.Connection, person_id: int) -> list[dict]:
    rows = conn.execute(
        """SELECT fact_id,predicate,value_json,valid_from,confidence,source_claim_id,
                  source_chat_id,source_message_id,source_ai_item_id
           FROM context_facts WHERE subject_type='person' AND subject_id=? AND is_current=1
           ORDER BY confidence DESC,valid_from DESC LIMIT 12""",
        (person_id,),
    ).fetchall()
    return [
        _record(
            row,
            (
                "fact_id",
                "predicate",
                "value_json",
                "valid_from",
                "confidence",
                "source_claim_id",
                "source_chat_id",
                "source_message_id",
                "source_ai_item_id",
            ),
        )
        for row in rows
    ]


def _profile_claims(conn: sqlite3.Connection, person_id: int) -> list[dict]:
    """Read profile-scoped claims without treating uncertain claims as canonical."""
    rows = conn.execute(
        """SELECT claim_id,claim_type,statement,payload_json,confidence,profile_assertion_kind,
                  profile_valid_from,profile_valid_to,created_at
           FROM semantic_claims WHERE profile_person_id=?
             AND profile_assertion_kind IN ('direct','third_party','inference')
           ORDER BY CASE profile_assertion_kind WHEN 'direct' THEN 0 WHEN 'inference' THEN 1 ELSE 2 END,
                    COALESCE(profile_valid_from,created_at) DESC,claim_id DESC LIMIT 32""",
        (person_id,),
    ).fetchall()
    result = []
    for row in rows:
        payload = _json_value(row[3])
        legacy = payload.get("legacy_item", {}) if isinstance(payload, dict) else {}
        title = str(legacy.get("title") or row[2])
        category, _, label = title.partition(":")
        result.append(
            {
                "claim_id": int(row[0]),
                "source_claim_id": int(row[0]),
                "claim_type": row[1],
                "title": label.strip() or title,
                "details": legacy.get("details", ""),
                "category": category.strip() or "profile.context",
                "confidence": float(row[4]),
                "assertion_kind": row[5],
                "valid_from": row[6],
                "valid_to": row[7],
                "created_at": row[8],
            }
        )
    return result


def _relationships(conn: sqlite3.Connection, person_id: int) -> list[dict]:
    rows = conn.execute(
        """SELECT relationship_id,from_type,from_id,to_type,to_id,relationship_type,
                  valid_from,confidence,source_claim_id,source_chat_id,source_message_id
           FROM relationships WHERE is_current=1
             AND ((from_type='person' AND from_id=?) OR (to_type='person' AND to_id=?))
           ORDER BY confidence DESC,valid_from DESC LIMIT 12""",
        (person_id, person_id),
    ).fetchall()
    result = []
    for row in rows:
        item = _record(
            row,
            (
                "relationship_id",
                "from_type",
                "from_id",
                "to_type",
                "to_id",
                "relationship_type",
                "valid_from",
                "confidence",
                "source_claim_id",
                "source_chat_id",
                "source_message_id",
            ),
        )
        other_type, other_id = (
            (item["to_type"], item["to_id"])
            if item["from_type"] == "person" and item["from_id"] == person_id
            else (item["from_type"], item["from_id"])
        )
        item["other_type"], item["other_id"] = other_type, other_id
        item["other_name"] = _entity_name(conn, other_type, other_id)
        result.append(item)
    return result


def _tasks(conn: sqlite3.Connection, person_id: int) -> list[dict]:
    rows = conn.execute(
        """SELECT task_id,title,details,status,owner,due_date,updated_at,related_company_id,
                  related_project_id,source_claim_id,source_chat_id,source_item_id
           FROM tasks WHERE related_person_id=? AND status IN ('open','waiting')
           ORDER BY CASE status WHEN 'waiting' THEN 0 ELSE 1 END,due_date,updated_at DESC LIMIT 16""",
        (person_id,),
    ).fetchall()
    return [
        _record(
            row,
            (
                "task_id",
                "title",
                "details",
                "status",
                "owner",
                "due_date",
                "updated_at",
                "company_id",
                "project_id",
                "source_claim_id",
                "source_chat_id",
                "source_ai_item_id",
            ),
        )
        for row in rows
    ]


def _follow_ups(conn: sqlite3.Connection, person_id: int) -> list[dict]:
    rows = conn.execute(
        """SELECT follow_up_id,title,reason,status,priority,due_at,last_contact_at,updated_at,task_id,
                  project_id,source_chat_id,source_message_id
           FROM follow_ups WHERE person_id=? AND status IN ('open','snoozed')
           ORDER BY due_at,updated_at DESC LIMIT 12""",
        (person_id,),
    ).fetchall()
    return [
        _record(
            row,
            (
                "follow_up_id",
                "title",
                "reason",
                "status",
                "priority",
                "due_at",
                "last_contact_at",
                "updated_at",
                "task_id",
                "project_id",
                "source_chat_id",
                "source_message_id",
            ),
        )
        for row in rows
    ]


def _open_loops(conn: sqlite3.Connection, person_id: int) -> list[dict]:
    rows = conn.execute(
        """SELECT loop_id,title,owner,status,loop_type,project_id,task_id,updated_at,source_chat_id,
                  source_message_id FROM conversation_open_loops WHERE person_id=?
                  AND status IN ('open','waiting') ORDER BY updated_at DESC LIMIT 12""",
        (person_id,),
    ).fetchall()
    return [
        _record(
            row,
            (
                "loop_id",
                "title",
                "owner",
                "status",
                "loop_type",
                "project_id",
                "task_id",
                "updated_at",
                "source_chat_id",
                "source_message_id",
            ),
        )
        for row in rows
    ]


def _projects(conn: sqlite3.Connection, person_id: int) -> list[dict]:
    rows = conn.execute(
        """SELECT p.project_id,p.canonical_name,ppc.role,ppc.status,ppc.current_summary,
                  ppc.last_activity_at,ppc.confidence FROM person_project_context AS ppc
           JOIN projects AS p ON p.project_id=ppc.project_id WHERE ppc.person_id=?
           ORDER BY ppc.last_activity_at DESC LIMIT 8""",
        (person_id,),
    ).fetchall()
    return [
        _record(
            row,
            (
                "project_id",
                "name",
                "role",
                "status",
                "summary",
                "last_activity_at",
                "confidence",
            ),
        )
        for row in rows
    ]


def _events(conn: sqlite3.Connection, person_id: int) -> list[dict]:
    rows = conn.execute(
        """SELECT event_id,event_type,title,description,occurred_at,confidence,source_claim_id,
                  source_chat_id,source_message_id,source_ai_item_id FROM context_events
           WHERE person_id=? AND event_type != 'observation_recorded'
           ORDER BY occurred_at DESC,created_at DESC LIMIT 12""",
        (person_id,),
    ).fetchall()
    return [
        _record(
            row,
            (
                "event_id",
                "event_type",
                "title",
                "description",
                "occurred_at",
                "confidence",
                "source_claim_id",
                "source_chat_id",
                "source_message_id",
                "source_ai_item_id",
            ),
        )
        for row in rows
    ]


def _segments(conn: sqlite3.Connection, person_id: int) -> list[dict]:
    rows = conn.execute(
        """SELECT s.started_at,s.ended_at,p.canonical_name,s.summary FROM conversation_contact_segments AS s
           LEFT JOIN projects AS p ON p.project_id=s.primary_project_id
           WHERE s.person_id=? ORDER BY s.started_at DESC LIMIT 8""",
        (person_id,),
    ).fetchall()
    return [
        _record(row, ("started_at", "ended_at", "project_name", "summary"))
        for row in rows
    ]


def _communication_stats(conn: sqlite3.Connection, person_id: int) -> dict:
    chat_ids = _linked_chat_ids(conn, person_id)
    if not chat_ids:
        return {"conversations": []}
    scope, scope_params = _profile_message_scope(conn, person_id)
    marks = ",".join("?" for _ in chat_ids)
    totals = conn.execute(
        f"""SELECT COUNT(*),SUM(CASE WHEN m.is_outgoing=1 THEN 1 ELSE 0 END),
                   MIN(m.date),MAX(m.date),COUNT(DISTINCT substr(m.date,1,10))
            FROM messages AS m
            WHERE m.chat_id IN ({marks}) AND COALESCE(m.is_deleted,0)=0
              AND ({scope})""",
        [*sorted(chat_ids), *scope_params],
    ).fetchone()
    rows = conn.execute(
        f"""SELECT m.chat_id,COALESCE(c.title,CAST(m.chat_id AS TEXT)),COUNT(*),
                   SUM(CASE WHEN m.is_outgoing=1 THEN 1 ELSE 0 END),
                   MIN(m.date),MAX(m.date),COUNT(DISTINCT substr(m.date,1,10))
            FROM messages AS m LEFT JOIN chats AS c ON c.chat_id=m.chat_id
            WHERE m.chat_id IN ({marks}) AND COALESCE(m.is_deleted,0)=0
              AND ({scope})
            GROUP BY m.chat_id ORDER BY MAX(m.date) DESC LIMIT 8""",
        [*sorted(chat_ids), *scope_params],
    ).fetchall()
    conversations = [
        {
            "chat_id": row[0],
            "title": row[1],
            "total": int(row[2]),
            "outgoing": int(row[3] or 0),
            "incoming": int(row[2] - (row[3] or 0)),
            "first_at": row[4],
            "last_at": row[5],
            "active_days": int(row[6] or 0),
        }
        for row in rows
    ]
    return {
        "total": int(totals[0] or 0),
        "outgoing": int(totals[1] or 0),
        "incoming": int((totals[0] or 0) - (totals[1] or 0)),
        "first_at": totals[2],
        "last_at": totals[3],
        "active_days": int(totals[4] or 0),
        "conversations": conversations,
        "response_times": _response_times(conn, person_id),
        "activity": _direct_activity(conn, person_id),
    }


def _direct_activity(conn: sqlite3.Connection, person_id: int) -> dict:
    """Deterministic initiation, gap, and recent-activity metrics for one direct chat."""
    row = conn.execute(
        """SELECT telegram_user_id FROM people WHERE person_id=?""", (person_id,)
    ).fetchone()
    if row is None or row[0] is None:
        return {}
    rows = conn.execute(
        """SELECT date,is_outgoing FROM messages WHERE chat_id=?
           AND COALESCE(is_deleted,0)=0 AND TRIM(COALESCE(text,''))<>'' AND date IS NOT NULL
           ORDER BY date,message_id""",
        (row[0],),
    ).fetchall()
    parsed = []
    for value, outgoing in rows:
        try:
            parsed.append(
                (
                    datetime.fromisoformat(str(value).replace("Z", "+00:00")),
                    bool(outgoing),
                )
            )
        except ValueError:
            continue
    initiators = {"me": 0, "them": 0}
    gaps = 0
    previous: datetime | None = None
    for current, outgoing in parsed:
        if previous is None or current - previous >= timedelta(days=14):
            initiators["me" if outgoing else "them"] += 1
        if previous is not None and current - previous >= timedelta(days=30):
            gaps += 1
        previous = current
    periods = sum(initiators.values())
    usual = None
    if periods >= 3 and initiators["me"] != initiators["them"]:
        usual = "me" if initiators["me"] > initiators["them"] else "them"
    now = datetime.now(parsed[-1][0].tzinfo) if parsed else None
    return {
        "initiation_periods": periods,
        "initiated_by_me": initiators["me"],
        "initiated_by_them": initiators["them"],
        "usual_initiator": usual,
        "long_gaps": gaps,
        "recent_7d": sum(
            1 for value, _ in parsed if now and now - value <= timedelta(days=7)
        ),
        "recent_30d": sum(
            1 for value, _ in parsed if now and now - value <= timedelta(days=30)
        ),
    }


def _response_times(conn: sqlite3.Connection, person_id: int) -> dict:
    """Measure only consecutive direction changes in the canonical direct chat."""
    row = conn.execute(
        """SELECT p.telegram_user_id FROM people AS p JOIN chats AS c
           ON c.chat_id=p.telegram_user_id AND c.chat_type='user' WHERE p.person_id=?""",
        (person_id,),
    ).fetchone()
    if row is None:
        return {}
    rows = conn.execute(
        """SELECT date,is_outgoing FROM messages WHERE chat_id=?
           AND COALESCE(is_deleted,0)=0 AND TRIM(COALESCE(text,''))<>'' AND date IS NOT NULL
           ORDER BY date,message_id""",
        (row[0],),
    ).fetchall()
    theirs: list[float] = []
    mine: list[float] = []
    previous: tuple[datetime, bool] | None = None
    for date_value, outgoing in rows:
        try:
            current = datetime.fromisoformat(str(date_value).replace("Z", "+00:00"))
        except ValueError:
            continue
        direction = bool(outgoing)
        if previous is not None and direction != previous[1]:
            elapsed = current - previous[0]
            if timedelta(0) <= elapsed <= timedelta(days=7):
                (mine if direction else theirs).append(elapsed.total_seconds() / 3600)
        previous = (current, direction)
    return {
        "their_reply_hours": round(float(median(theirs)), 1) if theirs else None,
        "their_reply_samples": len(theirs),
        "my_reply_hours": round(float(median(mine)), 1) if mine else None,
        "my_reply_samples": len(mine),
    }


def _project_evidence(
    conn: sqlite3.Connection, person_id: int, project_id: int
) -> list[dict]:
    """Resolve only a direct canonical relationship or task linkage as project proof."""
    relationship = conn.execute(
        """SELECT source_claim_id,source_chat_id,source_message_id FROM relationships
           WHERE is_current=1 AND ((from_type='person' AND from_id=? AND to_type='project' AND to_id=?)
              OR (to_type='person' AND to_id=? AND from_type='project' AND from_id=?))
           ORDER BY valid_from DESC LIMIT 1""",
        (person_id, project_id, person_id, project_id),
    ).fetchone()
    if relationship is not None:
        evidence = _evidence(
            conn,
            _record(
                relationship,
                ("source_claim_id", "source_chat_id", "source_message_id"),
            ),
        )
        if evidence:
            return evidence
    task = conn.execute(
        """SELECT source_claim_id,source_chat_id,source_item_id FROM tasks
           WHERE related_person_id=? AND related_project_id=?
             AND status IN ('open','waiting')
           ORDER BY updated_at DESC LIMIT 1""",
        (person_id, project_id),
    ).fetchone()
    return (
        _evidence(
            conn,
            _record(task, ("source_claim_id", "source_chat_id", "source_ai_item_id")),
        )
        if task is not None
        else []
    )


def _contact_briefing(profile: dict) -> dict:
    """Create a bounded, presentation-only briefing from exact profile evidence."""
    task_ids = {item["task_id"] for item in profile["tasks"]}
    loops = [
        item
        for item in profile["open_loops"]
        if item.get("task_id") is None or item["task_id"] not in task_ids
    ]
    commitments = profile["tasks"] + loops
    from_them = [item for item in commitments if item.get("owner") == "other"][:6]
    from_me = [item for item in commitments if item.get("owner") == "me"][:6]
    questions = [item for item in loops if item.get("loop_type") == "question"][:6]
    active_projects = [
        item
        for item in profile["projects"]
        if item.get("status") == "active" and item.get("evidence")
    ][:6]
    recent_changes = [item for item in profile["events"] if item.get("evidence")][:6]
    connections = [
        item
        for item in profile["relationships"]
        if item.get("evidence")
        and item.get("other_type") in {"person", "company", "project"}
    ][:6]
    candidates = [
        *profile["tasks"],
        *loops,
        *profile["follow_ups"],
        *profile["events"],
        *profile["facts"],
        *profile["relationships"],
    ]
    dated = [
        (evidence["date"], item, evidence)
        for item in candidates
        for evidence in item.get("evidence", [])
        if evidence.get("date")
    ]
    latest = max(dated, key=lambda item: item[0], default=None)
    return {
        "last_interaction": (
            {"record": latest[1], "evidence": latest[2]} if latest is not None else None
        ),
        "waiting_from_them": from_them,
        "waiting_from_me": from_me,
        "follow_ups": profile["follow_ups"][:6],
        "active_projects": active_projects,
        "unresolved_questions": questions,
        "recent_changes": recent_changes,
        "connections": connections,
    }


_TOPIC_NOISE = frozenset(
    {
        "for",
        "sender",
        "requested",
        "request",
        "details",
        "detail",
        "message",
        "from",
        "with",
        "that",
        "this",
        "have",
        "need",
        "the",
        "and",
        "are",
        "для",
        "от",
        "это",
        "что",
        "как",
        "или",
        "детали",
        "подробности",
    }
)


def _useful_topic(value: object) -> str | None:
    """Filter legacy materialized topic artefacts at the presentation boundary."""
    if not isinstance(value, str):
        return None
    normalized = " ".join(value.split()).casefold()
    if not normalized or normalized in _TOPIC_NOISE or normalized.isdigit():
        return None
    return normalized


def _action_items(profile: dict, *, as_of: datetime | None = None) -> list[dict]:
    """Normalize bounded operational rows for presentation without changing state."""
    now = as_of or datetime.now(UTC)
    project_status = {
        item["project_id"]: item.get("status", "active") for item in profile["projects"]
    }
    seen_tasks: set[int] = set()
    records: list[dict] = []
    for source, collection in (
        ("task", profile["tasks"]),
        ("follow_up", profile["follow_ups"]),
        ("loop", profile["open_loops"]),
    ):
        for value in collection:
            if source == "loop" and value.get("task_id") in seen_tasks:
                continue
            if source == "task":
                seen_tasks.add(value["task_id"])
            record = dict(value)
            record["record_type"] = source
            record["record_id"] = value.get(f"{source}_id")
            record["last_activity_at"] = (
                value.get("updated_at")
                or value.get("last_contact_at")
                or value.get("due_at")
            )
            record["due"] = value.get("due_date") or value.get("due_at")
            record["project_status"] = project_status.get(value.get("project_id"))
            record["certainty"] = _certainty(record)
            record["action_state"] = _action_state(record, now)
            records.append(record)
    order = {
        "ACTION": 0,
        "WAITING": 1,
        "BLOCKED": 2,
        "STALE": 3,
        "SCHEDULED": 4,
        "UNCERTAIN": 5,
        "DONE": 6,
    }
    return sorted(
        records,
        key=lambda item: (
            order[item["action_state"]],
            item.get("due") or "9999-12-31",
            item.get("last_activity_at") or "",
            str(item.get("title", "")).casefold(),
        ),
    )


def _certainty(record: dict) -> str:
    if record.get("assertion_kind") == "direct" or record.get("source_claim_id"):
        return "confirmed"
    if (
        record.get("assertion_kind") == "third_party"
        or float(record.get("confidence") or 0) >= 0.85
    ):
        return "probable"
    return "uncertain"


def _action_state(record: dict, now: datetime) -> str:
    status, owner = (
        str(record.get("status") or "open"),
        str(record.get("owner") or "unknown"),
    )
    if status in {"done", "canceled", "cancelled", "resolved"}:
        return "DONE"
    if status == "blocked" or record.get("project_status") == "blocked":
        return "BLOCKED"
    if status == "waiting" or owner == "other":
        return "WAITING"
    if status == "snoozed" or _future_date(record.get("due"), now):
        return "SCHEDULED"
    if owner == "unknown" or float(record.get("confidence") or 0) < 0.75:
        return "UNCERTAIN"
    last = _parse_datetime(record.get("last_activity_at"))
    if last is not None and now - last >= timedelta(days=30):
        return "STALE"
    return "ACTION"


def _future_date(value: object, now: datetime) -> bool:
    parsed = _parse_datetime(value)
    return bool(parsed and parsed > now)


def _parse_datetime(value: object) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _messages(conn: sqlite3.Connection, person_id: int) -> list[dict]:
    """Return a bounded raw-history list for the terminal Messages screen."""
    chat_ids = sorted(_linked_chat_ids(conn, person_id))
    if not chat_ids:
        return []
    scope, scope_params = _profile_message_scope(conn, person_id)
    marks = ",".join("?" for _ in chat_ids)
    rows = conn.execute(
        f"""SELECT m.chat_id,m.message_id,m.date,m.text,m.is_outgoing,m.sender_id,
                   COALESCE(c.title,CAST(m.chat_id AS TEXT))
              FROM messages AS m LEFT JOIN chats AS c ON c.chat_id=m.chat_id
             WHERE m.chat_id IN ({marks}) AND COALESCE(m.is_deleted,0)=0
               AND TRIM(COALESCE(m.text,''))<>''
               AND ({scope})
             ORDER BY m.date DESC,m.message_id DESC LIMIT 80""",
        [*chat_ids, *scope_params],
    ).fetchall()
    return [
        {
            "chat_id": int(row[0]),
            "message_id": int(row[1]),
            "date": row[2],
            "text": str(row[3])[:1_000],
            "speaker": "You" if row[4] else "Contact",
            "conversation": str(row[6]),
        }
        for row in rows
    ]


def _profile_message_scope(
    conn: sqlite3.Connection, person_id: int
) -> tuple[str, list[int]]:
    """Keep group history attributable to the selected person or to the owner.

    A linked group establishes context, not ownership of every participant's
    messages. Direct-chat history remains complete; group rows include only the
    selected person's sender ID and explicitly retained outgoing owner messages.
    """
    row = conn.execute(
        "SELECT telegram_user_id FROM people WHERE person_id=?", (person_id,)
    ).fetchone()
    telegram_user_id = int(row[0]) if row is not None and row[0] is not None else None
    if telegram_user_id is None:
        return "m.is_outgoing=1", []
    direct = conn.execute(
        "SELECT 1 FROM chats WHERE chat_id=? AND chat_type='user'", (telegram_user_id,)
    ).fetchone()
    if direct is not None:
        return "m.chat_id=? OR m.sender_id=? OR m.is_outgoing=1", [telegram_user_id] * 2
    return "m.sender_id=? OR m.is_outgoing=1", [telegram_user_id]


def _linked_chat_ids(conn: sqlite3.Connection, person_id: int) -> set[int]:
    rows = conn.execute(
        """SELECT source_chat_id FROM ai_items WHERE person_id=? AND source_chat_id IS NOT NULL
           UNION SELECT source_chat_id FROM tasks WHERE related_person_id=? AND source_chat_id IS NOT NULL
           UNION SELECT source_chat_id FROM context_events WHERE person_id=? AND source_chat_id IS NOT NULL
           UNION SELECT source_chat_id FROM context_facts WHERE subject_type='person' AND subject_id=? AND source_chat_id IS NOT NULL
           UNION SELECT source_chat_id FROM relationships WHERE ((from_type='person' AND from_id=?) OR (to_type='person' AND to_id=?)) AND source_chat_id IS NOT NULL
           UNION SELECT chat_id FROM chats WHERE chat_type='user' AND chat_id=(SELECT telegram_user_id FROM people WHERE person_id=?)""",
        (person_id, person_id, person_id, person_id, person_id, person_id, person_id),
    ).fetchall()
    return {int(row[0]) for row in rows if row[0] is not None}


def _attach_evidence(conn: sqlite3.Connection, records: Iterable[dict]) -> None:
    for record in records:
        record["evidence"] = _evidence(conn, record)


def _evidence(conn: sqlite3.Connection, record: dict) -> list[dict]:
    claim_id = record.get("source_claim_id")
    if claim_id is not None:
        rows = conn.execute(
            """SELECT m.chat_id,m.message_id,m.date,m.text,m.sender_id,m.is_outgoing FROM semantic_claim_evidence AS e
               JOIN messages AS m ON m.chat_id=e.source_chat_id AND m.message_id=e.source_message_id
               WHERE e.claim_id=? AND COALESCE(m.is_deleted,0)=0 ORDER BY e.ordinal LIMIT 3""",
            (claim_id,),
        ).fetchall()
    else:
        chat_id, message_id = (
            record.get("source_chat_id"),
            record.get("source_message_id"),
        )
        if message_id is None and record.get("source_ai_item_id") is not None:
            item = conn.execute(
                "SELECT source_chat_id,source_message_id FROM ai_items WHERE item_id=?",
                (record["source_ai_item_id"],),
            ).fetchone()
            chat_id, message_id = item if item else (None, None)
        rows = (
            conn.execute(
                "SELECT chat_id,message_id,date,text,sender_id,is_outgoing FROM messages WHERE chat_id=? AND message_id=? AND COALESCE(is_deleted,0)=0",
                (chat_id, message_id),
            ).fetchall()
            if chat_id is not None and message_id is not None
            else []
        )
    return [
        {
            "chat_id": int(row[0]),
            "message_id": int(row[1]),
            "date": row[2],
            "text": str(row[3] or "")[:500],
            "speaker": "You"
            if row[5]
            else (f"Sender {row[4]}" if row[4] is not None else "Other"),
        }
        for row in rows
    ]


def _entity_name(
    conn: sqlite3.Connection, entity_type: str, entity_id: int
) -> str | None:
    table = _ENTITY_TABLES.get(entity_type)
    if table is None:
        return None
    row = conn.execute(
        f"SELECT canonical_name FROM {table[0]} WHERE {table[1]}=?", (entity_id,)
    ).fetchone()
    return str(row[0]) if row else None


def _record(row: tuple, keys: tuple[str, ...]) -> dict:
    item = dict(zip(keys, row, strict=True))
    if "value_json" in item:
        try:
            item["value"] = json.loads(item["value_json"])
        except (TypeError, json.JSONDecodeError):
            item["value"] = item["value_json"]
    return item


def _json_value(value: object) -> object:
    try:
        return json.loads(str(value))
    except (TypeError, json.JSONDecodeError):
        return {}
