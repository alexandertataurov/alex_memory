# AM-112 session reproducibility

Add explicit session parameters, exact selected-membership replacement, and
session-bound pin validation through an additive database change. Verify fresh
and upgrade fixtures, repeat updates, invalid pins, and session explanation.
No live operation is included.

## Outcome

Completed 2026-08-29. Migration 22 stores the investigation contract without
rewriting existing rows. Session updates replace exact membership and pins are
limited to task-owned selected evidence. No live migration, replay, or rebuild
ran.
