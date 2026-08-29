# AM-056 — Candidate-only cross-chat graph discovery

## Objective

Identify bounded, source-backed cross-chat relationship candidates that local
deterministic graph repair cannot prove, without changing canonical entities,
relationships, tasks, facts, or source evidence. Candidates must enter the
existing Review queue and can affect canonical graph state only through its
existing manual acceptance path.

## Current state

`ContextGraphImprover` can create a `graph_link` review item only from a local
same-chat project consensus. The semantic graph records accepted/manual and
observed claim-derived edges, while `relationships` remains the compatibility
reader. Neither is a safe target for automatic candidate discovery.

## Design

1. Select a bounded set of already accepted canonical entity anchors and their
   exact source evidence; do not scan raw archive text without those anchors.
2. Use deterministic overlap and temporal/source evidence to create only a
   candidate payload describing the two endpoints, proposed relationship,
   confidence, exact message references, and selection reason.
3. Deduplicate candidates through the existing `review_queue`; a second run
   must create no duplicate review item.
4. Keep ambiguous, weak lexical, expired, and already-accepted relationships
   out of candidate output. Provider failure must leave archive and canonical
   state unchanged.
5. Reuse `resolve_review_item()` for the only acceptance path; do not add a
   second graph writer, a historical conversion, or a live maintenance pass.

## Scope and constraints

- Source evidence remains immutable and every candidate retains exact message
  provenance.
- Candidate selection is bounded by SQL limits and deterministic time windows.
- No model prompt, provider call, schema migration, replay, backfill, graph
  repair, or live operation is part of the first increment unless source
  inspection proves one is required.
- AM-120 compatibility readers remain on `relationships`; candidates do not
  grant accepted-graph reader authority.

## Validation

- Synthetic true cross-chat candidate with exact source references.
- False lexical overlap, ambiguous identity, and expired evidence are rejected.
- Repeated selection is idempotent and cannot mutate canonical state.
- Existing Review acceptance remains the only path that creates a manual graph
  edge and its temporal validity.

## Outcome

Completed 2026-08-29. `ContextGraphImprover.discover_cross_chat_candidates()`
selects at most 80 Review-only candidates from validated `ai_items` with exact,
non-deleted source messages, a shared resolved person, distinct chats, and a
90-day evidence interval. It rejects reviewed, untraceable, stale, and already
linked records; candidate payloads include confidence, endpoints, exact anchor
references, and reasons. The terminal Context Graph operation exposes this as
an explicit `discover` action. Existing `graph_link` Review acceptance remains
the sole canonical/manual graph mutation path. No model call, migration,
backfill, replay, repair, or live operation ran.
