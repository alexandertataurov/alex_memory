# AM-087 contact materialization rebuild

## Objective

Recompute derived contact and conversation state only through the existing
`ContactContextMaterializer` after identity and freshness fixes. Source rows,
accepted observations, feedback, task locks, notes, and pins remain unchanged.

## Current state

`ContactContextMaterializer.refresh_person()` is the sole writer for contact
segments, conversation context, person-project context, open loops, and person
state. It has only scoped refresh entry points; there is no bounded coordinator
for rebuilding every eligible canonical person.

## Design

1. Add one explicit bounded coordinator that selects active canonical people in
   stable ID order and calls `refresh_person()`.
2. Return counts only; do not expose message content or create a second writer.
3. Keep invocation explicit and fixture-tested. This work adds no startup job,
   automatic execution, schema change, or live operation.
4. Prove a second run has no duplicate derived rows and preserves source and
   manual state.

## Outcome

Pending implementation and temporary-SQLite verification.
