from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass

from .config import Settings
from .schema_support import (
    apply_compatibility_columns,
    apply_intelligence_version_columns,
    create_fts,
    create_source_evidence_tables,
    rebuild_fts,
)


SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_evidence (
    evidence_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_name TEXT NOT NULL,
    source_account_id TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    source_item_id TEXT NOT NULL,
    content_type TEXT NOT NULL DEFAULT 'message',
    author_id TEXT,
    occurred_at TEXT,
    observed_at TEXT NOT NULL,
    content TEXT,
    raw_locator_json TEXT NOT NULL DEFAULT '{}',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    edited_at TEXT,
    deleted_at TEXT,
    is_deleted INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(source_name, source_account_id, conversation_id, source_item_id)
);
CREATE INDEX IF NOT EXISTS idx_source_evidence_conversation_time
ON source_evidence(source_name, source_account_id, conversation_id, occurred_at);

CREATE TABLE IF NOT EXISTS source_evidence_versions (
    version_id INTEGER PRIMARY KEY AUTOINCREMENT,
    evidence_id INTEGER NOT NULL,
    content TEXT,
    captured_at TEXT NOT NULL,
    reason TEXT NOT NULL CHECK(reason IN ('initial', 'edited', 'deleted'))
);
CREATE INDEX IF NOT EXISTS idx_source_evidence_versions_evidence
ON source_evidence_versions(evidence_id, version_id);

