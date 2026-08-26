---
name: sqlite-integrity
description: Use when planning or verifying Alex Memory SQLite schema, migration, FTS, backfill, or derived-state work while preserving source evidence and manual authority.
---

# SQLite Integrity

Use this skill for SQLite schema changes, migrations, backfills, FTS work,
integrity repair, or materialized-state rebuilds.

First identify the authoritative source tables, each derived table, its single
writer, its rebuild contract, and all callers. Read `docs/DATA_MODEL.md`, the
migration ledger, `src/alex_memory/database.py`, and related tests. For a broad
migration, backfill, or rebuild, create or update an ExecPlan before editing.

Do not mutate raw evidence to repair a projection. Prefer additive,
ordered, idempotent migrations. Preserve manual corrections and validity
intervals. Make a migration transactionally safe, with source/derived parity
checks before recording it complete. Use temporary databases in tests; never
authenticate with Telegram or point a test at `data/telegram.sqlite`.

Before any explicitly authorized live schema action, require `make db-backup`.
For routine verification, use the read-only `make db-check`. Test fresh-schema,
legacy-upgrade, repeated-run, rollback/failure, foreign-key, and FTS parity
paths that apply. Report migration number, data impact, backup requirement,
and rebuild limits precisely.
