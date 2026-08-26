# AM-070 — Task-project links

## Outcome

Completed 2026-08-24. Task projection uses bounded deterministic project
candidates, preserves established links, queues weaker candidates for review,
and provides idempotent selective repair. No migration or live action occurred.

## Validation

Temporary-database coverage includes exact-message linking, review candidates,
link authority, bounded repeat repair, conversation periods, and Deep Dive
readers. `make check` passed 172 tests; documentation, task, and database
integrity checks passed.
