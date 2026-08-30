#!/usr/bin/env python3
"""Safe local developer tooling for Alex Memory.

Commands in this module deliberately inspect database metadata only. They never
print Telegram messages, session contents, or environment-variable values.
"""

from __future__ import annotations

import argparse
import ast
from datetime import UTC, datetime
import json
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
DOCS = ROOT / "docs"
DB_PATH = ROOT / "data" / "telegram.sqlite"
ENV_EXAMPLE = ROOT / ".env.example"
CONFIG_PATH = SRC / "alex_memory" / "config.py"
DATABASE_PATH = SRC / "alex_memory" / "database.py"
UV = ROOT / ".venv" / "bin" / "uv"

GENERATED_START = "<!-- AUTO-GENERATED:START -->"
GENERATED_END = "<!-- AUTO-GENERATED:END -->"

ENV_DESCRIPTIONS = {
    "TELEGRAM_API_ID": "Telegram application identifier (required).",
    "TELEGRAM_API_HASH": "Telegram application hash (required).",
    "TG_WORKERS": "Concurrent Telegram history workers.",
    "GROUP_FULL_THRESHOLD": "Archive full history for groups at or below this size.",
    "GROUP_RECENT_LIMIT": "Recent-message limit for large groups.",
    "TG_WRITE_QUEUE_SIZE": "Bounded SQLite write queue capacity.",
    "TG_COMMIT_EVERY": "Messages written before a Telegram sync commit.",
    "TG_RECONCILE_ENABLED": "Enable periodic incremental reconciliation.",
    "TG_RECONCILE_INTERVAL_MINUTES": "Minutes between reconciliation passes.",
    "TG_ITER_MESSAGES_WAIT_SECONDS": "Delay between Telegram history requests.",
    "GROQ_API_KEY": "Groq API key; optional unless Groq is selected.",
    "GROQ_MODEL": "Groq model identifier.",
    "GEMINI_API_KEY": "Gemini API key; optional unless Gemini is selected.",
    "GEMINI_MODEL": "Gemini model identifier.",
    "GEMINI_REQUESTS_PER_MINUTE": "Maximum Gemini requests per rolling minute.",
    "AI_PRIMARY_PROVIDER": "Primary AI provider: gemini or groq.",
    "AI_FALLBACK_PROVIDER": "Fallback AI provider: gemini or groq.",
    "AI_WORKERS": "Concurrent AI analysis workers.",
    "AI_MAX_MESSAGES_PER_RUN": "Legacy fallback for the daily analysis limit.",
    "AI_DAILY_MAX_MESSAGES": "Maximum messages considered in one daily run.",
    "AI_BATCH_MESSAGES": "Maximum messages in one AI request.",
    "AI_BATCH_CHARS": "Maximum characters in one AI request.",
    "AI_MAX_MESSAGE_CHARS": "Maximum characters retained per message for AI.",
    "AI_MAX_OUTPUT_TOKENS": "Maximum tokens reserved for an AI response.",
    "AI_MAX_RETRIES": "Attempts for a recoverable AI-provider failure.",
    "AI_RETRY_BASE_SECONDS": "Base delay for AI retry backoff.",
    "AI_REPORT_BATCHES": "Recent AI batches retained in diagnostics output.",
    "AI_INCLUDE_GROUPS": "Allow group messages to be analyzed by AI.",
    "AI_HISTORY_CHUNKS_PER_RUN": "Historical chunks processed per run.",
    "AI_HISTORY_CHUNK_MESSAGES": "Messages in each historical analysis chunk.",
    "AI_HISTORY_CHUNK_CHARS": "Character budget for a historical chunk.",
    "AI_CONTEXT_MESSAGES": "Prior messages included as bounded AI context.",
    "AI_AUTO_ACCEPT_CONFIDENCE": "Confidence at which operational updates are automatic.",
    "AI_REVIEW_CONFIDENCE": "Confidence at which findings enter review.",
    "AI_AUTO_ANALYZE_NEW_MESSAGES": "Enable periodic AI analysis of new messages.",
    "AI_AUTO_ANALYZE_INTERVAL_MINUTES": "Minutes between automatic AI runs.",
    "HISTORY_AUTO_ANALYZE": "Run resumable history analysis only while live ingestion is quiet.",
    "HISTORY_AUTO_ANALYZE_INTERVAL_MINUTES": "Minutes between quiet-time history-analysis checks.",
    "HISTORY_INTERNAL_CONCURRENCY": "Maximum provider-safe history jobs claimed in one run.",
    "HISTORY_INTERNAL_BATCH_MESSAGES": "Message limit for each provider-safe history window.",
    "HISTORY_INTERNAL_BATCH_CHARS": "Character limit for each provider-safe history window.",
    "DAILY_BRIEF_AUTO_GENERATE": "Enable scheduled daily-brief generation.",
    "DAILY_BRIEF_TIME": "Local time for daily brief generation.",
    "APP_TIMEZONE": "IANA timezone used for temporal interpretation.",
    "QA_MAX_RAW_MESSAGES": "Raw evidence limit for question answering.",
    "QA_MAX_TASKS": "Task limit for question-answering context.",
    "QA_MAX_MEMORIES": "Memory-item limit for question-answering context.",
    "QA_MAX_SUMMARIES": "Summary limit for question-answering context.",
    "QA_MAX_CONTEXT_CHARS": "Character cap for question-answering context.",
    "QA_USE_LLM": "Use an AI provider after deterministic retrieval.",
    "FOLLOW_UP_WAITING_AFTER_DAYS": "Waiting age before a follow-up is created.",
    "PROJECT_STALE_DAYS": "Days without activity before a project is stale.",
    "PROJECT_CRITICAL_STALE_DAYS": "Days without activity before critical status.",
    "NOTIFICATION_REPEAT_HOURS": "Minimum interval between duplicate notifications.",
    "CONTEXT_MAX_CHARS": "Character cap for contextual-memory assembly.",
    "CONTEXT_MAX_RAW_MESSAGES": "Raw-evidence limit for contextual memory.",
    "CONTEXT_MAX_EVENTS": "Event limit for contextual memory.",
    "CONTEXT_MAX_FACTS": "Fact limit for contextual memory.",
    "CONTEXT_MAX_TASKS": "Task limit for contextual memory.",
    "CONTEXT_MAX_SUMMARIES": "Summary limit for contextual memory.",
    "CONTEXT_MAX_PEOPLE": "Maximum people selected for a context package.",
    "CONTEXT_MAX_PROJECTS": "Maximum projects selected for a context package.",
    "CONTEXT_MAX_COMPANIES": "Maximum companies selected for a context package.",
    "CONTEXT_MAX_GRAPH_DEPTH": "Maximum relationship hops from resolved entities.",
    "TASK_DEEP_DIVE_MAX_SEARCH_ROUNDS": "Maximum bounded expansion rounds in a task investigation.",
    "TASK_DEEP_DIVE_MAX_QUERIES_PER_ROUND": "Maximum deterministic message queries in one deep-dive round.",
    "TASK_DEEP_DIVE_MAX_EVIDENCE": "Maximum selected evidence items for one task deep dive.",
    "TASK_DEEP_DIVE_MAX_RAW_MESSAGES": "Maximum raw Telegram messages selected for one task deep dive.",
    "TASK_DEEP_DIVE_CONTEXT_BEFORE": "Messages before a selected item shown as conversation context.",
    "TASK_DEEP_DIVE_CONTEXT_AFTER": "Messages after a selected item shown as conversation context.",
    "TASK_DEEP_DIVE_MAX_GRAPH_DEPTH": "Documented task-deep-dive relationship traversal limit.",
    "TASK_DEEP_DIVE_MAX_CONTEXT_CHARS": "Rendering character cap for task-deep-dive context.",
}

