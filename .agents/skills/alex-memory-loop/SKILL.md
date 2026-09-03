---
name: alex-memory-loop
description: Execute the Alex Memory development loop from the next Notion-authorized leaf through verification, evidence sync, commit, and automatic continuation until a real gate.
---

# Alex Memory execution loop

Use this skill for requests such as "continue Alex Memory", "fix the next thing",
"work on the backlog", or any request to execute already-authorized Alex Memory
work without manually selecting a task.

## Authority model

- **Work control:** Notion only.
- **Implementation truth:** repository code and tests.
- **Mirrors/history:** `TASKS.md`, ExecPlans, changelog, docs, and GitHub prose.

Repository state never creates, promotes, reprioritizes, authorizes, unblocks, or
closes work.

## Loop

1. Query **Codex — Ready & Authorized**.
2. Select the lowest-sequence unblocked executable implementation leaf.
3. Fetch only that task, its parent, blockers, gate fields, Owner Action, and any
   directly relevant product/context pages.
4. Inspect only the repository code, tests, schema/config, callers, and mirrors
   needed for that leaf.
5. Build a fresh in-session task packet:

```text
TASK
<Notion task ID/title>

GOAL
<current intended outcome>

CURRENT IMPLEMENTATION
<relevant current behavior/evidence>

AUTHORIZED SCOPE
<what this leaf permits>

DO NOT TOUCH
<nearby but unauthorized scope>

CHANGE CLASS
Fast | Standard | Risky

ACCEPTANCE
<observable completion conditions>

TARGETED TESTS
<smallest useful verification loop>

COMPLETION GATE
Fast: targeted tests + Ruff
Standard: make check
Risky: make verify

KNOWN BLOCKERS / GATES
<current blockers, owner action, or none>

EXPECTED FILES
<likely touched paths; advisory only>
```

The stored Notion `Prompt` is intent/context, not a substitute for this live
packet. If it conflicts with current task fields or code/tests, stop scope
expansion and resolve the inconsistency in Notion.

6. Implement the smallest coherent increment.
7. During iteration, run targeted tests after each coherent increment. Patch-time
   hooks should remain lightweight.
8. Run the completion gate for the selected change class:
   - **Fast:** targeted tests + Ruff on changed files; compile/import sanity where
     relevant.
   - **Standard:** `make check`.
   - **Risky:** ExecPlan + backup/dry-run when applicable + `make verify`.
9. Review callers, failure paths, and diff for unintended scope or AI-slop.
10. Update the authoritative Notion task with outcome, evidence, status, gates,
    and dependencies. Update repository mirrors only when materially required.
11. Commit the coherent completed leaf.
12. Query **Codex — Ready & Authorized** again. If another independently
    authorized leaf exists, continue automatically from step 2.

## Stop conditions

Do not ask whether to continue between independently authorized leaves. Stop and
surface the exact decision required only for:

- Owner Acceptance.
- Operator Authorization.
- destructive or migration approval not already granted.
- ambiguity that changes product direction or authorized scope.
- multiple equally valid product choices requiring owner preference.
- no remaining executable authorized leaf.

A blocked leaf is not a reason to stop the whole loop when another independent,
authorized leaf can proceed.

## Change classes

### Fast

Use when the change is local, reversible, has no persistent-data/schema impact,
and does not alter a cross-cutting contract.

Expected flow: code → targeted tests → Ruff → Notion evidence/status → material
mirror only if needed → commit.

### Standard

Use for ordinary product/engineering work spanning multiple files or behavior
boundaries without persistent-data migration risk.

Expected flow: code → targeted tests → `make check` → Notion → affected docs or
changelog if material → commit.

### Risky

Use for migrations, backfills, destructive work, security-sensitive changes,
broad architecture/routing changes, or changes capable of affecting persistent
data.

Expected flow: ExecPlan → backup/dry-run when applicable → code → targeted tests
→ `make verify` → Notion gates/evidence → material task/docs/changelog mirrors →
commit.

## Handoff

Report only what helps the next action: completed task ID, change class, changed
behavior/files, migration/data impact, verification run, Notion state, commit,
and either the next leaf being executed or the exact gate that stopped the loop.
