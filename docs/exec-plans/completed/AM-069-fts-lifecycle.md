# AM-069 — FTS Lifecycle and Coverage Repair

## Objective

Repair optional SQLite FTS5 indexes so every active index is rebuilt from its
authoritative source, maintained on mutable-source changes, and never masks a
broken schema or query as unavailable FTS capability.

## Current and target state

Current FTS tables were populated only by insert triggers. Existing source rows
were not backfilled, updates/deletes left stale rows, and broad
`sqlite3.OperationalError` handling silently changed defective FTS searches
into LIKE searches.

The completed migration atomically rebuilds all FTS tables from their
authoritative sources and replaces the triggers with full insert/update/delete
synchronization. FTS5 capability is explicit; only an absent module enables SQL
fallback. Other database/index/query failures remain visible. Diagnostics
compare each authoritative source with its derived index and health fails when
an available index is unhealthy.

## Constraints

- Raw messages, message versions, source evidence, accepted AI observations,
  canonical entities/tasks, feedback, pins, and manual locks remain unchanged.
- The six FTS tables are rebuildable derived state only, sourced from current
  non-deleted, non-empty content.
- Migration 12 is ordered, atomic, idempotent, and requires a SQLite API backup
  before a live application applies it.

## Affected areas

`schema_support.py`, `database.py`, retrieval and Task Deep Dive fallback
boundaries, safe developer health diagnostics, migration/search/deep-dive tests,
and database documentation.

## Implementation sequence

1. Added explicit FTS5 capability detection and source/index contracts.
2. Registered migration 12, which recreates/repopulates the six derived tables
   and their mutation triggers transactionally.
3. Restricted fallback to truly absent FTS5 capability and surfaced all other
   SQL/index errors.
4. Added metadata-only coverage diagnostics to health and database checks.
5. Added fresh/legacy backfill, mutation, entity-merge, unavailable-capability,
   drift, and broken-index tests.

## Risks and decisions

- FTS virtual tables are safely dropped/recreated because they are derived; the
  surrounding migration transaction preserves the prior state on failure.
- FTS5 absence is optional capability, not index-health failure. A present
  module plus a missing/corrupt table is a failure requiring repair.
- Search retains deterministic SQL stages. Deep Dive uses LIKE only when FTS5
  is unavailable, not for zero FTS hits or defects.

## Validation

- Focused FTS coverage: 23 passing migration, retrieval, and Task Deep Dive
  tests.
- Ruff, formatting, MyPy, `make docs-check`, and `make db-check` pass.
- Read-only live verification: schema 12, SQLite integrity `ok`, no foreign-key
  violations, and exact parity across all six FTS indexes.
- `make check` was not considered a pass: it stalled in the existing Gemini
  pacing test before FTS tests ran and was interrupted.

## Final outcome

Completed 2026-08-24. Migration 12 changes only rebuildable derived FTS state;
the live database had already been migrated after its documented API backup, so
this implementation performed read-only parity verification rather than another
live rebuild. Follow up separately on the stalled Gemini pacing test.
