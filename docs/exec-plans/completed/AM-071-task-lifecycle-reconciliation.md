# AM-071 — Task lifecycle reconciliation

## Objective

Make automatic task reconciliation conservative enough that unrelated work in a
long-lived chat cannot merge merely because its title is similar, while retaining
exact evidence and manual lifecycle authority.

## Current increment

The first bounded increment tightens candidate selection only. It must reject a
candidate with a conflicting known person, company, or project anchor, and must
not let `NULL` act as an entity wildcard. Exact-title continuation with an
unconflicted anchor remains supported. Manual task changes and rejection already
share `manually_update_task()`; fixtures must retain that one event path plus the
separate rejection feedback record.

## Constraints

- `ai_items` and source messages remain immutable; this changes only future
  canonical projection.
- Manual status locks dominate automatic updates.
- Terminal AI items with no safe candidate continue to Review; no historical
  completion backfill, replay, migration, or live operation is authorized.
- SQL remains chat-scoped and bounded; matching is deterministic and
  conservative.

## Affected boundary

`process_ai_batch()` resolves source-backed observations, then
`TaskReconciler.process_item()` chooses or creates one canonical `tasks` row and
writes a replay-safe `task_events` record. Terminal items without a safe match
are `task_completion` Review items. `reject_task()` records user feedback only
after its shared manual lifecycle mutation succeeds.

## Validation

- Synthetic temporary-SQLite same-chat, same-title tasks with conflicting
  person/company/project anchors do not merge.
- A matching anchor still permits an exact-title terminal update.
- Unanchored similar titles remain separate.
- Manual rejection has exactly one manual lifecycle event and one feedback
  record.

## Follow-up increments

Historical reconciliation/backfill is AM-074 work. It requires its own
dry-run, resume, idempotency fixtures, and operator authorization before any
live action.

## Progress

- 2026-08-27: candidate queries now select at most 50 same-chat active rows;
  conflicting populated person/company/project anchors are excluded before
  similarity ranking. Matching known anchors remain preferred, while a sparse
  historical row requires an exact normalized title. Temporary-SQLite fixtures
  prove conflict prevention, supported anchored completion, existing
  unanchored behavior, and shared manual rejection audit behavior. No schema,
  replay, backfill, or live action ran.
- 2026-08-27: fuzzy candidates now require the same task kind and source dates
  no more than 180 days apart; exact normalized titles retain long-running
  lifecycle continuity. Repeated manual actions and task rejection are
  idempotent. Cancellation linkage is fixture-tested. This completes AM-071's
  code-verifiable lifecycle scope; no historical repair was run.
