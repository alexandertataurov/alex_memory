# Notion task — Normalize action lifecycle and derived action state

## Control-plane status

This is a synchronized implementation plan for Notion task
`3c7f52e9-545b-8178-91c0-f9a4efd80efa`. Notion controls its scope, status,
dependencies, and completion. The task is active and has no owner or operator
gate.

## Objective

Make canonical task workflow state exactly `open`, `waiting`, `blocked`,
`done`, or `canceled`. Keep `due_date` as a date field; derive stale age and
uncertainty separately in read models. Preserve the existing manual task-status
lock, and show/ordering action, waiting, blocked, and stale work in the
Overview and Actions presentation.

## Current evidence and boundary

- `tasks.status` currently has a SQLite CHECK constraint that excludes
  `blocked`; automatic reconciliation and manual updates likewise reject it.
- Person Profile already computes an `action_state`, but it returns only one
  mutually exclusive label. A waiting, old, uncertain task consequently loses
  its stale and uncertainty signals.
- Canonical tasks, not raw evidence or immutable observations, are the only
  persistence boundary changed. `task_events` retain their existing source and
  manual audit record. No replay, backfill, repair, or live maintenance action
  is part of this work.

## State transition and constraints

1. Migration 24 rebuilds only `tasks` to extend the CHECK constraint with
   `blocked`, preserving every row and index. It neither changes stored row
   values nor writes synthetic lifecycle history.
2. The bootstrap schema receives the same constraint. Fresh and upgraded
   temporary SQLite databases must converge at schema version 24.
3. The automatic reducer may project a validated `blocked` task observation;
   existing manual locks still send automatic changes to Review. Manual status
   updates accept all five canonical states and retain the existing audit event.
4. Readers treat `open`, `waiting`, and `blocked` as non-terminal canonical
   task state where they enumerate active work. Waiting-only reminders remain
   waiting-only; no new reminder or notification behavior is introduced.
5. Person Profile retains the bounded collections and returns separate
   workflow, due/scheduling, staleness, and certainty signals. Presentation
   order is deterministic and is not a ranking/recommendation score.

## Affected modules

- `database.py`: migration/bootstrapping only.
- `operational.py`, `classification.py`, `context/builder.py`,
  `intelligence.py`, and `ui/screens.py`: active-task reader or lifecycle
  boundaries, each changed only where blocked is active work.
- `person_profile.py` and `ui/textual_app.py`: bounded read model and existing
  Overview/Actions rendering.

## Validation

- Fresh and legacy temporary-SQLite migration fixtures accept `blocked` and
  preserve the original task rows and indexes.
- Automatic blocked projection works only for accepted source-backed input;
  a manual lock still prevents it.
- Manual blocked updates keep the manual lock and audit event.
- A single profile action can be waiting, stale, and uncertain at once, with
  deterministic action/waiting/blocked/stale presentation order and no write
  from the read model.
- Focused test modules, then `make verify`, documentation/task checks, and a
  caller/failure-path review pass before the Notion completion update.

## Out of scope

No raw-evidence, claim, graph, new writer, scheduler, follow-up,
notification, replay, backfill, repair, or live-database operation changes.

## Outcome

- 2026-09-03: completed the authorized lifecycle increment. Migration 24
  preserves task rows, source-claim lineage, manual locks, and indexes while
  extending the canonical CHECK constraint with `blocked`; the existing
  FTS-derived task index is rebuilt from authoritative rows because SQLite
  table replacement drops its triggers.
- Task extraction validation and the existing prompt accept `blocked` only for
  source-explicit external dependencies. Automatic reconciliation still defers
  to a manual lock through the existing Review path.
- Profile action records retain `workflow_state`, `is_scheduled`, `is_stale`,
  and `certainty` independently, then choose a deterministic display group for
  Overview/Actions. Focused temporary-SQLite tests prove migration preservation,
  manual authority, automatic blocked projection, orthogonal signals,
  deterministic ordering, and no read-model write.
- Full verification passed: 380 tests, Ruff, formatting, MyPy, docs,
  lock/dependency/vulnerability, and SQLite checks. The read-only local
  database remains at schema version 23; no live migration was run.
