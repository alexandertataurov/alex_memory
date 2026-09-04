# AM-129 — Contact reconciliation workflow

## Control-plane status

This ExecPlan mirrors the Notion-authorized AM-129 leaf. Notion controls its
scope, status, gates, and completion. The plan does not authorize a live
identity mutation.

## Objective

Expose one bounded workflow for reviewing ambiguous person-identity candidates
and explicitly linking an alias, merging confirmed duplicates, separating a
candidate, or leaving it unresolved.

## Current and target state

`entity_merge` review records already retain candidate IDs, exact alias/reason,
and durable manual feedback. `resolve_review_item()` can perform a merge, but
the terminal asks directly for a keep ID and offers no preview or explicit
separate/link-alias decision.

The target is a preview-first command surface over those existing records. It
must show bounded candidate/evidence metadata before every action, persist an
auditable manual decision, and provide no bulk or automatic reconciliation.

## Constraints and safety boundary

- Raw evidence, claims, temporal facts, and manual authority remain intact.
- Preview is read-only. Apply requires an explicit action and existing
  confirmation path; no live command is run during development.
- Link alias and merge reject conflicting/manual ownership; separate and
  unresolved decisions do not mutate canonical identity links.
- No schema migration, live repair, replay, backfill, provider work, or broad
  identity redesign is permitted.

## Implementation sequence

1. Add a bounded candidate preview/read model with aliases, candidate IDs,
   direct-account identifiers, and review rationale only.
2. Add explicit manual reconciliation actions backed by durable review feedback:
   link a non-conflicting alias, merge via the existing merge primitive, mark
   separate, or leave unresolved.
3. Wire the existing review UI/command path to preview before apply and preserve
   its confirmation boundary.
4. Cover preview, alias conflict/manual authority, merge, separate, unresolved,
   and no-write preview in temporary SQLite.

## Validation and rollback

Run targeted reconciliation tests during implementation and `make verify` for
the Risky completion gate. Do not run a live apply. Rollback is code-only prior
to any owner-approved apply; completed manual actions remain auditable feedback
rather than being silently reversed.

## Final outcome

Implemented the bounded preview-first reconciliation path. An `entity_merge`
review shows candidate identifiers, aliases, and rationale before a confirmed
operator action. Explicit merge, alias link, separate, and unresolved choices
all retain durable manual feedback. Alias links are restricted to reviewed
candidates and reject both external and conflicting manual ownership. No schema
migration, bulk operation, replay, backfill, or live identity action ran.

Verification: focused app/operational tests passed (58 tests, 2 subtests), and
`make verify` passed: 418 tests plus lint, formatting, type, docs, dependency,
SQLite integrity, and FTS checks.
