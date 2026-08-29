# AM-072 — Project health

## Objective

Derive project health from source-backed operational activity, rather than
treating missing task links as a critical condition.

## Current increment

The health projection reads the latest timestamp from canonical task evidence,
project-linked AI observations, temporal context events, and conversation
segments. A project is `critical` only for a real overdue open or waiting task;
no activity is `stale`, recent activity is `active`, and current waiting tasks
retain `waiting`. Existing `completed` and `archived` states are not rewritten.

## Constraints and validation

This changes derived `projects` health fields only. Raw evidence, task state,
manual state, and project identity remain unchanged. Temporary-SQLite fixtures
prove recent non-task activity, stale no-evidence state, and overdue critical
state. No migration, backfill, or live recomputation is authorized; a safe
repair command remains AM-074 work.

## Final outcome — 2026-08-29

The projection preserves explicit `completed` and `archived` project states,
alongside its covered active, waiting, stale, and evidence-backed critical
outcomes. Tests run only on temporary SQLite databases. No migration, backfill,
or live recomputation ran; AM-074 remains the only repair path.
