# AM-053 — Context dirty queue

## Objective

Move derived context refresh out of canonical batch projection into durable,
coalesced, revision-aware invalidation work.

## Current and target state

Batch projection currently performs segments, graph work, contact refresh,
global snapshots, and operational refresh synchronously. Existing stale flags
do not identify an owned scope or survive a targeted refresh contract.

## Constraints

Raw messages, accepted observations, manual decisions, locks, pins, and
canonical task state remain unchanged. The ledger is additive and migration-led.
Workers must be bounded, restart-safe, and failure-isolated.

## Design

Each record identifies one affected scope and revision. New invalidation for the
same scope coalesces without allowing an older worker to clear newer work.
Canonical projection only records invalidation; named derived writers consume
it selectively and commit completion only for the revision they processed.

## Validation

Use temporary databases for migration, coalescing, restart, revision race,
targeted refresh, failure retry, and no-op projection cases. Verify integrity
and repeat execution before any operator-run maintenance.

## Progress

- 2026-08-28: explicit terminal operational refresh now requests and drains the
  `global` invalidation scope rather than bypassing the ledger with direct
  follow-up/project-health calls. Fixture coverage proves its revision reaches
  clean only after the global snapshot/operational projection worker succeeds.

## Final outcome

Completed 2026-08-28. Canonical projection remains transactional and only
records scoped invalidations. The bounded worker owns conversation, person, and
global materialization; the global path includes snapshot, project-health, and
follow-up projections. Coalescing, restart persistence, failure retry, revision
races, and non-global isolation are covered by temporary-SQLite tests. Project,
company, and task scopes retain their durable invalidation records for future
separate materializers; no unowned runtime writer bypasses the global contract.
No migration, backfill, or live operation ran.
