# AM-055 — Durable Background Intelligence Scheduling

## Objective

Replace dropped interval callbacks with one bounded scheduler that treats
durable message/job state as the source of pending work, gives live freshness
priority over history, and keeps Telegram ingestion independent from providers.

## Current and target state

`TelegramSyncService` separately starts periodic AI and history callbacks. The
daily callback is discarded when `analysis_lock` is held; history independently
infers eligibility from queue and callback flags. The target scheduler owns
that decision and treats existing durable evidence and `ai_jobs` as the restart
source of truth, using in-memory signals only to wake it.

## Constraints

- Provider work must never block Telegram writer persistence.
- Preserve bounded batches, single job claims, cancellation-safe release, and
  live-before-history priority.
- No migration/backfill unless the existing job contract proves insufficient.
- Use temporary databases and fakes only.

## Implementation sequence

1. Trace writer commit, durable job creation/claim/release, callback, failure,
   restart, and shutdown paths with synthetic tests.
2. Define one scheduler ownership boundary with bounded wake signals and a
   durable work recheck before dispatch.
3. Coalesce live triggers with short and maximum-delay bounds; history yields
   whenever live durable work exists.
4. Test busy-lock, burst, idle, maximum-delay, restart, provider-failure,
   cancellation, and priority paths.

## Risks and decisions

- In-memory wakeups are not durable work; messages/classifications/jobs retain
  restart truth.
- The scheduler must not duplicate repository batching, claims, or retries.

## Validation plan

Use synthetic clocks, queues, temporary SQLite databases, and fakes; then run
focused async/AI tests, static checks, docs/task checks, and read-only DB
integrity checks.

## Progress and discoveries

- 2026-08-24: confirmed the trigger-loss path. `ensure_daily_jobs()` creates
  bounded durable jobs only when invoked, so the scheduler must wake after
  committed messages and recheck durable eligibility at startup.
- 2026-08-24: implemented `BackgroundIntelligenceScheduler` as the sole
  automatic Daily/History owner. The writer invokes its wake signal only after
  a commit; durable messages and `ai_jobs` remain restart truth. History checks
  the writer and durable Daily jobs before each provider request. No migration
  was needed.

## Final outcome

Completed 2026-08-24. Automatic Daily and optional History work now has one
bounded owner; it coalesces committed-message wakeups, rechecks durable state
at startup and on the configured maximum delay, and retains live-over-History
priority. The existing `ai_jobs` and source messages supply retry and restart
truth, so no schema transition was required. Context invalidation remains the
separate durable-state concern scoped to AM-053.

Verification passed: focused temporary-SQLite scheduler/writer/history tests,
the full 151-test `make check` gate, generated-doc checks, and read-only SQLite
integrity/foreign-key/FTS checks.
