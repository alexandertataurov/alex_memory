# Database Migrations

Alex Memory tracks applied SQLite schema changes in `schema_migrations`. Each
entry has an integer version, a stable migration name, and an application time.
Run `make db-check` to see the active schema version without inspecting tables.

## Current sequence

1. `bootstrap_schema` creates only the stable baseline table set idempotently.
2. `compatibility_columns` applies its fixed pre-ledger compatibility snapshot.
3. `fts_indexes` creates optional FTS5 indexes and triggers; normal SQL fallback remains available when FTS5 is unavailable.
4. `source_neutral_evidence` adds source/account/conversation/item evidence records and version history for future ingestors.
5. `intelligence_coverage` adds resumable message-classification coverage state.
6. `context_conflict_review` adds source-backed proposed temporal observations and an append-only manual decision log.
7. `intelligence_versions` adds its fixed classification compatibility column,
   forward provenance, and selective message reclassification/re-analysis state.
8. `enforceable_chat_ai_policies` replaces inert lane-only chat-policy labels with automatic, include, exclude, classification-only, and news-only routing modes. Existing `daily_only` and `history_only` values become `auto`.
9. `conversation_segments` adds derived, time-bounded project conversation periods.
10. `conversation_intelligence` adds materialized person and conversation context without modifying source evidence.
11. `ai_routing_usage` adds aggregate daily model usage and recent routing outcomes. It contains no prompt text, raw provider payloads, or credentials.
12. `fts_lifecycle_rebuild` atomically rebuilds optional FTS5 indexes from
   current authoritative rows and installs insert/update/delete maintenance
   triggers. FTS5 remains optional; a present but unhealthy table is a repair
   failure rather than an SQL-fallback case.
13. `extraction_lifecycle` adds exact AI-work membership, separately durable
    projection states, rejection diagnostics, and revisioned invalidation.
14. `semantic_claim_graph` adds immutable semantic claims with exact evidence,
    unresolved entity references, temporal graph tables, and claim-lineage
    columns. It does not convert historical observations during startup.
15. `graph_projection_lineage` links new compatibility observations to their
    immutable claim and adds per-claim graph-projection state. It does not
    convert historic observations or relationship rows during startup.
16. `person_profile_summary` adds a presentation-only cited summary to current
    person context. It does not enqueue, scan, or project historical evidence.
17. `person_profile_enrichment` adds profile-summary freshness and person scan
    metadata to durable job rows. It does not enqueue work during migration.
18. `profile_ai_lane` rebuilds only the durable `ai_jobs` table to add the
    isolated `profile` lane, preserving every existing job and exact job-message
    membership. It does not enqueue, scan, or project any history.
19. `profile_claim_metadata` adds nullable person scope, assertion kind, and
    effective-period metadata to immutable semantic claims for Deep Person
    Profile reads. It does not alter existing claims or enqueue work.

Existing installations that predate this ledger are adopted safely: their next
database open runs the idempotent sequence and records it. This is a baseline
record, not a claim that the historical versions were separately present.

The ordering, transaction, and ledger record are owned by `database.py`.
Declarative compatibility-column, source-evidence, and optional FTS support is
kept in `schema_support.py`; it is only invoked through named migrations.

## Adding a migration

1. Create a new, strictly increasing `Migration` in `src/alex_memory/database.py`.
2. Make it safe to retry after an interrupted open. Do not alter old migration behavior.
3. For any change that rewrites data, drops/rebuilds a table, or changes a key,
   run `make db-backup` before applying it and document the recovery path.
4. Add fresh- and legacy-database tests, run `make db-check`, and regenerate docs.

FTS rebuilds never modify raw messages or canonical records. Before a live open
applies migration 12, create a SQLite API backup with `make db-backup`. The
migration opens one explicit SQLite transaction around the old-index drop, new
index/trigger creation, source backfill, parity check, and ledger record; a
failure rolls back to the prior derived state.

SQLite does not provide a general rollback mechanism for arbitrary schema
changes. Recovery is restoring the SQLite API backup after stopping the process
that owns the live database; do not copy a WAL database file directly.
