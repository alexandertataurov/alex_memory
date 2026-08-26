# AM-054 — Authoritative Runtime Status

## Objective

Replace fragmented, object-existence-based live-health displays with one
read-only runtime-status service. It must distinguish a working Telegram sync
from failed startup, supervised retry, a dead writer, and ordinary offline
operation, while reporting bounded freshness and data-quality signals.

## Current and target state

`AlexMemoryApp.start()` retains `live_sync` when `TelegramSyncService.start()`
raises. The home panel then infers availability from that object and renders
`RECOVERING`; the startup notice incorrectly promises a retry even though the
initial-start failure never registers the periodic retry worker. The status
screen separately recomputes a subset of database metrics and has no runtime
state.

The target has a single snapshot builder that combines explicit live lifecycle
state with bounded, read-only SQLite telemetry. The home and status screens
render that snapshot. Initial-start failure is `FAILED`; `RETRYING` is used
only while the sync service has a periodic supervised recovery path.

## Constraints

- No schema migration, backfill, or live database write: all health and quality
  measures are read-only derived observations.
- Do not expose raw Telegram content, prompts, credentials, or provider error
  payloads; retain short bounded diagnostic labels only.
- A writer task failure must be visible even if the Telegram client remains
  connected.
- Preserve provider and Telegram failure isolation: status reporting cannot
  block persistence or claim partial work succeeded.

## Affected areas

`telegram/live.py`, `models.py`, a focused runtime-status module, the app
startup/menu paths, terminal navigation/status rendering, focused tests, and
the architecture/quality documentation and change records.

## Implementation sequence

1. Add explicit live lifecycle state and reserve supervised retry for the
   already-running periodic reconciliation worker; startup failure remains
   failed until an operator retries it.
2. Implement bounded read-only runtime, freshness, AI, graph, review, and
   data-quality snapshot queries.
3. Route app home/status rendering through the one snapshot and remove the
   duplicated object-presence health projection.
4. Add synthetic-database and fake-live-service coverage for normal,
   processing, behind, startup-failed, retrying, rate-limited, offline,
   quality-warning, writer-crash, and fatal snapshots.
5. Run focused and project quality gates; record no-migration outcome.

## Risks and decisions

- The status service is intentionally a narrow read model, not a new scheduler
  or persistence layer. It owns no retry policy and writes no state.
- Archive lag derives from the newest stored message timestamp; it is an
  indicator, not proof Telegram has no newer message.
- `context_stale` classifications and `analysis_stale` state are the existing
  durable dirty-work signals; their minimum source date supplies oldest age.
- A completed writer task with an exception is fatal even before its exception
  is propagated elsewhere.

## Validation plan

Use temporary databases and synthetic `LiveSyncState`/writer tasks. Exercise
the listed task snapshots, then verify both home and full status rendering use
the service. Run focused tests, Ruff, formatting, MyPy, docs/task checks, and
the read-only database check. Do not authenticate or modify production data.

## Progress and discoveries

- 2026-08-24: traced `AlexMemoryApp.start()`, `TelegramSyncService`, writer,
  home panel, status screen, AI route telemetry, history coverage, FTS health,
  and graph diagnostics. The reported startup-object inference is confirmed.

## Final outcome

- Completed 2026-08-24. `RuntimeStatusService` now owns one read-only snapshot
  for the home and diagnostics screens. It exposes explicit Telegram lifecycle,
  archive lag, writer failure, AI work/current route/quota cooldown, stale
  context age, graph/review/history state, bounded recent errors, and the
  requested quality ratios.
- `TelegramSyncService` marks failed startup explicitly and reports retrying
  only after periodic reconciliation schedules recovery. No schema migration,
  backfill, derived-state rebuild, or live data action was performed.
- Validation: 22 focused runtime/UI/live-sync tests and 42 related deterministic
  tests passed; Ruff, format, MyPy, docs, task checks, review signals, and the
  read-only SQLite integrity/FTS check passed. The broader router suite was
  interrupted at the pre-existing Gemini pacing delay without a test failure.