TABLE_PURPOSES = {
    "schema_migrations": "Ordered record of applied SQLite schema migrations.",
    "source_evidence": "Source-neutral current evidence records for future ingestors.",
    "source_evidence_versions": "Prior source-evidence content retained across edits and deletions.",
    "message_classifications": "Versioned local routing classifications for archived messages.",
    "conversation_analysis_state": "Per-chat durable history-analysis coverage checkpoints.",
    "context_conflict_observations": "Proposed source-backed values for unresolved temporal conflicts.",
    "context_conflict_decisions": "Append-only manual resolutions of temporal fact conflicts.",
    "chats": "Archived Telegram dialog metadata.",
    "messages": "Raw Telegram evidence, including edit/deletion state.",
    "message_versions": "Audit trail for edited or deleted message text.",
    "sync_state": "Per-chat archive progress and bootstrap mode.",
    "ai_batches": "Provider request/response diagnostics for analysis batches.",
    "ai_jobs": "Resumable daily and historical analysis work.",
    "ai_message_state": "Analysis state for individual source messages.",
    "ai_items": "Validated, source-backed extracted observations.",
    "app_meta": "Small application metadata values.",
    "people": "Canonical people.",
    "companies": "Canonical companies.",
    "projects": "Canonical projects and health state.",
    "entity_aliases": "Normalized names and aliases for entity resolution.",
    "entity_relationships": "Inert compatibility table retained pending a future safe schema migration; no maintained runtime reader or writer.",
    "entity_merge_candidates": "Ambiguous identity merges awaiting review.",
    "review_queue": "Low-confidence or ambiguous decisions for review.",
    "tasks": "Canonical operational tasks and manual locks.",
    "task_events": "Audit history for task lifecycle changes.",
    "memory_chunks": "Durable summaries of completed AI batches.",
    "chat_daily_summaries": "Per-chat daily rollups.",
    "chat_monthly_summaries": "Per-chat monthly rollups.",
    "entity_memory": "Durable per-entity memory summaries.",
    "daily_briefs": "Stored structured daily brief payloads.",
    "follow_ups": "Deduplicated operational follow-ups.",
    "chat_ai_policy": "Explicit per-chat AI inclusion policy.",
    "user_feedback": "Manual feedback on entities and decisions.",
    "notification_outbox": "Deduplicated pending/sent attention notifications.",
    "context_events": "Source-backed canonical events.",
    "context_facts": "Temporal facts with validity intervals.",
    "relationships": "Temporal relationships between canonical entities.",
    "context_conflicts": "Conflicting fact observations awaiting resolution.",
    "context_summary_versions": "Versioned contextual summaries.",
    "global_state_snapshots": "Point-in-time global state summaries.",
    "pinned_memory": "User-pinned canonical memory.",
    "person_context_state": "Materialized current person context.",
    "temporal_resolutions": "Resolved relative/dependent time expressions.",
    "task_deep_dive_sessions": "Bounded task-investigation sessions and selected evidence metadata.",
    "task_deep_dive_evidence": "Evidence references discovered by a task-investigation session.",
    "task_notes": "User-authored notes attached to a canonical task.",
    "task_deep_dive_pins": "User-pinned evidence references for a canonical task.",
}


