# AM-088 — Conversation open-loop lifecycle

## Objective

Make task-backed conversation loops an exact, bounded projection of canonical
open/waiting tasks. Keep heuristic questions explicitly low-confidence derived
state, resolve them only on adjacent substantive replies, and age them out of
current context without erasing history.

## Current and target state

The materializer selects only open/waiting tasks and upserts their loops. It
never removes a previously projected task loop when its task becomes done or
canceled. Its question pass scans 120 messages but may resolve the latest
opposite-author question using a later weak token.

Target: each refreshed conversation first removes task loops no longer backed
by an active canonical task, then projects its bounded current task set.
Question loops stay separate (`loop_type='question'`, confidence 0.6), resolve
only through an immediate opposite-author reply with substantive support, and
become resolved after the current-window age threshold while remaining stored
for history.

## Constraints

- Do not rewrite source evidence, accepted observations, canonical tasks,
  manual state, pins, or notes.
- Do not migrate, replay, or touch production data. Normal refresh may only
  maintain its own derived conversation-loop rows.
- Keep every scan and mutation scoped to one person/conversation and bounded.
- A heuristic question must never gain canonical-task authority.

## Sequence and validation

1. Remove stale task-derived loops before projecting active canonical tasks.
2. Replace stack-like weak-token matching with adjacent, direction-aware,
   substantive-reply matching.
3. Resolve aged question loops without deleting their history.
4. Prove done/canceled cleanup, idempotent refresh, weak/unrelated replies,
   valid adjacent replies, bounded-window behavior, and historical aging.

## Outcome

Completed 2026-08-28. Task loops now project only scoped canonical
open/waiting tasks, removing stale, completed, canceled, and orphaned derived
rows during refresh. Question loops remain low-confidence derived state,
resolve only through an adjacent substantive opposite-author reply, and age to
resolved history after 90 days.
