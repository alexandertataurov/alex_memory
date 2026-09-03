# AM-124 — Bounded Shared Connections

## Control-plane status

This ExecPlan is a synchronized repository mirror. Notion controls this task's
scope, status, dependencies, gates, authorization, and completion; this plan
cannot authorize a subsequent AM-124 increment.

## Objective

For two canonical person/company/project endpoints, return the current shared
canonical entities reachable as `A -> C <- B`, with each independent,
authoritative leg's exact provenance.

## Contract

- Exactly two hops; query at most 80 authoritative one-hop edges per endpoint
  and return at most 20 deduplicated `(entity_type, canonical_id)` results.
- Use only `current_authoritative_edges`; exclude endpoints A and B, legacy
  compatibility rows, observed/non-current/confidence-only/source-less
  automatic material, and all graph writes.
- Both legs must be valid at the same canonical UTC `as_of`. Aware timestamps
  normalize through the existing temporal contract; naive datetimes fail.
- Manual legs remain manual; automatic legs retain claim evidence or an already
  allowed historical-event source-message locator. No scores or ranking: stable
  presentation ordering is newest leg time, entity type, then entity ID.

## Scope and verification

Expose one reusable read-only result model only; no graph UI or Person Profile
change. Cover shared/deduplicated identity, manual-plus-automatic provenance,
authority exclusions, temporal overlap and UTC equivalence, compatibility
exclusion, deterministic limits, and no writes with temporary SQLite fixtures.
No migration, conversion, replay, repair, backfill, or live action is allowed.

## Progress

- 2026-09-03: implemented `shared_authoritative_connections()` as an
  intersection of two independently bounded `current_authoritative_edges()`
  reads. It returns the two original edge records for evidence/authority
  closure, deduplicates typed canonical endpoints, excludes inputs, normalizes
  aware `as_of` to UTC, and performs no writes. No product UI was added.

## Final outcome

- 2026-09-03: accepted and closed by owner. This bounded V1 is the final
  authorized AM-124 increment. The full repository gate passed: 373 tests,
  Ruff, formatting, MyPy, docs, lock/dependency/vulnerability, and SQLite
  checks. No remaining acceptance gate exists, and no further AM-124 work is
  authorized.
