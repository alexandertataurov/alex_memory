# AM-073 — Classification Contract and Selective Reclassification

## Objective

Make deterministic message classification truthful, versioned, multilingual-aware,
and safe for semantic-work routing without modifying raw evidence.

## State transition

Classifier v1 persisted wall-clock age labels, forced forwarded messages to
external-news scope, classified actionable questions too early, and relied on
English-only phrases. Classifier v2 stores only source-time-stable date presence,
separates provenance from scope, classifies operational semantics before generic
questions, and uses bounded English/Russian/Georgian signals.

`message_classifications` is rebuildable derived state sourced from current raw
messages and bounded local context. The existing version-aware queue selectively
revisits unknown, stale, high-value, forwarded, and actionable-question v1 rows
without provider calls. Approved manual classification reviews are excluded.

## Constraints and decisions

- Raw evidence, accepted observations, feedback, pins, and manual authority are
  unchanged.
- No schema migration or live backfill was needed. AM-074 remains responsible
  for a separately authorized live repair command.
- Context signals use source date/message-ID order and do not look ahead to
  reclassification-time state.

## Validation

- Hand-reviewed fixture: 7/7 English/Russian/Georgian operational cases correct,
  with zero unknown scopes.
- Tests cover request/promise/decision/payment/meeting routing, forwarded private
  evidence versus news, private groups, source-time context, as-of age,
  selective reclassification, and manual-review preservation.
- 38 focused history/workflow/review/migration tests, Ruff, MyPy, generated docs,
  task-queue validation, and read-only database checks pass.

## Final outcome

Completed 2026-08-24. The normal bounded classification queue is the repeatable,
provider-free repair path; no production classifications were changed.