CREATE TABLE IF NOT EXISTS chats (
    chat_id INTEGER PRIMARY KEY,
    title TEXT,
    username TEXT,
    chat_type TEXT,
    is_bot INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS messages (
    chat_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    sender_id INTEGER,
    date TEXT,
    text TEXT,
    reply_to_message_id INTEGER,
    is_outgoing INTEGER,
    has_media INTEGER,
    is_forwarded INTEGER NOT NULL DEFAULT 0,
    forward_source TEXT,
    edited_at TEXT,
    is_deleted INTEGER NOT NULL DEFAULT 0,
    deleted_at TEXT,
    PRIMARY KEY (chat_id, message_id)
);

CREATE TABLE IF NOT EXISTS message_versions (
    version_id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    text TEXT,
    captured_at TEXT NOT NULL,
    reason TEXT NOT NULL CHECK (reason IN ('initial', 'edited', 'deleted'))
);

CREATE INDEX IF NOT EXISTS idx_message_versions_message
ON message_versions(chat_id, message_id, version_id);

CREATE TABLE IF NOT EXISTS sync_state (
    chat_id INTEGER PRIMARY KEY,
    bootstrap_complete INTEGER NOT NULL DEFAULT 0,
    bootstrap_mode TEXT,
    group_total_at_bootstrap INTEGER,
    last_sync_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS ai_batches (
    batch_id INTEGER PRIMARY KEY AUTOINCREMENT,
    model TEXT NOT NULL,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    message_count INTEGER NOT NULL,
    chat_id INTEGER,
    summary TEXT,
    error TEXT,
    prompt_chars INTEGER NOT NULL DEFAULT 0,
    response_json TEXT,
    returned_item_count INTEGER NOT NULL DEFAULT 0,
    saved_item_count INTEGER NOT NULL DEFAULT 0,
    rejected_item_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS ai_jobs (
    job_id INTEGER PRIMARY KEY AUTOINCREMENT,
    lane TEXT NOT NULL CHECK (lane IN ('daily', 'history')),
    chat_id INTEGER NOT NULL,
    first_message_id INTEGER NOT NULL,
    last_message_id INTEGER NOT NULL,
    date_from TEXT,
    date_to TEXT,
    message_count INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'done', 'failed')),
    provider TEXT,
    model TEXT,
    fallback_used INTEGER NOT NULL DEFAULT 0,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    UNIQUE(lane, chat_id, first_message_id, last_message_id)
);

CREATE TABLE IF NOT EXISTS ai_message_state (
    chat_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    batch_id INTEGER,
    analysis_version INTEGER NOT NULL DEFAULT 1,
    context_version_used INTEGER NOT NULL DEFAULT 1,
    analysis_stale INTEGER NOT NULL DEFAULT 0,
    analyzed_at TEXT NOT NULL,
    PRIMARY KEY (chat_id, message_id)
);

CREATE TABLE IF NOT EXISTS message_classifications (
    chat_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    conversation_type TEXT NOT NULL,
    content_type TEXT NOT NULL,
    actionability TEXT NOT NULL,
    importance TEXT NOT NULL,
    content_scope TEXT NOT NULL,
    information_scope TEXT NOT NULL DEFAULT 'unknown',
    temporal_relevance TEXT NOT NULL,
    potential_state_change INTEGER NOT NULL DEFAULT 0,
    is_forwarded INTEGER NOT NULL DEFAULT 0,
    topic_json TEXT NOT NULL DEFAULT '[]',
    classifier_type TEXT NOT NULL,
    provider TEXT,
    model TEXT,
    confidence REAL NOT NULL,
    classification_version INTEGER NOT NULL,
    context_version INTEGER NOT NULL DEFAULT 1,
    context_stale INTEGER NOT NULL DEFAULT 0,
    classified_at TEXT NOT NULL,
    PRIMARY KEY (chat_id, message_id)
);
CREATE INDEX IF NOT EXISTS idx_message_classifications_retrieval
ON message_classifications(importance, content_type, actionability, temporal_relevance);

CREATE TABLE IF NOT EXISTS conversation_analysis_state (
    chat_id INTEGER PRIMARY KEY,
    covered_until_message_id INTEGER,
    covered_until_date TEXT,
    message_count_analyzed INTEGER NOT NULL DEFAULT 0,
    classification_complete INTEGER NOT NULL DEFAULT 0,
    semantic_analysis_complete INTEGER NOT NULL DEFAULT 0,
    context_version INTEGER NOT NULL DEFAULT 1,
    last_analyzed_at TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ai_items (
    item_id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER NOT NULL,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    details TEXT NOT NULL,
    status TEXT NOT NULL,
    owner TEXT NOT NULL,
    due_date TEXT,
    person TEXT,
    company TEXT,
    amount REAL,
    currency TEXT,
    confidence REAL NOT NULL,
    source_chat_id INTEGER NOT NULL,
    source_message_id INTEGER NOT NULL,
    source_date TEXT,
    created_at TEXT NOT NULL,
    dedupe_key TEXT NOT NULL UNIQUE
);

CREATE INDEX IF NOT EXISTS idx_messages_date
ON messages(date);

CREATE INDEX IF NOT EXISTS idx_messages_sender
ON messages(sender_id);

CREATE INDEX IF NOT EXISTS idx_ai_items_kind_status
ON ai_items(kind, status);

CREATE INDEX IF NOT EXISTS idx_ai_items_due_date
ON ai_items(due_date);

CREATE INDEX IF NOT EXISTS idx_ai_jobs_queue
ON ai_jobs(lane, status, job_id);

CREATE TABLE IF NOT EXISTS app_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS people (
    person_id INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_name TEXT NOT NULL,
    telegram_user_id INTEGER UNIQUE,
    telegram_username TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS companies (
    company_id INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_name TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
    project_id INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_name TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS entity_aliases (
    alias_id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL CHECK (entity_type IN ('person', 'company', 'project')),
    entity_id INTEGER NOT NULL,
    alias TEXT NOT NULL,
    normalized_alias TEXT NOT NULL,
    source TEXT,
    confidence REAL,
    created_at TEXT NOT NULL,
    UNIQUE(entity_type, normalized_alias, entity_id)
);

CREATE INDEX IF NOT EXISTS idx_entity_aliases_lookup
ON entity_aliases(entity_type, normalized_alias);

CREATE TABLE IF NOT EXISTS entity_relationships (
    relationship_id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_type TEXT NOT NULL,
    from_id INTEGER NOT NULL,
    to_type TEXT NOT NULL,
    to_id INTEGER NOT NULL,
    relationship_type TEXT NOT NULL,
    confidence REAL,
    source_item_id INTEGER,
    created_at TEXT NOT NULL,
    UNIQUE(from_type, from_id, to_type, to_id, relationship_type)
);

CREATE TABLE IF NOT EXISTS entity_merge_candidates (
    candidate_id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,
    normalized_alias TEXT NOT NULL,
    entity_ids_json TEXT NOT NULL,
    reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'resolved', 'ignored')),
    created_at TEXT NOT NULL,
    resolved_at TEXT,
    UNIQUE(entity_type, normalized_alias, status)
);

CREATE TABLE IF NOT EXISTS review_queue (
    review_id INTEGER PRIMARY KEY AUTOINCREMENT,
    review_type TEXT NOT NULL,
    subject_type TEXT NOT NULL,
    subject_id INTEGER,
    payload_json TEXT NOT NULL,
    confidence REAL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
    created_at TEXT NOT NULL,
    resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS tasks (
    task_id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    normalized_title TEXT NOT NULL,
    details TEXT,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'waiting', 'done', 'canceled')),
    owner TEXT NOT NULL DEFAULT 'me',
    related_person_id INTEGER,
    related_company_id INTEGER,
    related_project_id INTEGER,
    source_chat_id INTEGER,
    due_date TEXT,
    confidence REAL NOT NULL DEFAULT 1.0,
    source_item_id INTEGER,
    manual_updated_at TEXT,
    manual_status_locked INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tasks_status_due
ON tasks(status, due_date);
CREATE INDEX IF NOT EXISTS idx_tasks_match
ON tasks(normalized_title, source_chat_id, related_person_id);

CREATE TABLE IF NOT EXISTS task_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    source TEXT NOT NULL,
    source_item_id INTEGER,
    payload_json TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_task_events_task
ON task_events(task_id, created_at);

CREATE TABLE IF NOT EXISTS memory_chunks (
    chunk_id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    batch_id INTEGER UNIQUE,
    job_id INTEGER,
    date_from TEXT,
    date_to TEXT,
    summary TEXT NOT NULL,
    provider TEXT,
    model TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_memory_chunks_chat_date
ON memory_chunks(chat_id, date_from, date_to);

CREATE TABLE IF NOT EXISTS chat_daily_summaries (
    chat_id INTEGER NOT NULL,
    summary_date TEXT NOT NULL,
    summary TEXT NOT NULL,
    chunk_count INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(chat_id, summary_date)
);

CREATE TABLE IF NOT EXISTS chat_monthly_summaries (
    chat_id INTEGER NOT NULL,
    summary_month TEXT NOT NULL,
    summary TEXT NOT NULL,
    day_count INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(chat_id, summary_month)
);

CREATE TABLE IF NOT EXISTS entity_memory (
    entity_type TEXT NOT NULL,
    entity_id INTEGER NOT NULL,
    memory_key TEXT NOT NULL,
    summary TEXT NOT NULL,
    source_item_id INTEGER,
    confidence REAL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(entity_type, entity_id, memory_key)
);

CREATE TABLE IF NOT EXISTS daily_briefs (
    brief_date TEXT PRIMARY KEY,
    data_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS follow_ups (
    follow_up_id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','snoozed','done','cancelled')),
    priority TEXT NOT NULL DEFAULT 'normal' CHECK(priority IN ('critical','high','normal','low')),
    person_id INTEGER,
    company_id INTEGER,
    project_id INTEGER,
    task_id INTEGER,
    reason TEXT NOT NULL,
    due_at TEXT,
    last_contact_at TEXT,
    source_chat_id INTEGER,
    source_message_id INTEGER,
    confidence REAL NOT NULL DEFAULT 1.0,
    dedupe_key TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    resolved_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_follow_ups_status_due ON follow_ups(status, due_at);
CREATE INDEX IF NOT EXISTS idx_follow_ups_person ON follow_ups(person_id, status);

CREATE TABLE IF NOT EXISTS chat_ai_policy (
    chat_id INTEGER PRIMARY KEY,
    mode TEXT NOT NULL CHECK(mode IN ('auto','include','exclude','classify_only','news_only')),
    reason TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_feedback (
    feedback_id INTEGER PRIMARY KEY AUTOINCREMENT,
    feedback_type TEXT NOT NULL,
    entity_type TEXT,
    entity_id INTEGER,
    payload_json TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'user',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_feedback_entity ON user_feedback(entity_type, entity_id, feedback_type);

CREATE TABLE IF NOT EXISTS notification_outbox (
    notification_id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    priority TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    entity_type TEXT,
    entity_id INTEGER,
    scheduled_at TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','sent','cancelled')),
    dedupe_key TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    sent_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_notification_pending ON notification_outbox(status, scheduled_at);

CREATE TABLE IF NOT EXISTS context_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    title TEXT,
    description TEXT,
    occurred_at TEXT,
    observed_at TEXT NOT NULL,
    person_id INTEGER,
    company_id INTEGER,
    project_id INTEGER,
    task_id INTEGER,
    source_type TEXT,
    source_chat_id INTEGER,
    source_message_id INTEGER,
    source_ai_item_id INTEGER,
    confidence REAL NOT NULL DEFAULT 0.5,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_context_events_person_time ON context_events(person_id, occurred_at);
CREATE INDEX IF NOT EXISTS idx_context_events_project_time ON context_events(project_id, occurred_at);
CREATE INDEX IF NOT EXISTS idx_context_events_company_time ON context_events(company_id, occurred_at);

CREATE TABLE IF NOT EXISTS context_facts (
    fact_id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_type TEXT NOT NULL,
    subject_id INTEGER NOT NULL,
    predicate TEXT NOT NULL,
    value_json TEXT NOT NULL,
    valid_from TEXT NOT NULL,
    valid_to TEXT,
    observed_at TEXT NOT NULL,
    is_current INTEGER NOT NULL DEFAULT 1,
    superseded_by_fact_id INTEGER,
    confidence REAL NOT NULL,
    source_type TEXT,
    source_chat_id INTEGER,
    source_message_id INTEGER,
    source_ai_item_id INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_context_facts_current ON context_facts(subject_type, subject_id, is_current);
CREATE INDEX IF NOT EXISTS idx_context_facts_predicate ON context_facts(predicate, is_current);

CREATE TABLE IF NOT EXISTS relationships (
    relationship_id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_type TEXT NOT NULL,
    from_id INTEGER NOT NULL,
    to_type TEXT NOT NULL,
    to_id INTEGER NOT NULL,
    relationship_type TEXT NOT NULL,
    valid_from TEXT NOT NULL,
    valid_to TEXT,
    is_current INTEGER NOT NULL DEFAULT 1,
    confidence REAL NOT NULL,
    source_chat_id INTEGER,
    source_message_id INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_relationships_from ON relationships(from_type, from_id, is_current);
CREATE INDEX IF NOT EXISTS idx_relationships_to ON relationships(to_type, to_id, is_current);

CREATE TABLE IF NOT EXISTS context_conflicts (
    conflict_id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_type TEXT NOT NULL,
    subject_id INTEGER NOT NULL,
    predicate TEXT NOT NULL,
    existing_fact_id INTEGER,
    new_observation_id INTEGER,
    conflict_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','resolved','ignored')),
    resolution_json TEXT,
    created_at TEXT NOT NULL,
    resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS context_conflict_observations (
    conflict_id INTEGER PRIMARY KEY,
    value_json TEXT NOT NULL,
    valid_from TEXT NOT NULL,
    confidence REAL NOT NULL,
    source_chat_id INTEGER,
    source_message_id INTEGER,
    source_ai_item_id INTEGER,
    created_at TEXT NOT NULL,
    FOREIGN KEY(conflict_id) REFERENCES context_conflicts(conflict_id)
);

CREATE TABLE IF NOT EXISTS context_conflict_decisions (
    decision_id INTEGER PRIMARY KEY AUTOINCREMENT,
    conflict_id INTEGER NOT NULL,
    decision TEXT NOT NULL CHECK(decision IN ('keep_existing','accept_observation','ignore')),
    resulting_fact_id INTEGER,
    note TEXT,
    decided_at TEXT NOT NULL,
    FOREIGN KEY(conflict_id) REFERENCES context_conflicts(conflict_id)
);
CREATE INDEX IF NOT EXISTS idx_context_conflict_decisions_conflict
ON context_conflict_decisions(conflict_id, decided_at);

CREATE TABLE IF NOT EXISTS context_summary_versions (
    version_id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,
    entity_id INTEGER NOT NULL,
    summary_type TEXT NOT NULL,
    summary TEXT NOT NULL,
    valid_from TEXT NOT NULL,
    valid_to TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_context_summary_versions ON context_summary_versions(entity_type, entity_id, valid_from);

CREATE TABLE IF NOT EXISTS global_state_snapshots (
    snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
    as_of TEXT NOT NULL UNIQUE,
    state_json TEXT NOT NULL,
    summary TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pinned_memory (
    memory_id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,
    entity_id INTEGER NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pinned_memory_entity ON pinned_memory(entity_type, entity_id);

CREATE TABLE IF NOT EXISTS person_context_state (
    person_id INTEGER PRIMARY KEY,
    relationship_type TEXT,
    communication_language TEXT,
    communication_style TEXT,
    typical_response_hours REAL,
    last_contact_at TEXT,
    current_summary TEXT,
    long_term_summary TEXT,
    profile_summary TEXT,
    profile_summary_updated_at TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS temporal_resolutions (
    resolution_id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    raw_expression TEXT NOT NULL,
    resolved_at TEXT,
    resolution_type TEXT NOT NULL,
    dependency_type TEXT,
    resolution_confidence REAL NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(chat_id, message_id, raw_expression)
);

CREATE TABLE IF NOT EXISTS task_deep_dive_sessions (
    session_id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'closed')),
    summary_json TEXT NOT NULL DEFAULT '{}',
    started_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_task_deep_dive_sessions_task
ON task_deep_dive_sessions(task_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS task_deep_dive_evidence (
    session_id INTEGER NOT NULL,
    evidence_type TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    relevance_score REAL NOT NULL,
    discovered_at TEXT NOT NULL,
    PRIMARY KEY(session_id, evidence_type, evidence_id)
);

CREATE TABLE IF NOT EXISTS task_notes (
    note_id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_task_notes_task ON task_notes(task_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS task_deep_dive_pins (
    task_id INTEGER NOT NULL,
    evidence_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(task_id, evidence_id)
);

CREATE TABLE IF NOT EXISTS conversation_segments (
    segment_id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    project_id INTEGER NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    anchor_count INTEGER NOT NULL DEFAULT 1,
    confidence REAL NOT NULL,
    source TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(chat_id, project_id, started_at, source)
);
CREATE INDEX IF NOT EXISTS idx_conversation_segments_chat_time
ON conversation_segments(chat_id, started_at, ended_at);
CREATE INDEX IF NOT EXISTS idx_conversation_segments_project_time
ON conversation_segments(project_id, started_at, ended_at);

CREATE TABLE IF NOT EXISTS conversation_contact_segments (
    segment_id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id INTEGER NOT NULL,
    source_type TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    chat_id INTEGER,
    primary_project_id INTEGER,
    primary_company_id INTEGER,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    topic_json TEXT NOT NULL DEFAULT '[]',
    summary TEXT NOT NULL DEFAULT '',
    importance REAL NOT NULL DEFAULT 0.5,
    confidence REAL NOT NULL,
    source TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(person_id, source_type, conversation_id, started_at, source)
);
CREATE INDEX IF NOT EXISTS idx_contact_segments_person_time
ON conversation_contact_segments(person_id, started_at, ended_at);
CREATE INDEX IF NOT EXISTS idx_contact_segments_conversation_time
ON conversation_contact_segments(source_type, conversation_id, started_at, ended_at);

CREATE TABLE IF NOT EXISTS current_conversation_context (
    person_id INTEGER NOT NULL,
    source_type TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    chat_id INTEGER,
    primary_project_id INTEGER,
    primary_company_id INTEGER,
    current_state TEXT NOT NULL DEFAULT '',
    topic_json TEXT NOT NULL DEFAULT '[]',
    open_loops_json TEXT NOT NULL DEFAULT '[]',
    recent_summary TEXT NOT NULL DEFAULT '',
    last_meaningful_at TEXT,
    evidence_through_at TEXT,
    context_version INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(person_id, source_type, conversation_id)
);
CREATE INDEX IF NOT EXISTS idx_current_conversation_context_person
ON current_conversation_context(person_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS person_project_context (
    person_id INTEGER NOT NULL,
    project_id INTEGER NOT NULL,
    role TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    first_activity_at TEXT,
    last_activity_at TEXT,
    current_summary TEXT NOT NULL DEFAULT '',
    long_term_summary TEXT NOT NULL DEFAULT '',
    confidence REAL NOT NULL DEFAULT 0.5,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(person_id, project_id)
);
CREATE INDEX IF NOT EXISTS idx_person_project_context_project
ON person_project_context(project_id, status, last_activity_at DESC);

CREATE TABLE IF NOT EXISTS conversation_open_loops (
    loop_id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id INTEGER NOT NULL,
    project_id INTEGER,
    source_type TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    loop_type TEXT NOT NULL,
    title TEXT NOT NULL,
    owner TEXT NOT NULL DEFAULT 'unknown',
    status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','waiting','resolved')),
    task_id INTEGER,
    source_chat_id INTEGER,
    source_message_id INTEGER,
    resolved_by_chat_id INTEGER,
    resolved_by_message_id INTEGER,
    confidence REAL NOT NULL DEFAULT 0.5,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(person_id, source_type, conversation_id, loop_type, title, source_chat_id, source_message_id)
);
CREATE INDEX IF NOT EXISTS idx_conversation_open_loops_person_status
ON conversation_open_loops(person_id, status, updated_at DESC);

CREATE TABLE IF NOT EXISTS conversation_context_links (
    link_id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id INTEGER NOT NULL,
    link_type TEXT NOT NULL,
    from_chat_id INTEGER NOT NULL,
    from_message_id INTEGER NOT NULL,
    to_chat_id INTEGER NOT NULL,
    to_message_id INTEGER NOT NULL,
    confidence REAL NOT NULL,
    source TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(link_type, from_chat_id, from_message_id, to_chat_id, to_message_id)
);
CREATE INDEX IF NOT EXISTS idx_conversation_context_links_person
ON conversation_context_links(person_id, created_at DESC);
"""

# Migration 1 predates the ledger.  These tables were accidentally copied into
# its evolving bootstrap text even though later migrations own them.  Keep the
# historical DDL text available for legacy-adoption context, but never execute
# a later migration's table or index from migration 1.
_POST_BOOTSTRAP_TABLES = frozenset(
    {
        "source_evidence",
        "source_evidence_versions",
        "message_classifications",
        "conversation_analysis_state",
        "context_conflict_observations",
        "context_conflict_decisions",
        "conversation_segments",
        "conversation_contact_segments",
        "current_conversation_context",
        "person_project_context",
        "conversation_open_loops",
        "conversation_context_links",
    }
)


@dataclass(frozen=True)
class Migration:
    """One ordered, idempotent schema evolution."""

    version: int
    name: str
    apply: Callable[[sqlite3.Connection], None]


def _bootstrap_schema(conn: sqlite3.Connection) -> None:
    """Create only migration 1's stable table set for fresh databases."""
    statements = [
        statement
        for statement in SCHEMA.split(";")
        if not any(f" {table}" in statement for table in _POST_BOOTSTRAP_TABLES)
    ]
    conn.executescript(";".join(statements))


def _apply_compatibility_columns(conn: sqlite3.Connection) -> None:
    apply_compatibility_columns(conn)


def _create_intelligence_coverage_tables(conn: sqlite3.Connection) -> None:
    """Add resumable classification state without modifying raw evidence."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS message_classifications (
            chat_id INTEGER NOT NULL,
            message_id INTEGER NOT NULL,
            conversation_type TEXT NOT NULL,
            content_type TEXT NOT NULL,
            actionability TEXT NOT NULL,
            importance TEXT NOT NULL,
            content_scope TEXT NOT NULL,
            information_scope TEXT NOT NULL DEFAULT 'unknown',
            temporal_relevance TEXT NOT NULL,
            potential_state_change INTEGER NOT NULL DEFAULT 0,
            is_forwarded INTEGER NOT NULL DEFAULT 0,
            topic_json TEXT NOT NULL DEFAULT '[]',
            classifier_type TEXT NOT NULL,
            provider TEXT,
            model TEXT,
            confidence REAL NOT NULL,
            classification_version INTEGER NOT NULL,
            context_version INTEGER NOT NULL DEFAULT 1,
            context_stale INTEGER NOT NULL DEFAULT 0,
            classified_at TEXT NOT NULL,
            PRIMARY KEY (chat_id, message_id)
        );
        CREATE INDEX IF NOT EXISTS idx_message_classifications_retrieval
        ON message_classifications(importance, content_type, actionability, temporal_relevance);
        CREATE TABLE IF NOT EXISTS conversation_analysis_state (
            chat_id INTEGER PRIMARY KEY,
            covered_until_message_id INTEGER,
            covered_until_date TEXT,
            message_count_analyzed INTEGER NOT NULL DEFAULT 0,
            classification_complete INTEGER NOT NULL DEFAULT 0,
            semantic_analysis_complete INTEGER NOT NULL DEFAULT 0,
            context_version INTEGER NOT NULL DEFAULT 1,
            last_analyzed_at TEXT,
            updated_at TEXT NOT NULL
        );
        """
    )


def _create_context_conflict_review_tables(conn: sqlite3.Connection) -> None:
    """Store the proposed observation and every manual temporal-fact decision."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS context_conflict_observations (
            conflict_id INTEGER PRIMARY KEY,
            value_json TEXT NOT NULL,
            valid_from TEXT NOT NULL,
            confidence REAL NOT NULL,
            source_chat_id INTEGER,
            source_message_id INTEGER,
            source_ai_item_id INTEGER,
            created_at TEXT NOT NULL,
            FOREIGN KEY(conflict_id) REFERENCES context_conflicts(conflict_id)
        );
        CREATE TABLE IF NOT EXISTS context_conflict_decisions (
            decision_id INTEGER PRIMARY KEY AUTOINCREMENT,
            conflict_id INTEGER NOT NULL,
            decision TEXT NOT NULL CHECK(decision IN ('keep_existing','accept_observation','ignore')),
            resulting_fact_id INTEGER,
            note TEXT,
            decided_at TEXT NOT NULL,
            FOREIGN KEY(conflict_id) REFERENCES context_conflicts(conflict_id)
        );
        CREATE INDEX IF NOT EXISTS idx_context_conflict_decisions_conflict
        ON context_conflict_decisions(conflict_id, decided_at);
        """
    )


def _add_intelligence_versions(conn: sqlite3.Connection) -> None:
    """Additive provenance for selective reclassification and re-analysis."""
    apply_intelligence_version_columns(conn)


def _upgrade_chat_ai_policies(conn: sqlite3.Connection) -> None:
    """Replace inert lane-only policy labels with enforceable analysis modes."""
    conn.executescript(
        """
        CREATE TABLE chat_ai_policy_next (
            chat_id INTEGER PRIMARY KEY,
            mode TEXT NOT NULL CHECK(mode IN ('auto','include','exclude','classify_only','news_only')),
            reason TEXT,
            updated_at TEXT NOT NULL
        );
        INSERT INTO chat_ai_policy_next(chat_id,mode,reason,updated_at)
        SELECT chat_id,
               CASE WHEN mode IN ('daily_only','history_only') THEN 'auto' ELSE mode END,
               reason,updated_at
        FROM chat_ai_policy;
        DROP TABLE chat_ai_policy;
        ALTER TABLE chat_ai_policy_next RENAME TO chat_ai_policy;
        """
    )


def _create_conversation_segments(conn: sqlite3.Connection) -> None:
    """Add derived temporal project periods without changing raw evidence."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS conversation_segments (
            segment_id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            project_id INTEGER NOT NULL,
            started_at TEXT NOT NULL,
            ended_at TEXT,
            anchor_count INTEGER NOT NULL DEFAULT 1,
            confidence REAL NOT NULL,
            source TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(chat_id, project_id, started_at, source)
        );
        CREATE INDEX IF NOT EXISTS idx_conversation_segments_chat_time
        ON conversation_segments(chat_id, started_at, ended_at);
        CREATE INDEX IF NOT EXISTS idx_conversation_segments_project_time
        ON conversation_segments(project_id, started_at, ended_at);
        """
    )


def _create_conversation_intelligence_tables(conn: sqlite3.Connection) -> None:
    """Add materialized person/conversation state without modifying evidence."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS conversation_contact_segments (
            segment_id INTEGER PRIMARY KEY AUTOINCREMENT,
            person_id INTEGER NOT NULL,
            source_type TEXT NOT NULL,
            conversation_id TEXT NOT NULL,
            chat_id INTEGER,
            primary_project_id INTEGER,
            primary_company_id INTEGER,
            started_at TEXT NOT NULL,
            ended_at TEXT,
            topic_json TEXT NOT NULL DEFAULT '[]',
            summary TEXT NOT NULL DEFAULT '',
            importance REAL NOT NULL DEFAULT 0.5,
            confidence REAL NOT NULL,
            source TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(person_id, source_type, conversation_id, started_at, source)
        );
        CREATE INDEX IF NOT EXISTS idx_contact_segments_person_time
        ON conversation_contact_segments(person_id, started_at, ended_at);
        CREATE INDEX IF NOT EXISTS idx_contact_segments_conversation_time
        ON conversation_contact_segments(source_type, conversation_id, started_at, ended_at);
        CREATE TABLE IF NOT EXISTS current_conversation_context (
            person_id INTEGER NOT NULL,
            source_type TEXT NOT NULL,
            conversation_id TEXT NOT NULL,
            chat_id INTEGER,
            primary_project_id INTEGER,
            primary_company_id INTEGER,
            current_state TEXT NOT NULL DEFAULT '',
            topic_json TEXT NOT NULL DEFAULT '[]',
            open_loops_json TEXT NOT NULL DEFAULT '[]',
            recent_summary TEXT NOT NULL DEFAULT '',
            last_meaningful_at TEXT,
            evidence_through_at TEXT,
            context_version INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(person_id, source_type, conversation_id)
        );
        CREATE INDEX IF NOT EXISTS idx_current_conversation_context_person
        ON current_conversation_context(person_id, updated_at DESC);
        CREATE TABLE IF NOT EXISTS person_project_context (
            person_id INTEGER NOT NULL,
            project_id INTEGER NOT NULL,
            role TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            first_activity_at TEXT,
            last_activity_at TEXT,
            current_summary TEXT NOT NULL DEFAULT '',
            long_term_summary TEXT NOT NULL DEFAULT '',
            confidence REAL NOT NULL DEFAULT 0.5,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(person_id, project_id)
        );
        CREATE INDEX IF NOT EXISTS idx_person_project_context_project
        ON person_project_context(project_id, status, last_activity_at DESC);
        CREATE TABLE IF NOT EXISTS conversation_open_loops (
            loop_id INTEGER PRIMARY KEY AUTOINCREMENT,
            person_id INTEGER NOT NULL,
            project_id INTEGER,
            source_type TEXT NOT NULL,
            conversation_id TEXT NOT NULL,
            loop_type TEXT NOT NULL,
            title TEXT NOT NULL,
            owner TEXT NOT NULL DEFAULT 'unknown',
            status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','waiting','resolved')),
            task_id INTEGER,
            source_chat_id INTEGER,
            source_message_id INTEGER,
            resolved_by_chat_id INTEGER,
            resolved_by_message_id INTEGER,
            confidence REAL NOT NULL DEFAULT 0.5,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(person_id, source_type, conversation_id, loop_type, title, source_chat_id, source_message_id)
        );
        CREATE INDEX IF NOT EXISTS idx_conversation_open_loops_person_status
        ON conversation_open_loops(person_id, status, updated_at DESC);
        CREATE TABLE IF NOT EXISTS conversation_context_links (
            link_id INTEGER PRIMARY KEY AUTOINCREMENT,
            person_id INTEGER NOT NULL,
            link_type TEXT NOT NULL,
            from_chat_id INTEGER NOT NULL,
            from_message_id INTEGER NOT NULL,
            to_chat_id INTEGER NOT NULL,
            to_message_id INTEGER NOT NULL,
            confidence REAL NOT NULL,
            source TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(link_type, from_chat_id, from_message_id, to_chat_id, to_message_id)
        );
        CREATE INDEX IF NOT EXISTS idx_conversation_context_links_person
        ON conversation_context_links(person_id, created_at DESC);
        """
    )


def _create_ai_routing_usage_tables(conn: sqlite3.Connection) -> None:
    """Persist only aggregate routing telemetry, never prompts or credentials."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS ai_model_usage (
            usage_date TEXT NOT NULL,
            model_key TEXT NOT NULL,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            attempt_count INTEGER NOT NULL DEFAULT 0,
            success_count INTEGER NOT NULL DEFAULT 0,
            estimated_input_tokens INTEGER NOT NULL DEFAULT 0,
            actual_input_tokens INTEGER NOT NULL DEFAULT 0,
            output_tokens INTEGER NOT NULL DEFAULT 0,
            last_request_at TEXT,
            last_success_at TEXT,
            last_error_at TEXT,
            last_error TEXT,
            cooldown_until TEXT,
            PRIMARY KEY (usage_date, model_key)
        );
        CREATE TABLE IF NOT EXISTS ai_route_events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            workload TEXT NOT NULL,
            priority TEXT NOT NULL,
            model_key TEXT NOT NULL,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            estimated_input_tokens INTEGER NOT NULL,
            decision_reason TEXT NOT NULL,
            outcome TEXT NOT NULL,
            error TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_ai_route_events_created
        ON ai_route_events(created_at DESC);
        """
    )


def _add_column_if_missing(
    conn: sqlite3.Connection, table: str, definition: str
) -> None:
    column = definition.split()[0]
    columns = {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")


def _upgrade_extraction_lifecycle(conn: sqlite3.Connection) -> None:
    """Add exact AI-work membership and independently durable downstream states."""
    job_columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(ai_jobs)")}
    if "selection_fingerprint" not in job_columns:
        conn.execute("DROP INDEX IF EXISTS idx_ai_jobs_queue")
        conn.execute("ALTER TABLE ai_jobs RENAME TO ai_jobs_legacy_range")
        conn.executescript(
            """
            CREATE TABLE ai_jobs (
                job_id INTEGER PRIMARY KEY AUTOINCREMENT,
                lane TEXT NOT NULL CHECK (lane IN ('daily', 'history')),
                chat_id INTEGER NOT NULL,
                first_message_id INTEGER NOT NULL,
                last_message_id INTEGER NOT NULL,
                date_from TEXT,
                date_to TEXT,
                message_count INTEGER NOT NULL,
                analysis_version INTEGER NOT NULL,
                selection_fingerprint TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending','running','done','failed','superseded')),
                provider TEXT,
                model TEXT,
                fallback_used INTEGER NOT NULL DEFAULT 0,
                attempt_count INTEGER NOT NULL DEFAULT 0,
                last_error TEXT,
                created_at TEXT NOT NULL,
                started_at TEXT,
                completed_at TEXT,
                UNIQUE(lane, chat_id, analysis_version, selection_fingerprint)
            );
            CREATE INDEX idx_ai_jobs_queue ON ai_jobs(lane, status, job_id);
            """
        )
        conn.execute(
            """
            INSERT INTO ai_jobs(
                job_id,lane,chat_id,first_message_id,last_message_id,date_from,date_to,
                message_count,analysis_version,selection_fingerprint,status,provider,
                model,fallback_used,attempt_count,last_error,created_at,started_at,completed_at
            )
            SELECT job_id,lane,chat_id,first_message_id,last_message_id,date_from,date_to,
                   message_count,1,'legacy-range:' || job_id,
                   CASE WHEN status IN ('pending','running') THEN 'superseded' ELSE status END,
                   provider,model,fallback_used,attempt_count,
                   CASE WHEN status IN ('pending','running')
                        THEN 'superseded: legacy range has no exact membership'
                        ELSE last_error END,
                   created_at,started_at,completed_at
            FROM ai_jobs_legacy_range
            """
        )
        conn.execute("DROP TABLE ai_jobs_legacy_range")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS ai_job_messages (
            job_id INTEGER NOT NULL,
            ordinal INTEGER NOT NULL,
            chat_id INTEGER NOT NULL,
            message_id INTEGER NOT NULL,
            PRIMARY KEY(job_id, ordinal),
            UNIQUE(job_id, chat_id, message_id)
        );
        CREATE INDEX IF NOT EXISTS idx_ai_job_messages_message
        ON ai_job_messages(chat_id, message_id, job_id);
        CREATE TABLE IF NOT EXISTS ai_item_rejections (
            rejection_id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id INTEGER NOT NULL,
            item_index INTEGER NOT NULL,
            reason TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(batch_id, item_index)
        );
        CREATE TABLE IF NOT EXISTS context_invalidations (
            scope_type TEXT NOT NULL CHECK(scope_type IN ('conversation','person','project','company','task','global')),
            scope_id INTEGER,
            requested_revision INTEGER NOT NULL DEFAULT 0,
            completed_revision INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','running','failed','clean')),
            attempt_count INTEGER NOT NULL DEFAULT 0,
            last_error TEXT,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(scope_type, scope_id)
        );
        CREATE TABLE IF NOT EXISTS ai_batch_invalidations (
            batch_id INTEGER NOT NULL,
            scope_type TEXT NOT NULL,
            scope_id INTEGER,
            requested_revision INTEGER NOT NULL,
            integrated_at TEXT,
            PRIMARY KEY(batch_id, scope_type, scope_id)
        );
        """
    )
    _add_column_if_missing(conn, "ai_items", "project_name TEXT")
    _add_column_if_missing(conn, "ai_message_state", "canonicalized_at TEXT")
    for definition in (
        "analysis_version INTEGER NOT NULL DEFAULT 1",
        "projection_status TEXT NOT NULL DEFAULT 'pending'",
        "projection_attempt_count INTEGER NOT NULL DEFAULT 0",
        "projection_error TEXT",
        "projection_started_at TEXT",
        "projected_at TEXT",
        "context_integrated_at TEXT",
    ):
        _add_column_if_missing(conn, "ai_batches", definition)


def _create_semantic_claim_graph(conn: sqlite3.Connection) -> None:
    """Add immutable AI claims and the future temporal-graph persistence boundary."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS semantic_claims (
            claim_id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id INTEGER NOT NULL,
            claim_type TEXT NOT NULL CHECK(claim_type IN (
                'entity','event','commitment','temporal_fact','relationship',
                'topic','action_candidate'
            )),
            statement TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            extractor_version INTEGER NOT NULL,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            confidence REAL NOT NULL CHECK(confidence >= 0 AND confidence <= 1),
            authority_status TEXT NOT NULL DEFAULT 'observed' CHECK(authority_status IN (
                'observed','accepted','manual','rejected','superseded'
            )),
            dedupe_key TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_semantic_claims_batch
        ON semantic_claims(batch_id, claim_id);
        CREATE INDEX IF NOT EXISTS idx_semantic_claims_status
        ON semantic_claims(authority_status, claim_type, created_at);

        CREATE TABLE IF NOT EXISTS semantic_claim_evidence (
            claim_id INTEGER NOT NULL,
            ordinal INTEGER NOT NULL,
            source_chat_id INTEGER NOT NULL,
            source_message_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY(claim_id, ordinal),
            UNIQUE(claim_id, source_chat_id, source_message_id)
        );
        CREATE INDEX IF NOT EXISTS idx_semantic_claim_evidence_source
        ON semantic_claim_evidence(source_chat_id, source_message_id, claim_id);

        CREATE TABLE IF NOT EXISTS semantic_claim_entity_refs (
            claim_id INTEGER NOT NULL,
            ordinal INTEGER NOT NULL,
            role TEXT NOT NULL,
            entity_type TEXT NOT NULL CHECK(entity_type IN (
                'person','company','project','task','conversation','event',
                'commitment','topic'
            )),
            surface_name TEXT NOT NULL,
            canonical_entity_id INTEGER,
            resolution_status TEXT NOT NULL DEFAULT 'unresolved' CHECK(
                resolution_status IN ('unresolved','resolved','review','rejected')
            ),
            created_at TEXT NOT NULL,
            PRIMARY KEY(claim_id, ordinal)
        );
        CREATE INDEX IF NOT EXISTS idx_semantic_claim_entity_refs_resolution
        ON semantic_claim_entity_refs(entity_type, canonical_entity_id, resolution_status);

        CREATE TABLE IF NOT EXISTS graph_nodes (
            node_id INTEGER PRIMARY KEY AUTOINCREMENT,
            node_key TEXT NOT NULL UNIQUE,
            node_type TEXT NOT NULL CHECK(node_type IN (
                'person','company','project','task','conversation','event',
                'commitment','topic'
            )),
            canonical_entity_type TEXT,
            canonical_entity_id INTEGER,
            properties_json TEXT NOT NULL DEFAULT '{}',
            authority_status TEXT NOT NULL DEFAULT 'observed' CHECK(authority_status IN (
                'observed','accepted','manual','rejected','superseded'
            )),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_graph_nodes_canonical
        ON graph_nodes(canonical_entity_type, canonical_entity_id, authority_status);

        CREATE TABLE IF NOT EXISTS graph_edges (
            edge_id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_node_id INTEGER NOT NULL,
            to_node_id INTEGER NOT NULL,
            relationship_type TEXT NOT NULL,
            valid_from TEXT NOT NULL,
            valid_to TEXT,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            confidence REAL NOT NULL CHECK(confidence >= 0 AND confidence <= 1),
            authority_status TEXT NOT NULL DEFAULT 'observed' CHECK(authority_status IN (
                'observed','accepted','manual','rejected','superseded'
            )),
            properties_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_graph_edges_from
        ON graph_edges(from_node_id, authority_status, valid_from, valid_to);
        CREATE INDEX IF NOT EXISTS idx_graph_edges_to
        ON graph_edges(to_node_id, authority_status, valid_from, valid_to);

        CREATE TABLE IF NOT EXISTS graph_edge_claims (
            edge_id INTEGER NOT NULL,
            claim_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY(edge_id, claim_id)
        );
        CREATE INDEX IF NOT EXISTS idx_graph_edge_claims_claim
        ON graph_edge_claims(claim_id, edge_id);
        """
    )
    for table in ("tasks", "context_events", "context_facts", "relationships"):
        _add_column_if_missing(conn, table, "source_claim_id INTEGER")


def _add_graph_projection_lineage(conn: sqlite3.Connection) -> None:
    """Link compatibility observations to claims and record graph projection state."""
    _add_column_if_missing(conn, "ai_items", "source_claim_id INTEGER")
    _add_column_if_missing(
        conn,
        "semantic_claims",
        "projection_status TEXT NOT NULL DEFAULT 'pending' CHECK("
        "projection_status IN ('pending','projected','review','rejected'))",
    )
    _add_column_if_missing(conn, "semantic_claims", "projected_at TEXT")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_semantic_claims_projection "
        "ON semantic_claims(projection_status, claim_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ai_items_source_claim "
        "ON ai_items(source_claim_id)"
    )


def _add_person_profile_summary(conn: sqlite3.Connection) -> None:
    """Add presentation-only profile summary fields to the existing context row."""
    _add_column_if_missing(conn, "person_context_state", "profile_summary TEXT")
    _add_column_if_missing(
        conn, "person_context_state", "profile_summary_updated_at TEXT"
    )


def _add_person_profile_enrichment(conn: sqlite3.Connection) -> None:
    """Add scoped, resumable profile-scan metadata without touching evidence."""
    _add_column_if_missing(
        conn, "person_context_state", "profile_summary_input_hash TEXT"
    )
    _add_column_if_missing(conn, "ai_jobs", "profile_person_id INTEGER")
    _add_column_if_missing(conn, "ai_jobs", "profile_extractor_version INTEGER")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ai_jobs_profile_scan "
        "ON ai_jobs(profile_person_id,profile_extractor_version,status,job_id)"
    )


def _add_profile_ai_lane(conn: sqlite3.Connection) -> None:
    """Add the isolated Person Profile lane while preserving durable jobs."""
    conn.execute("DROP INDEX IF EXISTS idx_ai_jobs_queue")
    conn.execute("DROP INDEX IF EXISTS idx_ai_jobs_profile_scan")
    conn.execute("ALTER TABLE ai_jobs RENAME TO ai_jobs_pre_profile_lane")
    conn.executescript(
        """
        CREATE TABLE ai_jobs (
            job_id INTEGER PRIMARY KEY AUTOINCREMENT,
            lane TEXT NOT NULL CHECK (lane IN ('daily', 'history', 'profile')),
            chat_id INTEGER NOT NULL,
            first_message_id INTEGER NOT NULL,
            last_message_id INTEGER NOT NULL,
            date_from TEXT,
            date_to TEXT,
            message_count INTEGER NOT NULL,
            analysis_version INTEGER NOT NULL,
            selection_fingerprint TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending','running','done','failed','superseded')),
            provider TEXT,
            model TEXT,
            fallback_used INTEGER NOT NULL DEFAULT 0,
            attempt_count INTEGER NOT NULL DEFAULT 0,
            last_error TEXT,
            created_at TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT,
            profile_person_id INTEGER,
            profile_extractor_version INTEGER,
            UNIQUE(lane, chat_id, analysis_version, selection_fingerprint)
        );
        CREATE INDEX idx_ai_jobs_queue ON ai_jobs(lane, status, job_id);
        CREATE INDEX idx_ai_jobs_profile_scan
        ON ai_jobs(profile_person_id,profile_extractor_version,status,job_id);
        """
    )
    conn.execute(
        """
        INSERT INTO ai_jobs(
            job_id,lane,chat_id,first_message_id,last_message_id,date_from,date_to,
            message_count,analysis_version,selection_fingerprint,status,provider,
            model,fallback_used,attempt_count,last_error,created_at,started_at,completed_at,
            profile_person_id,profile_extractor_version
        )
        SELECT job_id,lane,chat_id,first_message_id,last_message_id,date_from,date_to,
               message_count,analysis_version,selection_fingerprint,status,provider,
               model,fallback_used,attempt_count,last_error,created_at,started_at,completed_at,
               profile_person_id,profile_extractor_version
        FROM ai_jobs_pre_profile_lane
        """
    )
    conn.execute("DROP TABLE ai_jobs_pre_profile_lane")


def _add_profile_claim_metadata(conn: sqlite3.Connection) -> None:
    """Add profile-only assertion metadata to immutable semantic claims."""
    _add_column_if_missing(conn, "semantic_claims", "profile_person_id INTEGER")
    _add_column_if_missing(conn, "semantic_claims", "profile_assertion_kind TEXT")
    _add_column_if_missing(conn, "semantic_claims", "profile_valid_from TEXT")
    _add_column_if_missing(conn, "semantic_claims", "profile_valid_to TEXT")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_semantic_claims_profile "
        "ON semantic_claims(profile_person_id,profile_assertion_kind,profile_valid_from,claim_id)"
    )


MIGRATIONS: tuple[Migration, ...] = (
    Migration(1, "bootstrap_schema", _bootstrap_schema),
    Migration(2, "compatibility_columns", _apply_compatibility_columns),
    Migration(3, "fts_indexes", create_fts),
    Migration(4, "source_neutral_evidence", create_source_evidence_tables),
    Migration(
        5,
        "intelligence_coverage",
        lambda conn: _create_intelligence_coverage_tables(conn),
    ),
    Migration(
        6,
        "context_conflict_review",
        lambda conn: _create_context_conflict_review_tables(conn),
    ),
    Migration(7, "intelligence_versions", _add_intelligence_versions),
    Migration(8, "enforceable_chat_ai_policies", _upgrade_chat_ai_policies),
    Migration(9, "conversation_segments", _create_conversation_segments),
    Migration(
        10, "conversation_intelligence", _create_conversation_intelligence_tables
    ),
    Migration(11, "ai_routing_usage", _create_ai_routing_usage_tables),
    Migration(12, "fts_lifecycle_rebuild", rebuild_fts),
    Migration(13, "extraction_lifecycle", _upgrade_extraction_lifecycle),
    Migration(14, "semantic_claim_graph", _create_semantic_claim_graph),
    Migration(15, "graph_projection_lineage", _add_graph_projection_lineage),
    Migration(16, "person_profile_summary", _add_person_profile_summary),
    Migration(17, "person_profile_enrichment", _add_person_profile_enrichment),
    Migration(18, "profile_ai_lane", _add_profile_ai_lane),
    Migration(19, "profile_claim_metadata", _add_profile_claim_metadata),
)
SCHEMA_VERSION = MIGRATIONS[-1].version


def connect(settings: Settings) -> sqlite3.Connection:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA temp_store=MEMORY")
    _apply_migrations(conn)
    _cleanup_legacy_empty_ai_marks(conn)
    _requeue_interrupted_ai_jobs(conn)
    conn.commit()
    return conn


def _apply_migrations(conn: sqlite3.Connection) -> None:
    """Apply each missing migration and record it only after it succeeds.

    The bootstrap migration is intentionally idempotent so installations that
    existed before the ledger can be adopted safely on their next open.
    """
    conn.execute(
        """CREATE TABLE IF NOT EXISTS schema_migrations (
               version INTEGER PRIMARY KEY,
               name TEXT NOT NULL,
               applied_at TEXT NOT NULL
           )"""
    )
    applied = {
        int(row[0])
        for row in conn.execute("SELECT version FROM schema_migrations").fetchall()
    }
    from .utils import utc_now

    for migration in MIGRATIONS:
        if migration.version in applied:
            continue
        try:
            with conn:
                migration.apply(conn)
                conn.execute(
                    "INSERT INTO schema_migrations(version,name,applied_at) VALUES (?,?,?)",
                    (migration.version, migration.name, utc_now()),
                )
        except sqlite3.Error as error:
            raise RuntimeError(
                f"Database migration {migration.version} ({migration.name}) failed. "
                "Restore the most recent SQLite API backup before retrying."
            ) from error


def schema_version(conn: sqlite3.Connection) -> int:
    """Return the latest applied migration, or zero for an untracked legacy DB."""
    try:
        row = conn.execute(
            "SELECT COALESCE(MAX(version), 0) FROM schema_migrations"
        ).fetchone()
    except sqlite3.OperationalError:
        return 0
    return int(row[0] or 0)


def migration_history(conn: sqlite3.Connection) -> list[tuple[int, str, str]]:
    """Return the ordered ledger for diagnostics and upgrade tooling."""
    try:
        return [
            (int(row[0]), str(row[1]), str(row[2]))
            for row in conn.execute(
                "SELECT version,name,applied_at FROM schema_migrations ORDER BY version"
            )
        ]
    except sqlite3.OperationalError:
        return []


def set_app_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    from .utils import utc_now

    conn.execute(
        """
        INSERT INTO app_meta(key, value, updated_at) VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
        """,
        (key, value, utc_now()),
    )


def update_known_chat_metadata(conn: sqlite3.Connection, dialogs: list) -> None:
    """Refresh AI-relevant metadata without treating new dialogs as archived."""
    rows = [
        (
            info.title,
            info.username,
            info.chat_type,
            int(info.is_bot),
            info.chat_id,
        )
        for info in dialogs
    ]
    if not rows:
        return

    with conn:
        conn.executemany(
            """
            UPDATE chats
            SET title = ?, username = ?, chat_type = ?, is_bot = ?
            WHERE chat_id = ?
            """,
            rows,
        )


def _cleanup_legacy_empty_ai_marks(conn: sqlite3.Connection) -> int:
    """Remove old 'analyzed' markers for messages never sent to Groq.

    Earlier versions inserted ai_message_state rows for empty/media-only
    messages with batch_id=NULL. That made the status screen claim more
    messages were AI-analyzed than were actually submitted.
    """
    cursor = conn.execute(
        """
        DELETE FROM ai_message_state
        WHERE batch_id IS NULL
          AND EXISTS (
              SELECT 1
              FROM messages AS m
              WHERE m.chat_id = ai_message_state.chat_id
                AND m.message_id = ai_message_state.message_id
                AND TRIM(COALESCE(m.text, '')) = ''
          )
        """
    )
    return max(0, cursor.rowcount)


def _requeue_interrupted_ai_jobs(conn: sqlite3.Connection) -> int:
    """A process cannot know whether a prior running job was interrupted.

    No messages are marked until the same transaction saves the successful
    response, so returning these jobs to pending is safe and idempotent.
    """
    cursor = conn.execute(
        "UPDATE ai_jobs SET status = 'pending' WHERE status = 'running'"
    )
    return max(0, cursor.rowcount)


def load_last_message_ids(conn: sqlite3.Connection) -> dict[int, int]:
    return {
        int(chat_id): int(max_id or 0)
        for chat_id, max_id in conn.execute(
            """
            SELECT chat_id, MAX(message_id)
            FROM messages
            GROUP BY chat_id
            """
        )
    }


def load_sync_states(conn: sqlite3.Connection) -> dict[int, dict]:
    states: dict[int, dict] = {}
    rows = conn.execute(
        """
        SELECT
            chat_id,
            bootstrap_complete,
            bootstrap_mode,
            group_total_at_bootstrap,
            last_sync_at
        FROM sync_state
        """
    )

    for row in rows:
        states[int(row[0])] = {
            "bootstrap_complete": bool(row[1]),
            "bootstrap_mode": row[2],
            "group_total": row[3],
            "last_sync_at": row[4],
        }
    return states


def archive_stats(conn: sqlite3.Connection) -> tuple[int, int, int, str | None]:
    chats = conn.execute("SELECT COUNT(*) FROM chats").fetchone()[0]
    messages = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    bootstrapped = conn.execute(
        "SELECT COUNT(*) FROM sync_state WHERE bootstrap_complete = 1"
    ).fetchone()[0]
    last_message = conn.execute("SELECT MAX(date) FROM messages").fetchone()[0]
    return chats, messages, bootstrapped, last_message
