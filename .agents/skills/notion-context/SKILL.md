---
name: notion-context
description: Retrieve targeted Notion project, decision, requirement, or business context before work that depends on prior history; do not use for self-contained coding tasks.
---

# Targeted Notion context

Use this for an existing Alex Memory project/task/feature, a prior decision,
requirements, people or company context, blockers, roadmap, research, or a
request to continue prior work. Do not use it for a failing unit test or a
small self-contained code edit.

1. Name the concrete entity, project, feature, or decision. Search Notion with
   that specific phrase, not generic terms such as `project`.
2. Fetch only the smallest useful result set: usually a project/task page and
   one linked decision or specification. Do not enumerate a database or the
   workspace.
3. Extract current/superseded status, decisions, requirements, constraints,
   open tasks, blockers, and unresolved questions. Give a compact summary and
   say which pages were used.
4. Compare against `TASKS.md`, architecture/docs, and the implementation.
   Repository code is authoritative for what exists now; Notion is
   authoritative for intent and business history. Surface discrepancies and
   avoid feature creep from stale, completed, rejected, or speculative notes.

If Notion fails or authentication is unavailable, report it once and continue
with repository evidence; do not retry repeatedly.
