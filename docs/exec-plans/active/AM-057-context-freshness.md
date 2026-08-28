# AM-057 — Dependency-scoped context freshness

## Objective

Make freshness reflect committed dependency coverage rather than refresh count
or a chat-wide stale flag. A deterministic graph/materialization change must
queue only its affected derived context and must not create unnecessary AI work.

## Current and target state

Graph improvement now writes revisioned canonical scopes instead of broadly
marking source messages stale. Runtime status reports archive, classification,
semantic, canonicalized, integrated, and conservatively current-enough
coverage. `ai_message_state.context_version_used` is still a global version and
cannot prove which individual scope an analysis depended on.

Target: persist the exact scope/revision membership used by each accepted batch,
then compute a message's current-enough state from those memberships and the
current invalidation ledger. Existing `ai_batch_invalidations` remains the
authoritative projection-side source; no prompt, provider, source evidence, or
canonical mutation path is added.

## Constraints

- Use a forward-only migration and temporary SQLite fixtures only.
- Preserve exact job message membership, immutable claim evidence, manual
  authority, and existing batch projection/retry semantics.
- Do not requeue an AI request for deterministic derived-context changes.
- Bound all coverage queries; no historical replay or live rebuild is part of
  this task.

## Implementation sequence

1. Add a narrow batch/message dependency table keyed by existing batch and
   invalidation scope/revision identifiers, populated transactionally from the
   accepted projection scopes.
2. Backfill nothing automatically: legacy rows remain explicitly partial until
   a separately authorized derived-state repair.
3. Make the coverage query compare stored memberships with the current scope
   revisions and label rows current-enough only when every dependency is clean
   at or beyond its recorded revision.
4. Test scoped graph changes, unrelated scope changes, restart-safe projection,
   and legacy partial coverage. Update runtime wording and task evidence.

## Risks and validation

The main risk is falsely treating a message as fresh when a relevant scope has
advanced, or falsely making unrelated corpus rows stale. Fixtures must prove
both directions. The migration must be idempotent and cannot mutate source,
claim, task, fact, or relationship rows.

## Progress

- 2026-08-28: graph changes enqueue affected revisioned scopes and runtime
  reporting distinguishes the lifecycle stages. Exact per-message dependency
  comparison remains unimplemented.