def config_variables() -> list[str]:
    """Return environment variable names from the actual settings implementation."""
    text = CONFIG_PATH.read_text(encoding="utf-8")
    names = set(re.findall(r'os\.getenv\("([A-Z][A-Z0-9_]+)"', text))
    names.update(
        re.findall(
            r'_(?:positive_int|provider_name|confidence|bool|clock_time|timezone|nonnegative_float)\(\s*"([A-Z][A-Z0-9_]+)"',
            text,
        )
    )
    return sorted(names)


def env_defaults() -> dict[str, str]:
    defaults: dict[str, str] = {}
    for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        if "=" not in line or line.lstrip().startswith("#"):
            continue
        name, value = line.split("=", 1)
        defaults[name.strip()] = value.strip()
    return defaults


def schema_summary() -> str:
    source = DATABASE_PATH.read_text(encoding="utf-8")
    schema = re.search(r'SCHEMA\s*=\s*"""(.*?)"""', source, re.DOTALL)
    if schema is None:
        raise RuntimeError("Could not find SCHEMA in src/alex_memory/database.py")
    blocks = re.findall(
        r"CREATE TABLE IF NOT EXISTS ([a-z_]+) \((.*?)\);", schema.group(1), re.DOTALL
    )
    indexes: dict[str, list[str]] = {}
    for name, table, columns in re.findall(
        r"CREATE INDEX IF NOT EXISTS ([a-z_]+)\s+ON ([a-z_]+)\(([^)]+)\)",
        schema.group(1),
    ):
        indexes.setdefault(table, []).append(f"{name} ({columns})")

    lines = [
        "| Table | Purpose | Primary/key columns | Important indexes |",
        "| --- | --- | --- | --- |",
    ]
    for table, body in blocks:
        cols = []
        for raw in body.splitlines():
            line = raw.strip().rstrip(",")
            if not line or line.startswith(
                ("PRIMARY KEY", "FOREIGN KEY", "UNIQUE", "CHECK")
            ):
                continue
            parts = line.split()
            if len(parts) >= 2:
                cols.append(parts[0])
        important = ", ".join(indexes.get(table, [])) or "—"
        keys = f"`{', '.join(cols[:6])}`{' …' if len(cols) > 6 else ''}"
        lines.append(
            f"| `{table}` | {TABLE_PURPOSES.get(table, 'Application data.')} | {keys} | `{important}` |"
        )
    return "\n".join(lines)


def generated_environment_table() -> str:
    defaults = env_defaults()
    lines = ["| Variable | Example/default | Meaning |", "| --- | --- | --- |"]
    for name in config_variables():
        default = defaults.get(name, "(runtime default)")
        description = ENV_DESCRIPTIONS.get(name, "See `Settings` in `config.py`.")
        lines.append(f"| `{name}` | `{default}` | {description} |")
    return "\n".join(lines)


def replace_generated(content: str, generated: str) -> str:
    replacement = f"{GENERATED_START}\n{generated}\n{GENERATED_END}"
    pattern = re.escape(GENERATED_START) + r".*?" + re.escape(GENERATED_END)
    if not re.search(pattern, content, flags=re.DOTALL):
        raise RuntimeError("Document is missing auto-generated markers")
    return re.sub(pattern, replacement, content, flags=re.DOTALL)


