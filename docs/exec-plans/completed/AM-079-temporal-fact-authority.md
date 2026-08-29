# AM-079 — Temporal fact authority

## Objective

Remove keyword and suffix-driven state projection so a predicate name cannot
silently grant authority to replace temporal canonical state.

## Current and target state

`ContextService` previously projected broad task and document heuristics into
facts, and `set_temporal_fact()` treated any predicate ending in `_status`,
`_state`, or `_progress` as automatically replaceable. Those generic writers
could convert ordinary observations into false project or person state.

Target: there is no automatic temporal-fact projection from accepted AI items.
The repository remains a temporal storage and Review primitive: changed values
create a Review conflict by default, and an explicit deterministic projector or
already-authoritative manual flow must opt into `conflict_policy="replace"`.

## Constraints

- Do not migrate, replay, delete, or alter existing fact history.
- Never use a predicate's spelling as an authority or conflict rule.
- Keep historical intervals closed instead of overwriting facts.
- Keep duplicate source observations idempotent and reject stale Review
  decisions before they can create a second current fact.

## Sequence and validation

1. Remove broad task/document fact projection from `ContextService`.
2. Replace suffix semantics with explicit replacement policy at the repository
   boundary.
3. Deduplicate an exact pending conflict replay only when it carries durable
   source identity.
4. Re-read the current predicate timeline inside the conflict-resolution
   transaction before accepting a proposed value.
5. Prove status-suffixed predicates default to Review, explicit replacement
   preserves history, duplicate replay is idempotent, and stale resolution is
   rejected.

## Outcome

Completed 2026-08-29. There are no automatic temporal-fact projectors in the
accepted-item path. Changed facts now default to Review regardless of predicate
name; replacement is an explicit call-site policy. Exact source replays do not
duplicate a pending conflict, and acceptance revalidates current state in its
transaction. No migration, backfill, replay, deletion, or live operation ran.
