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