DOCUMENTS = {
    "ARCHITECTURE.md": """# Architecture\n\nAlex Memory is a local, source-backed operational memory system. Telegram is the current ingestion source; Gmail, WhatsApp, iMessage, and Drive are future sources that should feed the same evidence model rather than bypass it.\n\n## Data flow\n\n```text\nRaw evidence → AI observations → events / temporal facts → canonical state\n→ bounded context → intelligence, tasks, follow-ups, briefs, search\n```\n\n## Components\n\n- `telegram/`: inventory, catch-up sync, live handlers, normalization, and the bounded SQLite writer queue.\n- `ai/`: batching, Gemini/Groq routing and validated source-backed findings.\n- `operational.py`: canonical entities, tasks, review queue, briefs, and summaries.\n- `context/`: temporal facts, relationships, contextual builders, and global snapshots.\n- `intelligence.py`: bounded retrieval, grounded Q&A, follow-ups, profiles, and notifications.\n\n## Invariants\n\nRaw messages remain traceable. AI findings are fallible and must validate against submitted source messages. Manual task state beats later AI inference. Current and historical facts are distinct. Provider failure must not stop Telegram ingestion.\n""",
    "DATA_MODEL.md": """# Data Model\n\nThe application records ordered schema upgrades in `schema_migrations`. A new database applies the current migration sequence; a pre-ledger database adopts the idempotent bootstrap and compatibility migrations on its next open. Back up a live database through `make db-backup` before a migration that changes existing data or columns.\n\n## Schema summary\n\n"""
    + GENERATED_START
    + "\n"
    + GENERATED_END
    + "\n\nFTS5 indexes messages, tasks, entities, durable memory, and summaries where the local SQLite build supports it.\n",
    "DEVELOPMENT.md": """# Development\n\nUse Python 3.12 and the locked repository virtual environment. Dependencies live in `pyproject.toml` and `uv.lock`; do not use ad-hoc `pip install` commands for project dependencies.\n\n```bash\n# Install uv first: https://docs.astral.sh/uv/getting-started/installation/\nuv sync\ncode .\n```\n\nCopy `.env.example` to `.env` and provide your Telegram credentials. Tests use temporary SQLite databases and must not authenticate with Telegram.\n\n## Environment reference\n\n"""
    + GENERATED_START
    + "\n"
    + GENERATED_END
    + "\n\nRun `make docs` after changing `Settings` or the database schema, and `make docs-check` in review. `make check` is the fast deterministic gate. `make verify` also validates the lockfile, dependency declarations, known package vulnerabilities, SQLite integrity, generated documentation, and task-queue structure.\n",
    "OPERATIONS.md": """# Operations\n\n`make run` starts the interactive terminal UI and also installs live Telegram sync. `make daemon` is for an unattended local process and should be supervised by the host process manager when used in production. No systemd unit is currently present in this repository.\n\nDatabase safety: `data/telegram.sqlite` is a live WAL database. Use `make db-check` for read-only integrity checks and `make db-backup` for a consistent SQLite backup API snapshot. Never copy a live `.sqlite` file alone or inspect/commit Telegram session files.\n\n`make health` only reports configuration presence; it never prints secrets.\n""",
    "AI_PIPELINE.md": """# AI Pipeline\n\nAI work is bounded and source-backed. Telegram messages are normalized, filtered by chat policy, grouped into limited batches, then sent to the configured primary provider (Gemini by default) with Groq as fallback. Results are locally validated before they are saved; messages are marked analyzed only with a successful persistence transaction.\n\nOperational projection creates canonical entities, tasks, summaries, memory chunks, and review records. Low-confidence or ambiguous changes remain reviewable. Do not use an LLM for deterministic matching, timestamp arithmetic, SQL joins, or simple scoring.\n""",
    "CONTEXT_ENGINE.md": """# Context Engine\n\nThe context subsystem converts source-backed observations into events, temporal facts, relationships, snapshots, and bounded context bundles. A changed current fact closes the prior validity interval instead of overwriting history. Builders accept an `as_of` time and prioritize canonical and pinned state before summaries and limited raw evidence.\n\nThis keeps retrieval explainable and prevents unbounded Telegram history from being sent to an AI provider.\n""",
}


def rendered_documents() -> dict[Path, str]:
    rendered: dict[Path, str] = {}
    for name, template in DOCUMENTS.items():
        generated = (
            schema_summary()
            if name == "DATA_MODEL.md"
            else generated_environment_table()
            if name == "DEVELOPMENT.md"
            else ""
        )
        path = DOCS / name
        # Preserve all human-maintained prose in existing documents. Only the
        # generated marker region may be replaced after the initial scaffold.
        current = path.read_text(encoding="utf-8") if path.exists() else template
        rendered[path] = replace_generated(current, generated) if generated else current
    return rendered


def docs(check: bool) -> int:
    expected = rendered_documents()
    stale = []
    for path, content in expected.items():
        if not path.exists() or path.read_text(encoding="utf-8") != content:
            stale.append(path)
            if not check:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
    configured = set(config_variables())
    exemplar = set(env_defaults())
    missing = sorted(configured - exemplar)
    if missing:
        print(".env.example is missing settings:", ", ".join(missing))
        return 1
    if check and stale:
        print("Generated documentation is stale:")
        for path in stale:
            print(" -", path.relative_to(ROOT))
        return 1
    print("Documentation is current." if check else "Documentation generated.")
    return 0


def readonly_connection() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise RuntimeError(f"Database is missing: {DB_PATH.relative_to(ROOT)}")
    return sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)


