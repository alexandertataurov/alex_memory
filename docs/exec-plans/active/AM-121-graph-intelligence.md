# AM-121 — Bounded Graph Intelligence

## Objective

Make accepted/manual graph context available to entity-scoped People and
Project intelligence without changing the compatibility relationship reader or
turning graph traversal into ranking, inference, or canonical mutation.

## Current and target state

`current_authoritative_edges()` already returns a bounded, temporal,
authority-filtered one-hop graph result. `retrieve_related()` instead reads
only direct task, observation, event, and fact columns, so an entity-scoped
intelligence result cannot presently surface an accepted graph connection.

The first increment adds a read-only graph-context result to
`retrieve_related()` for person, company, and project scopes. Every automatic
result must retain exact claim evidence; the historical-event path must retain
its exact source-message locator; a manual edge must stay explicitly manual
without fabricated AI provenance. No ContextBuilder caller changes in this
plan.

## Constraints

- Query only `current_authoritative_edges()` at a canonical UTC `as_of`, under
  an explicit bounded limit.
- Exclude observed, rejected, superseded, expired, confidence-only, and
  source-less automatic graph rows.
- Preserve `retrieve_related(..., as_of=...)` historical behavior: no current
  materialization may appear as historical truth.
- Resolve only the opposite canonical endpoint and a deterministic exact
  citation; do not use lexical matching, graph ranking, score promotion, or
  recursive traversal.
- Preserve manual authority as manual and do not invent claim evidence.
- Do not change `ContextBuilder`, `relationships`, graph projection,
  migrations, backfill, replay, or live state.

## Implementation sequence

1. Trace `retrieve_related()` callers and its result/citation rendering.
2. Add a focused helper that maps the existing authoritative one-hop edge to a
   bounded `SearchResult` with endpoint identity, relationship semantics,
   authority label, temporal date, and exact evidence locator when present.
3. Invoke it only for person/company/project scopes, at a fixed bounded share
   of the existing related-result budget.
4. Add temporary-SQLite regressions for accepted claim-backed edges,
   source-message-backed historical events, manual edges, observed/expired
   exclusion, endpoint directionality, temporal `as_of`, and no graph-result
   leakage into a task scope.
5. Update product/architecture docs and task evidence. Run focused and full
   quality checks before considering a later product/UI increment.

## Completion evidence

- Entity-scoped retrieval returns only current accepted/manual one-hop graph
  context and gives each automatic result an exact citation.
- Historical calls include only edges valid at that instant and omit mutable
  materializations.
- No graph query writes database state and no compatibility reader changes.
- Focused synthetic regressions and the repository quality gate pass.

## Explicitly deferred

- ContextBuilder cutover from `relationships`.
- Multi-hop traversal, scoring/ranking, recommendations, graph UI, and graph
  discovery expansion.
- Any migration, conversion, replay, repair, or live operation.

## Progress

- 2026-09-02: `retrieve_related()` now consumes the existing bounded
  `current_authoritative_edges()` contract for person/company/project scopes.
  It emits only one-hop accepted/manual connections, resolves the opposite
  canonical endpoint, and retains a deterministic exact citation for automatic
  claim-backed or historical-event edges. Manual rows stay provenance-honest;
  observed rows remain absent. No ContextBuilder caller, schema, graph writer,
  compatibility-reader, or live state changed.
- 2026-09-02: Company and Project profile rendering now consumes that same
  shared one-hop query, showing endpoint, authority-labelled relationship, and
  provenance. The helper remains a bounded read-only primitive rather than a
  second graph implementation.
- 2026-09-02: automatic-connection coverage now verifies the exact claim
  evidence locator that the retrieval result exposes, alongside manual and
  observed-edge exclusion coverage.
- 2026-09-02: Company and Project profiles now include a bounded canonical
  event timeline only where the event retains an exact source-message locator.
