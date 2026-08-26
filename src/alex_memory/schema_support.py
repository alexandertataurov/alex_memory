"""Declarative SQLite support used by the ordered database migration ledger."""

from __future__ import annotations

import sqlite3
from types import MappingProxyType


FTS_TABLES = (
    "messages_fts",
    "tasks_fts",
    "memory_fts",
    "summaries_fts",
    "entities_fts",
    "entity_memory_fts",
)

FTS_TRIGGERS = (
    "messages_fts_insert",
    "messages_fts_update",
    "messages_fts_delete",
    "tasks_fts_insert",
    "tasks_fts_update",
    "tasks_fts_delete",
    "memory_fts_insert",
    "memory_fts_update",
    "memory_fts_delete",
    "summaries_fts_insert",
    "summaries_fts_update",
    "summaries_fts_delete",
    "people_fts_insert",
    "people_fts_update",
    "people_fts_delete",
    "companies_fts_insert",
    "companies_fts_update",
    "companies_fts_delete",
    "projects_fts_insert",
    "projects_fts_update",
    "projects_fts_delete",
    "entity_memory_fts_insert",
    "entity_memory_fts_update",
    "entity_memory_fts_delete",
)


_COMPATIBILITY_COLUMN_DEFINITIONS = {
    "chats": {"is_bot": "INTEGER NOT NULL DEFAULT 0"},
    "ai_batches": {
        "response_json": "TEXT",
        "returned_item_count": "INTEGER NOT NULL DEFAULT 0",
        "saved_item_count": "INTEGER NOT NULL DEFAULT 0",
        "rejected_item_count": "INTEGER NOT NULL DEFAULT 0",
        "lane": "TEXT NOT NULL DEFAULT 'daily'",
        "provider": "TEXT",
        "fallback_used": "INTEGER NOT NULL DEFAULT 0",
        "job_id": "INTEGER",
        "usage_json": "TEXT",
    },
    "ai_items": {
        "person_id": "INTEGER",
        "company_id": "INTEGER",
        "project_id": "INTEGER",
    },
    "messages": {
        "edited_at": "TEXT",
        "is_deleted": "INTEGER NOT NULL DEFAULT 0",
        "deleted_at": "TEXT",
        "is_forwarded": "INTEGER NOT NULL DEFAULT 0",
        "forward_source": "TEXT",
    },
    "message_classifications": {"information_scope": "TEXT NOT NULL DEFAULT 'unknown'"},
    "ai_message_state": {
        "analysis_version": "INTEGER NOT NULL DEFAULT 1",
        "context_version_used": "INTEGER NOT NULL DEFAULT 1",
        "analysis_stale": "INTEGER NOT NULL DEFAULT 0",
    },
    "projects": {
        "status": "TEXT NOT NULL DEFAULT 'active'",
        "health_score": "INTEGER",
        "last_activity_at": "TEXT",
    },
}

COMPATIBILITY_COLUMNS = MappingProxyType(
    {
        table: MappingProxyType(columns)
        for table, columns in _COMPATIBILITY_COLUMN_DEFINITIONS.items()
    }
)

# Migrations 2 and 7 are historical adoption steps. Their snapshots are
# immutable at runtime so a helper caller cannot silently alter a recorded
# migration while a database is opening.
_COMPATIBILITY_COLUMN_SNAPSHOT = tuple(
    (table, tuple(columns.items())) for table, columns in COMPATIBILITY_COLUMNS.items()
)
_MIGRATION_2_COMPATIBILITY_SNAPSHOT = tuple(
    (table, columns)
    for table, columns in _COMPATIBILITY_COLUMN_SNAPSHOT
    if table != "message_classifications"
)
_MIGRATION_7_COMPATIBILITY_SNAPSHOT = tuple(
    (table, columns)
    for table, columns in _COMPATIBILITY_COLUMN_SNAPSHOT
    if table == "message_classifications"
)


def apply_compatibility_columns(conn: sqlite3.Connection) -> None:
    """Apply the one additive pre-ledger column map through migration 2."""
    _apply_column_snapshot(conn, _MIGRATION_2_COMPATIBILITY_SNAPSHOT)


def apply_intelligence_version_columns(conn: sqlite3.Connection) -> None:
    """Apply migration 7's fixed compatibility addition after migration 5."""
    _apply_column_snapshot(conn, _MIGRATION_7_COMPATIBILITY_SNAPSHOT)