def logical_reference_violations(
    conn: sqlite3.Connection,
) -> list[tuple[str, str, int]]:
    """Return bounded counts for logical references without inspecting content."""
    checks = (
        (
            "tasks",
            "related_person_id",
            """SELECT COUNT(*) FROM tasks AS child
               WHERE child.related_person_id IS NOT NULL
                 AND NOT EXISTS (SELECT 1 FROM people WHERE person_id=child.related_person_id)""",
        ),
        (
            "tasks",
            "related_company_id",
            """SELECT COUNT(*) FROM tasks AS child
               WHERE child.related_company_id IS NOT NULL
                 AND NOT EXISTS (SELECT 1 FROM companies WHERE company_id=child.related_company_id)""",
        ),
        (
            "tasks",
            "related_project_id",
            """SELECT COUNT(*) FROM tasks AS child
               WHERE child.related_project_id IS NOT NULL
                 AND NOT EXISTS (SELECT 1 FROM projects WHERE project_id=child.related_project_id)""",
        ),
        (
            "tasks",
            "source_item_id",
            """SELECT COUNT(*) FROM tasks AS child
               WHERE child.source_item_id IS NOT NULL
                 AND NOT EXISTS (SELECT 1 FROM ai_items WHERE item_id=child.source_item_id)""",
        ),
        (
            "ai_items",
            "source_message",
            """SELECT COUNT(*) FROM ai_items AS child
               WHERE NOT EXISTS (
                   SELECT 1 FROM messages
                   WHERE chat_id=child.source_chat_id AND message_id=child.source_message_id
               )""",
        ),
        (
            "entity_relationships",
            "source_item_id",
            """SELECT COUNT(*) FROM entity_relationships AS child
               WHERE child.source_item_id IS NOT NULL
                 AND NOT EXISTS (SELECT 1 FROM ai_items WHERE item_id=child.source_item_id)""",
        ),
        (
            "relationships",
            "from_endpoint",
            """SELECT COUNT(*) FROM relationships AS child WHERE NOT CASE child.from_type
                 WHEN 'person' THEN EXISTS (SELECT 1 FROM people WHERE person_id=child.from_id)
                 WHEN 'company' THEN EXISTS (SELECT 1 FROM companies WHERE company_id=child.from_id)
                 WHEN 'project' THEN EXISTS (SELECT 1 FROM projects WHERE project_id=child.from_id)
                 WHEN 'task' THEN EXISTS (SELECT 1 FROM tasks WHERE task_id=child.from_id)
                 WHEN 'event' THEN EXISTS (SELECT 1 FROM context_events WHERE event_id=child.from_id)
                 WHEN 'fact' THEN EXISTS (SELECT 1 FROM context_facts WHERE fact_id=child.from_id)
                 ELSE 0 END""",
        ),
        (
            "relationships",
            "to_endpoint",
            """SELECT COUNT(*) FROM relationships AS child WHERE NOT CASE child.to_type
                 WHEN 'person' THEN EXISTS (SELECT 1 FROM people WHERE person_id=child.to_id)
                 WHEN 'company' THEN EXISTS (SELECT 1 FROM companies WHERE company_id=child.to_id)
                 WHEN 'project' THEN EXISTS (SELECT 1 FROM projects WHERE project_id=child.to_id)
                 WHEN 'task' THEN EXISTS (SELECT 1 FROM tasks WHERE task_id=child.to_id)
                 WHEN 'event' THEN EXISTS (SELECT 1 FROM context_events WHERE event_id=child.to_id)
                 WHEN 'fact' THEN EXISTS (SELECT 1 FROM context_facts WHERE fact_id=child.to_id)
                 ELSE 0 END""",
        ),
        (
            "source_evidence_versions",
            "evidence_id",
            """SELECT COUNT(*) FROM source_evidence_versions AS child
               WHERE NOT EXISTS (
                   SELECT 1 FROM source_evidence WHERE evidence_id=child.evidence_id
               )""",
        ),
        (
            "conversation_open_loops",
            "task_id",
            """SELECT COUNT(*) FROM conversation_open_loops AS child
               WHERE child.task_id IS NOT NULL
                 AND NOT EXISTS (SELECT 1 FROM tasks WHERE task_id=child.task_id)""",
        ),
        (
            "current_conversation_context",
            "person_id",
            """SELECT COUNT(*) FROM current_conversation_context AS child
               WHERE NOT EXISTS (SELECT 1 FROM people WHERE person_id=child.person_id)""",
        ),
        (
            "current_conversation_context",
            "primary_project_id",
            """SELECT COUNT(*) FROM current_conversation_context AS child
               WHERE child.primary_project_id IS NOT NULL
                 AND NOT EXISTS (SELECT 1 FROM projects WHERE project_id=child.primary_project_id)""",
        ),
        (
            "current_conversation_context",
            "primary_company_id",
            """SELECT COUNT(*) FROM current_conversation_context AS child
               WHERE child.primary_company_id IS NOT NULL
                 AND NOT EXISTS (SELECT 1 FROM companies WHERE company_id=child.primary_company_id)""",
        ),
    )
    violations = []
    for table, key, query in checks:
        count = int(conn.execute(query).fetchone()[0])
        if count:
            violations.append((table, key, count))
    return violations


