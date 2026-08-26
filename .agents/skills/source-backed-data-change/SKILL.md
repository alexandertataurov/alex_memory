---
name: source-backed-data-change
description: Plan or implement Alex Memory database migrations, backfills, FTS repair, or derived-state rebuilds while preserving source evidence and manual authority.
---

Use this skill for schema, migration, repair, or rebuild work that can affect
SQLite-backed canonical or materialized state.

1. Read `AGENTS.md`, `TASKS.md`, `docs/DATA_MODEL.md`, and
   `docs/DATABASE_MIGRATIONS.md`; inspect the schema, migration registry, and
   existing tests before editing.
2. Create or update an ExecPlan for a migration, backfill, broad repair, or
   table rebuild. Define the authoritative inputs, derived outputs, rollback
   path, bounded work units, and idempotency requirement.
3. Keep raw `messages`, source-evidence versions, accepted AI evidence, manual
   feedback, pins, and manual task locks immutable. Prefer additive, ordered,
   idempotent migrations. A live-data migration or table rebuild requires
   `make db-backup` first; fixture tests never use the live database.
4. State whether every affected table is authoritative, canonical, or
   rebuildable. Do not use a derived table as evidence when its source is
   available.
5. Add focused migration, restart/resume, source-parity, and repeat-run tests.
   Verify with `make db-check` and the relevant search/retrieval behavior.

Report the migration version (or explicitly say none), preserved evidence,
rebuild inputs, test coverage, and any operational follow-up.