def _apply_column_snapshot(
    conn: sqlite3.Connection,
    snapshot: tuple[tuple[str, tuple[tuple[str, str], ...]], ...],
) -> None:
    for table, columns in snapshot:
        existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        for column, definition in columns:
            if column not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def create_source_evidence_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
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
        """
    )


def fts5_available(conn: sqlite3.Connection) -> bool:
    """Return whether this SQLite connection exposes the optional FTS5 module."""
    return (
        conn.execute(
            "SELECT 1 FROM pragma_module_list WHERE name='fts5' LIMIT 1"
        ).fetchone()
        is not None
    )


def create_fts(conn: sqlite3.Connection) -> None:
    """Create the original optional FTS structures for migration 3 only.

    New lifecycle guarantees are applied by migration 12. This older migration
    deliberately remains creation-only so the ordered ledger's history is not
    rewritten for existing installations.
    """
    if not fts5_available(conn):
        return
    conn.executescript(
        """
            CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(text, chat_id UNINDEXED, message_id UNINDEXED);
            CREATE VIRTUAL TABLE IF NOT EXISTS tasks_fts USING fts5(title, details, task_id UNINDEXED);
            CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(title, details, item_id UNINDEXED);
            CREATE VIRTUAL TABLE IF NOT EXISTS summaries_fts USING fts5(summary, source_type UNINDEXED, source_id UNINDEXED);
            CREATE VIRTUAL TABLE IF NOT EXISTS entities_fts USING fts5(name, entity_type UNINDEXED, entity_id UNINDEXED);
            CREATE VIRTUAL TABLE IF NOT EXISTS entity_memory_fts USING fts5(summary, entity_type UNINDEXED, entity_id UNINDEXED);
            CREATE TRIGGER IF NOT EXISTS messages_fts_insert AFTER INSERT ON messages BEGIN
                INSERT INTO messages_fts(text, chat_id, message_id) VALUES (NEW.text, NEW.chat_id, NEW.message_id);
            END;
            CREATE TRIGGER IF NOT EXISTS tasks_fts_insert AFTER INSERT ON tasks BEGIN
                INSERT INTO tasks_fts(title, details, task_id) VALUES (NEW.title, COALESCE(NEW.details, ''), NEW.task_id);
            END;
            CREATE TRIGGER IF NOT EXISTS memory_fts_insert AFTER INSERT ON ai_items BEGIN
                INSERT INTO memory_fts(title, details, item_id) VALUES (NEW.title, NEW.details, NEW.item_id);
            END;
            CREATE TRIGGER IF NOT EXISTS summaries_fts_insert AFTER INSERT ON memory_chunks BEGIN
                INSERT INTO summaries_fts(summary, source_type, source_id) VALUES (NEW.summary, 'chunk', NEW.chunk_id);
            END;
            CREATE TRIGGER IF NOT EXISTS people_fts_insert AFTER INSERT ON people BEGIN
                INSERT INTO entities_fts(name, entity_type, entity_id) VALUES (NEW.canonical_name, 'person', NEW.person_id);
            END;
            CREATE TRIGGER IF NOT EXISTS companies_fts_insert AFTER INSERT ON companies BEGIN
                INSERT INTO entities_fts(name, entity_type, entity_id) VALUES (NEW.canonical_name, 'company', NEW.company_id);
            END;
            CREATE TRIGGER IF NOT EXISTS projects_fts_insert AFTER INSERT ON projects BEGIN
                INSERT INTO entities_fts(name, entity_type, entity_id) VALUES (NEW.canonical_name, 'project', NEW.project_id);
            END;
            CREATE TRIGGER IF NOT EXISTS entity_memory_fts_insert AFTER INSERT ON entity_memory BEGIN
                INSERT INTO entity_memory_fts(summary, entity_type, entity_id) VALUES (NEW.summary, NEW.entity_type, NEW.entity_id);
            END;
        """
    )


def rebuild_fts(conn: sqlite3.Connection) -> None:
    """Atomically rebuild all FTS-derived state from current authoritative rows."""
    if not fts5_available(conn):
        return
    drops = "\n".join(
        [
            *(f"DROP TRIGGER IF EXISTS {trigger};" for trigger in FTS_TRIGGERS),
            *(f"DROP TABLE IF EXISTS {table};" for table in FTS_TABLES),
        ]
    )
    # executescript commits any pending transaction before executing its input.
    # Start one in the script and leave it open: _apply_migrations records the
    # migration in the same transaction, or its context manager rolls back all
    # dropped/rebuilt derived objects when any statement or parity check fails.
    conn.executescript(
        f"""BEGIN IMMEDIATE;
        {drops}
        CREATE VIRTUAL TABLE messages_fts USING fts5(text, chat_id UNINDEXED, message_id UNINDEXED);
        CREATE VIRTUAL TABLE tasks_fts USING fts5(title, details, task_id UNINDEXED);
        CREATE VIRTUAL TABLE memory_fts USING fts5(title, details, item_id UNINDEXED);
        CREATE VIRTUAL TABLE summaries_fts USING fts5(summary, source_type UNINDEXED, source_id UNINDEXED);
        CREATE VIRTUAL TABLE entities_fts USING fts5(name, entity_type UNINDEXED, entity_id UNINDEXED);
        CREATE VIRTUAL TABLE entity_memory_fts USING fts5(summary, entity_type UNINDEXED, entity_id UNINDEXED, memory_key UNINDEXED);

        INSERT INTO messages_fts(text,chat_id,message_id)
        SELECT text,chat_id,message_id FROM messages
        WHERE is_deleted=0 AND trim(COALESCE(text,''))<>'';
        INSERT INTO tasks_fts(title,details,task_id)
        SELECT title,COALESCE(details,''),task_id FROM tasks
        WHERE trim(COALESCE(title,'') || COALESCE(details,''))<>'';
        INSERT INTO memory_fts(title,details,item_id)
        SELECT title,details,item_id FROM ai_items
        WHERE trim(COALESCE(title,'') || COALESCE(details,''))<>'';
        INSERT INTO summaries_fts(summary,source_type,source_id)
        SELECT summary,'chunk',chunk_id FROM memory_chunks
        WHERE trim(COALESCE(summary,''))<>'';
        INSERT INTO entities_fts(name,entity_type,entity_id)
        SELECT canonical_name,'person',person_id FROM people
        WHERE status<>'merged' AND trim(COALESCE(canonical_name,''))<>''
        UNION ALL
        SELECT canonical_name,'company',company_id FROM companies
        WHERE status<>'merged' AND trim(COALESCE(canonical_name,''))<>''
        UNION ALL
        SELECT canonical_name,'project',project_id FROM projects
        WHERE status<>'merged' AND trim(COALESCE(canonical_name,''))<>'';
        INSERT INTO entity_memory_fts(summary,entity_type,entity_id,memory_key)
        SELECT summary,entity_type,entity_id,memory_key FROM entity_memory
        WHERE trim(COALESCE(summary,''))<>'';

        CREATE TRIGGER messages_fts_insert AFTER INSERT ON messages BEGIN
            INSERT INTO messages_fts(text,chat_id,message_id)
            SELECT NEW.text,NEW.chat_id,NEW.message_id
            WHERE NEW.is_deleted=0 AND trim(COALESCE(NEW.text,''))<>'';
        END;
        CREATE TRIGGER messages_fts_update AFTER UPDATE ON messages BEGIN
            DELETE FROM messages_fts WHERE chat_id=OLD.chat_id AND message_id=OLD.message_id;
            INSERT INTO messages_fts(text,chat_id,message_id)
            SELECT NEW.text,NEW.chat_id,NEW.message_id
            WHERE NEW.is_deleted=0 AND trim(COALESCE(NEW.text,''))<>'';
        END;
        CREATE TRIGGER messages_fts_delete AFTER DELETE ON messages BEGIN
            DELETE FROM messages_fts WHERE chat_id=OLD.chat_id AND message_id=OLD.message_id;
        END;

        CREATE TRIGGER tasks_fts_insert AFTER INSERT ON tasks BEGIN
            INSERT INTO tasks_fts(title,details,task_id)
            SELECT NEW.title,COALESCE(NEW.details,''),NEW.task_id
            WHERE trim(COALESCE(NEW.title,'') || COALESCE(NEW.details,''))<>'';
        END;
        CREATE TRIGGER tasks_fts_update AFTER UPDATE ON tasks BEGIN
            DELETE FROM tasks_fts WHERE task_id=OLD.task_id;
            INSERT INTO tasks_fts(title,details,task_id)
            SELECT NEW.title,COALESCE(NEW.details,''),NEW.task_id
            WHERE trim(COALESCE(NEW.title,'') || COALESCE(NEW.details,''))<>'';
        END;
        CREATE TRIGGER tasks_fts_delete AFTER DELETE ON tasks BEGIN
            DELETE FROM tasks_fts WHERE task_id=OLD.task_id;
        END;

        CREATE TRIGGER memory_fts_insert AFTER INSERT ON ai_items BEGIN
            INSERT INTO memory_fts(title,details,item_id)
            SELECT NEW.title,NEW.details,NEW.item_id
            WHERE trim(COALESCE(NEW.title,'') || COALESCE(NEW.details,''))<>'';
        END;
        CREATE TRIGGER memory_fts_update AFTER UPDATE ON ai_items BEGIN
            DELETE FROM memory_fts WHERE item_id=OLD.item_id;
            INSERT INTO memory_fts(title,details,item_id)
            SELECT NEW.title,NEW.details,NEW.item_id
            WHERE trim(COALESCE(NEW.title,'') || COALESCE(NEW.details,''))<>'';
        END;
        CREATE TRIGGER memory_fts_delete AFTER DELETE ON ai_items BEGIN
            DELETE FROM memory_fts WHERE item_id=OLD.item_id;
        END;

        CREATE TRIGGER summaries_fts_insert AFTER INSERT ON memory_chunks BEGIN
            INSERT INTO summaries_fts(summary,source_type,source_id)
            SELECT NEW.summary,'chunk',NEW.chunk_id WHERE trim(COALESCE(NEW.summary,''))<>'';
        END;
        CREATE TRIGGER summaries_fts_update AFTER UPDATE ON memory_chunks BEGIN
            DELETE FROM summaries_fts WHERE source_type='chunk' AND source_id=OLD.chunk_id;
            INSERT INTO summaries_fts(summary,source_type,source_id)
            SELECT NEW.summary,'chunk',NEW.chunk_id WHERE trim(COALESCE(NEW.summary,''))<>'';
        END;
        CREATE TRIGGER summaries_fts_delete AFTER DELETE ON memory_chunks BEGIN
            DELETE FROM summaries_fts WHERE source_type='chunk' AND source_id=OLD.chunk_id;
        END;

        CREATE TRIGGER people_fts_insert AFTER INSERT ON people BEGIN
            INSERT INTO entities_fts(name,entity_type,entity_id)
            SELECT NEW.canonical_name,'person',NEW.person_id WHERE NEW.status<>'merged' AND trim(COALESCE(NEW.canonical_name,''))<>'';
        END;
        CREATE TRIGGER people_fts_update AFTER UPDATE ON people BEGIN
            DELETE FROM entities_fts WHERE entity_type='person' AND entity_id=OLD.person_id;
            INSERT INTO entities_fts(name,entity_type,entity_id)
            SELECT NEW.canonical_name,'person',NEW.person_id WHERE NEW.status<>'merged' AND trim(COALESCE(NEW.canonical_name,''))<>'';
        END;
        CREATE TRIGGER people_fts_delete AFTER DELETE ON people BEGIN
            DELETE FROM entities_fts WHERE entity_type='person' AND entity_id=OLD.person_id;
        END;

        CREATE TRIGGER companies_fts_insert AFTER INSERT ON companies BEGIN
            INSERT INTO entities_fts(name,entity_type,entity_id)
            SELECT NEW.canonical_name,'company',NEW.company_id WHERE NEW.status<>'merged' AND trim(COALESCE(NEW.canonical_name,''))<>'';
        END;
        CREATE TRIGGER companies_fts_update AFTER UPDATE ON companies BEGIN
            DELETE FROM entities_fts WHERE entity_type='company' AND entity_id=OLD.company_id;
            INSERT INTO entities_fts(name,entity_type,entity_id)
            SELECT NEW.canonical_name,'company',NEW.company_id WHERE NEW.status<>'merged' AND trim(COALESCE(NEW.canonical_name,''))<>'';
        END;
        CREATE TRIGGER companies_fts_delete AFTER DELETE ON companies BEGIN
            DELETE FROM entities_fts WHERE entity_type='company' AND entity_id=OLD.company_id;
        END;

        CREATE TRIGGER projects_fts_insert AFTER INSERT ON projects BEGIN
            INSERT INTO entities_fts(name,entity_type,entity_id)
            SELECT NEW.canonical_name,'project',NEW.project_id WHERE NEW.status<>'merged' AND trim(COALESCE(NEW.canonical_name,''))<>'';
        END;
        CREATE TRIGGER projects_fts_update AFTER UPDATE ON projects BEGIN
            DELETE FROM entities_fts WHERE entity_type='project' AND entity_id=OLD.project_id;
            INSERT INTO entities_fts(name,entity_type,entity_id)
            SELECT NEW.canonical_name,'project',NEW.project_id WHERE NEW.status<>'merged' AND trim(COALESCE(NEW.canonical_name,''))<>'';
        END;
        CREATE TRIGGER projects_fts_delete AFTER DELETE ON projects BEGIN
            DELETE FROM entities_fts WHERE entity_type='project' AND entity_id=OLD.project_id;
        END;

        CREATE TRIGGER entity_memory_fts_insert AFTER INSERT ON entity_memory BEGIN
            INSERT INTO entity_memory_fts(summary,entity_type,entity_id,memory_key)
            SELECT NEW.summary,NEW.entity_type,NEW.entity_id,NEW.memory_key WHERE trim(COALESCE(NEW.summary,''))<>'';
        END;
        CREATE TRIGGER entity_memory_fts_update AFTER UPDATE ON entity_memory BEGIN
            DELETE FROM entity_memory_fts
            WHERE entity_type=OLD.entity_type AND entity_id=OLD.entity_id AND memory_key=OLD.memory_key;
            INSERT INTO entity_memory_fts(summary,entity_type,entity_id,memory_key)
            SELECT NEW.summary,NEW.entity_type,NEW.entity_id,NEW.memory_key WHERE trim(COALESCE(NEW.summary,''))<>'';
        END;
        CREATE TRIGGER entity_memory_fts_delete AFTER DELETE ON entity_memory BEGIN
            DELETE FROM entity_memory_fts
            WHERE entity_type=OLD.entity_type AND entity_id=OLD.entity_id AND memory_key=OLD.memory_key;
        END;
        """
    )
    health = fts_index_health(conn)
    if not health["healthy"]:
        raise RuntimeError("FTS rebuild did not reach source/index parity")


def fts_index_health(conn: sqlite3.Connection) -> dict[str, object]:
    """Compare each FTS index against its authoritative current source rows."""
    if not fts5_available(conn):
        return {"available": False, "healthy": True, "indexes": {}}
    contracts = {
        "messages": (
            "SELECT text,chat_id,message_id FROM messages WHERE is_deleted=0 AND trim(COALESCE(text,''))<>''",
            "SELECT text,chat_id,message_id FROM messages_fts",
        ),
        "tasks": (
            "SELECT title,COALESCE(details,''),task_id FROM tasks WHERE trim(COALESCE(title,'') || COALESCE(details,''))<>''",
            "SELECT title,details,task_id FROM tasks_fts",
        ),
        "memory": (
            "SELECT title,details,item_id FROM ai_items WHERE trim(COALESCE(title,'') || COALESCE(details,''))<>''",
            "SELECT title,details,item_id FROM memory_fts",
        ),
        "summaries": (
            "SELECT summary,'chunk',chunk_id FROM memory_chunks WHERE trim(COALESCE(summary,''))<>''",
            "SELECT summary,source_type,source_id FROM summaries_fts",
        ),
        "entities": (
            "SELECT canonical_name,'person',person_id FROM people WHERE status<>'merged' AND trim(COALESCE(canonical_name,''))<>'' UNION ALL SELECT canonical_name,'company',company_id FROM companies WHERE status<>'merged' AND trim(COALESCE(canonical_name,''))<>'' UNION ALL SELECT canonical_name,'project',project_id FROM projects WHERE status<>'merged' AND trim(COALESCE(canonical_name,''))<>''",
            "SELECT name,entity_type,entity_id FROM entities_fts",
        ),
        "entity_memory": (
            "SELECT summary,entity_type,entity_id,memory_key FROM entity_memory WHERE trim(COALESCE(summary,''))<>''",
            "SELECT summary,entity_type,entity_id,memory_key FROM entity_memory_fts",
        ),
    }
    indexes: dict[str, dict[str, int | bool]] = {}
    for name, (source_sql, index_sql) in contracts.items():
        source_rows = [tuple(row) for row in conn.execute(source_sql)]
        index_rows = [tuple(row) for row in conn.execute(index_sql)]
        source_counts: dict[tuple, int] = {}
        index_counts: dict[tuple, int] = {}
        for row in source_rows:
            source_counts[row] = source_counts.get(row, 0) + 1
        for row in index_rows:
            index_counts[row] = index_counts.get(row, 0) + 1
        missing = sum(
            max(count - index_counts.get(row, 0), 0)
            for row, count in source_counts.items()
        )
        orphaned = sum(
            max(count - source_counts.get(row, 0), 0)
            for row, count in index_counts.items()
        )
        indexes[name] = {
            "source_rows": len(source_rows),
            "index_rows": len(index_rows),
            "missing_rows": missing,
            "orphaned_rows": orphaned,
            "healthy": missing == 0 and orphaned == 0,
        }
    return {
        "available": True,
        "healthy": all(bool(index["healthy"]) for index in indexes.values()),
        "indexes": indexes,
    }