def db_check() -> int:
    try:
        with readonly_connection() as conn:
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
            foreign_keys = conn.execute("PRAGMA foreign_key_check").fetchall()
            logical_references = logical_reference_violations(conn)
            version_row = conn.execute(
                "SELECT COALESCE(MAX(version), 0) FROM schema_migrations"
            ).fetchone()
            fts_health = _fts_health(conn)
    except (OSError, sqlite3.Error) as error:
        print(f"Database check failed: {error}")
        return 1
    print("SQLite integrity:", integrity)
    print("Foreign-key violations:", len(foreign_keys))
    print("Logical-reference violations:", len(logical_references))
    for table, key, count in logical_references:
        print(f" - {table}.{key}: {count}")
    print("Schema version:", int(version_row[0] or 0))
    _print_fts_health(fts_health)
    return (
        0
        if integrity == "ok"
        and not foreign_keys
        and not logical_references
        and fts_health["healthy"]
        else 1
    )


def db_backup() -> int:
    if not DB_PATH.exists():
        print("Database backup skipped: data/telegram.sqlite is missing.")
        return 1
    destination_dir = ROOT / "backups"
    destination_dir.mkdir(mode=0o700, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    destination = destination_dir / f"telegram-{stamp}.sqlite"
    try:
        with sqlite3.connect(DB_PATH) as source, sqlite3.connect(destination) as target:
            source.backup(target)
        destination.chmod(0o600)
    except (OSError, sqlite3.Error) as error:
        print(f"Database backup failed: {error}")
        return 1
    print(f"SQLite backup created: {destination.relative_to(ROOT)}")
    return 0


def repair_dry_run(operations: list[str], limit: int) -> int:
    """Print a read-only, finite derived-state repair scope."""
    if not operations:
        print("Repair dry-run requires at least one --operation.")
        return 1
    if limit < 1:
        print("Repair dry-run limit must be positive.")
        return 1
    sys.path.insert(0, str(SRC))
    from alex_memory.repair import derived_state_repair_dry_run

    try:
        with readonly_connection() as conn:
            report = derived_state_repair_dry_run(
                conn, operations=set(operations), limit=limit
            )
    except (OSError, sqlite3.Error, ValueError) as error:
        print(f"Repair dry-run failed: {error}")
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0


def graph_parity(seeds: list[str], as_of: str | None, max_depth: int) -> int:
    """Report whether one bounded ContextBuilder relationship scope is graph-ready."""
    parsed_seeds: list[tuple[str, int]] = []
    for seed in seeds:
        match = re.fullmatch(r"(person|company|project):([1-9][0-9]*)", seed)
        if match is None:
            print("Graph parity seeds must use person|company|project:positive-id.")
            return 1
        parsed_seeds.append((match.group(1), int(match.group(2))))
    if not parsed_seeds:
        print("Graph parity requires at least one --seed.")
        return 1
    if max_depth < 0:
        print("Graph parity max depth must be non-negative.")
        return 1
    selected_as_of = as_of or datetime.now(UTC).isoformat()
    try:
        datetime.fromisoformat(selected_as_of.replace("Z", "+00:00"))
    except ValueError:
        print("Graph parity --as-of must be an ISO-8601 timestamp.")
        return 1

    sys.path.insert(0, str(SRC))
    from alex_memory.context.graph import context_builder_relationship_parity_gaps

    try:
        with readonly_connection() as conn:
            report = context_builder_relationship_parity_gaps(
                conn,
                parsed_seeds,
                selected_as_of,
                max_depth=max_depth,
            )
    except (OSError, sqlite3.Error, ValueError) as error:
        print(f"Graph parity failed: {error}")
        return 1
    report["ready"] = not bool(report["truncated"] or report["gaps"])
    print(json.dumps(report, sort_keys=True))
    return 0


def env_names(path: Path) -> set[str]:
    if not path.exists():
        return set()
    result = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            result.add(line.split("=", 1)[0].strip())
    return result


def health() -> int:
    rows: list[tuple[str, bool, str]] = []
    rows.append(("Python", sys.version_info >= (3, 12), sys.version.split()[0]))
    rows.append(("Virtualenv", sys.prefix != sys.base_prefix, Path(sys.prefix).name))
    rows.append(
        ("Database", DB_PATH.exists(), "present" if DB_PATH.exists() else "missing")
    )
    fts_health: dict[str, object] = {
        "available": False,
        "healthy": True,
        "indexes": {},
    }
    fts_error: str | None = None
    if DB_PATH.exists():
        try:
            with readonly_connection() as conn:
                fts_health = _fts_health(conn)
        except sqlite3.Error as error:
            fts_error = str(error)
    if fts_error:
        rows.append(("SQLite FTS5", False, f"broken: {fts_error}"))
    elif bool(fts_health["available"]):
        rows.append(("SQLite FTS5", True, "available"))
        rows.append(
            (
                "FTS coverage",
                bool(fts_health["healthy"]),
                _fts_health_detail(fts_health),
            )
        )
    else:
        rows.append(("SQLite FTS5", True, "unavailable; SQL fallback"))
    configured = env_names(ROOT / ".env")
    rows.append(
        (
            "Telegram config",
            {"TELEGRAM_API_ID", "TELEGRAM_API_HASH"} <= configured,
            "configured"
            if {"TELEGRAM_API_ID", "TELEGRAM_API_HASH"} <= configured
            else "missing required names",
        )
    )
    rows.append(
        (
            "Telegram session",
            (ROOT / "alex_memory.session").exists(),
            "present" if (ROOT / "alex_memory.session").exists() else "missing",
        )
    )
    rows.append(
        (
            "Gemini config",
            "GEMINI_API_KEY" in configured,
            "configured" if "GEMINI_API_KEY" in configured else "not configured",
        )
    )
    rows.append(
        (
            "Groq config",
            "GROQ_API_KEY" in configured,
            "configured" if "GROQ_API_KEY" in configured else "not configured",
        )
    )
    disk = shutil.disk_usage(ROOT)
    rows.append(("Free disk", disk.free > 0, f"{disk.free // (1024**3)} GiB"))
    print("Alex Memory Health")
    failed = False
    for label, ok, detail in rows:
        print(f"{label:<18} {'OK' if ok else 'WARN'}  {detail}")
        failed = (
            failed
            or label
            in {
                "Python",
                "Virtualenv",
                "Database",
                "SQLite FTS5",
                "FTS coverage",
            }
            and not ok
        )
    return 1 if failed else 0


def _fts_health(conn: sqlite3.Connection) -> dict[str, object]:
    """Load the application-owned FTS coverage check without exposing content."""
    sys.path.insert(0, str(SRC))
    from alex_memory.schema_support import fts_index_health

    return fts_index_health(conn)


def _fts_health_detail(health: dict[str, object]) -> str:
    indexes = health["indexes"]
    assert isinstance(indexes, dict)
    parts = []
    for name, values in indexes.items():
        assert isinstance(values, dict)
        parts.append(
            f"{name}: {values['index_rows']}/{values['source_rows']} "
            f"(missing {values['missing_rows']}, orphaned {values['orphaned_rows']})"
        )
    return "; ".join(parts)


def _print_fts_health(health: dict[str, object]) -> None:
    if not bool(health["available"]):
        print("FTS5 coverage: unavailable; SQL fallback")
        return
    print("FTS5 coverage:", _fts_health_detail(health))
    print("FTS5 indexes healthy:", bool(health["healthy"]))


def git_output(*args: str) -> tuple[int, str]:
    result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    return result.returncode, result.stdout.strip() or result.stderr.strip()


def changes() -> int:
    code, status = git_output("status", "--short")
    if code:
        print("Git change summary unavailable: this directory is not a Git worktree.")
        print(
            "Update CHANGELOG.md and docs/CHANGES.md from a reviewed file diff once Git is initialized."
        )
        return 0
    _, names = git_output("diff", "--name-status")
    _, stat = git_output("diff", "--stat")
    print("Git status:\n" + (status or "clean"))
    if status and not names:
        print("\nTracked diff:\nno tracked changes")
        print("\nNote: untracked paths are shown in Git status but not git diff.")
    else:
        print("\nChanged paths:\n" + (names or "no unstaged changes"))
        print("\nDiff stat:\n" + (stat or "no unstaged changes"))
    return 0


def task_summary() -> int:
    path = ROOT / "TASKS.md"
    if not path.exists():
        print("TASKS.md is missing")
        return 1
    text = path.read_text(encoding="utf-8")
    ids = re.findall(r"^- \[[ x]\] (AM-\d{3})\b", text, re.MULTILINE)
    now = re.search(r"## Now\n(.*?)(?=\n## |\Z)", text, re.DOTALL)
    completed_in_now = bool(now and re.search(r"- \[x\]", now.group(1)))
    print(
        f"Tasks: {len(ids)} IDs; {text.count('- [ ]')} open; {text.count('- [x]')} completed"
    )
    if completed_in_now:
        print("Completed tasks must not remain in Now.")
    return 1 if completed_in_now else 0


def code_health() -> int:
    modules: list[tuple[int, Path]] = []
    large_functions: list[tuple[int, Path, str, int]] = []
    bare_excepts: list[tuple[Path, int]] = []
    exception_passes: list[tuple[Path, int]] = []
    for path in sorted(SRC.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        modules.append((source.count("\n") + 1, path))
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                end = getattr(node, "end_lineno", node.lineno)
                if end - node.lineno + 1 > 100:
                    large_functions.append(
                        (end - node.lineno + 1, path, node.name, node.lineno)
                    )
            if isinstance(node, ast.ExceptHandler):
                if node.type is None:
                    bare_excepts.append((path, node.lineno))
                if (
                    isinstance(node.type, ast.Name)
                    and node.type.id == "Exception"
                    and len(node.body) == 1
                    and isinstance(node.body[0], ast.Pass)
                ):
                    exception_passes.append((path, node.lineno))
    todo_count = sum(
        len(re.findall(r"\b(?:TODO|FIXME)\b", path.read_text(encoding="utf-8")))
        for path in SRC.rglob("*.py")
    )
    print("Largest modules:")
    for lines, path in sorted(modules, reverse=True)[:8]:
        print(f"  {lines:>4}  {path.relative_to(ROOT)}")
    print("Functions over ~100 lines:", len(large_functions))
    for lines, path, name, line in sorted(large_functions, reverse=True):
        print(f"  {lines:>4}  {path.relative_to(ROOT)}:{line} {name}")
    print("Bare except clauses:", len(bare_excepts))
    print("except Exception: pass:", len(exception_passes))
    print("TODO/FIXME markers:", todo_count)
    return 0


def review() -> int:
    print("Alex Memory review (flags require judgment; they do not replace review)")
    code_health()
    print(
        "Checklist: inspect source duplication, new dependencies, test coverage, bounded queues/context, logging, SQL/shell safety, and docs/task/changelog updates."
    )
    return 0


def run_checks() -> int:
    commands = [
        [sys.executable, "-m", "compileall", "-q", "src"],
        [sys.executable, "-m", "pytest"],
        [sys.executable, "-m", "ruff", "check", "src", "tests", "scripts"],
        [sys.executable, "-m", "ruff", "format", "--check", "src", "tests", "scripts"],
        [sys.executable, "-m", "mypy", "src", "scripts"],
    ]
    status = 0
    for command in commands:
        print("$", " ".join(command))
        status |= subprocess.run(command, cwd=ROOT).returncode
    return status


def uv_command(*args: str) -> list[str]:
    """Use the synced project tool, falling back to a bootstrap installation."""
    return [str(UV if UV.exists() else "uv"), *args]


def dependency_check() -> int:
    command = uv_command("run", "--locked", "deptry", ".")
    print("$", " ".join(command))
    try:
        return subprocess.run(command, cwd=ROOT).returncode
    except FileNotFoundError:
        print("uv is unavailable; install uv and run `uv sync` first.")
        return 1


def security_audit() -> int:
    command = uv_command("run", "--locked", "pip-audit")
    print("$", " ".join(command))
    try:
        return subprocess.run(command, cwd=ROOT).returncode
    except FileNotFoundError:
        print("uv is unavailable; install uv and run `uv sync` first.")
        return 1


def verify() -> int:
    status = run_checks()
    status |= docs(check=True)
    lock_command = uv_command("lock", "--check")
    print("$", " ".join(lock_command))
    try:
        status |= subprocess.run(lock_command, cwd=ROOT).returncode
    except FileNotFoundError:
        print("uv is unavailable; install uv and run `uv sync` first.")
        status |= 1
    status |= dependency_check()
    status |= security_audit()
    status |= db_check()
    status |= task_summary()
    return status


def codex_hooks_check() -> int:
    """Validate local Codex hooks without reading private configuration or data."""
    command = [sys.executable, str(ROOT / ".codex" / "hooks" / "check.py")]
    print("$", " ".join(command))
    return subprocess.run(command, cwd=ROOT).returncode


def codex_check() -> int:
    print("Alex Memory Codex Check")
    code, git_status = git_output("status", "--short")
    print("Git status:", git_status if not code else "unavailable (not a Git worktree)")
    print("Python:", sys.version.split()[0])
    print("Environment:", sys.prefix)
    status = codex_hooks_check()
    status |= verify()
    changelog = (
        (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        if (ROOT / "CHANGELOG.md").exists()
        else ""
    )
    print(
        "Unreleased changelog section:",
        "present" if "## Unreleased" in changelog else "missing",
    )
    return status


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=(
            "docs",
            "docs-check",
            "db-check",
            "db-backup",
            "repair-dry-run",
            "graph-parity",
            "health",
            "changes",
            "tasks",
            "review",
            "codex-hooks-check",
            "codex-check",
            "check",
            "verify",
        ),
    )
    parser.add_argument(
        "--operation",
        action="append",
        choices=("fts", "task-project", "segments", "context", "project-health"),
        help="One repair operation to include; required for repair-dry-run.",
    )
    parser.add_argument(
        "--seed",
        action="append",
        help="ContextBuilder seed in person|company|project:positive-id form.",
    )
    parser.add_argument(
        "--as-of",
        help="ISO-8601 reader timestamp; defaults to the current UTC instant.",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=2,
        help="Relationship traversal depth for graph-parity (default: 2).",
    )
    parser.add_argument("--limit", type=int, default=500)
    args = parser.parse_args()
    commands = {
        "docs": lambda: docs(check=False),
        "docs-check": lambda: docs(check=True),
        "db-check": db_check,
        "db-backup": db_backup,
        "repair-dry-run": lambda: repair_dry_run(args.operation or [], args.limit),
        "graph-parity": lambda: graph_parity(
            args.seed or [], args.as_of, args.max_depth
        ),
        "health": health,
        "changes": changes,
        "tasks": task_summary,
        "review": review,
        "codex-hooks-check": codex_hooks_check,
        "codex-check": codex_check,
        "check": run_checks,
        "verify": verify,
    }
    return commands[args.command]()


if __name__ == "__main__":
    raise SystemExit(main())
