# Technical Debt

## Normal

### TD-002 — Large core modules

- Component: AI repository, database, UI, Telegram worker
- Problem: Several modules exceed 500 lines and need deliberate responsibility review.
- Impact: Higher change and review cost.
- Recommended fix: AM-036 should use `make review` findings to extract only cohesive review, repository, context, and terminal-screen behavior behind tested boundaries.

### TD-006 — Context invalidation consolidation

- Component: Context
- Problem: Accepted canonical projection now records scoped revisions in
  `context_invalidations`, and the refresh worker prevents an older run from
  clearing a newer revision. The remaining debt is to finish moving the
  still-open project/company/global materializations onto that same bounded
  ownership contract.
- Impact: Those remaining materializations can still have less precise refresh
  scope than person context.
- Recommended fix: Complete AM-053's writer/caller inventory and migrate only
  the proven remaining materializations to the existing ledger.

### TD-007 — Semantic graph compatibility cutover

- Component: Context graph and chat AI policy
- Problem: Chat AI policy modes are enforceable. The remaining risk is that
  active compatibility readers/writers still depend on `relationships`, while
  automatic semantic-graph acceptance currently covers task-to-project only.
- Impact: Moving consumers before graph-query and authority parity would drop
  supported relationship types or over-authorize automatic links.
- Recommended fix: Follow AM-120's caller inventory: establish bounded query
  parity and explicit projection authority before migrating one consumer at a
  time; retain Review for ambiguous historical links.

## Low

### TD-004 — Host service supervision

- Component: Operations
- Problem: There is no checked-in systemd/service definition for daemon supervision.
- Impact: Long-running sync deployment is manual.
- Recommended fix: Add a documented, environment-specific unit only when deployment ownership and paths are agreed.
