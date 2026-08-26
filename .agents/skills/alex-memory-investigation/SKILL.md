---
name: alex-memory-investigation
description: Debug, refactor, or measure Alex Memory behavior with a source-backed baseline, caller tracing, focused tests, and no speculative abstraction.
---

Use this skill for defects, refactors, performance investigations, or cleanup
that is more than a mechanical local edit.

1. Reproduce or measure the issue first. Trace the relevant entry point,
   callers, persistence boundary, and user-visible behavior before editing.
2. Write down competing hypotheses and falsify them with code, tests, SQL
   metadata, timing, or profiling evidence. Do not use random edits as
   debugging.
3. Preserve observed invariants. Refactor only after reference discovery and
   keep the smallest coherent responsibility boundary. Delete dead code only
   after proving it has no dynamic or external consumer.
4. Test the fixed behavior, failure path, and a nearby boundary case. For
   performance work, compare like-for-like measurements and report the
   workload; for architectural work, record the decision in an ExecPlan or ADR
   when it changes a durable boundary.

Finish with the root cause, the evidence for the chosen change, checks run,
and remaining uncertainty.
