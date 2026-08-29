# Execution Plans

Use an ExecPlan when a change has a durable state transition or material
rollback risk: migrations, backfills, large derived-state rebuilds,
cross-cutting architecture changes, model/routing migrations, or non-obvious
deletion/refactoring work.

Keep active plans in `docs/exec-plans/active/` and move completed plans to
`docs/exec-plans/completed/` with their final outcome and verification. A plan
must state the objective, current and target state, constraints, affected
modules, implementation sequence, risks/decisions, validation, progress,
discoveries, and final outcome. Do not create a plan for a small self-contained
fix.

## Active
- [AM-074 repair](exec-plans/active/AM-074.md)
- [AM-118 application remediation](exec-plans/active/AM-118-application-remediation.md)
- [AM-122 person profile](exec-plans/active/AM-122-person-profile.md)
- [AM-120 semantic graph projection](exec-plans/active/AM-120-semantic-graph-projection.md)

## Completed

- [AM-079 temporal fact authority](exec-plans/completed/AM-079-temporal-fact-authority.md)
- [AM-107 Deep Dive evidence integrity](exec-plans/completed/AM-107-deep-dive-evidence-integrity.md)
- [AM-094 Ask Memory evidence and router pipeline](exec-plans/completed/AM-094-ask-memory-pipeline.md)
- [AM-088 conversation open-loop lifecycle](exec-plans/completed/AM-088-open-loop-lifecycle.md)
- [AM-086 duplicate observation-event removal](exec-plans/completed/AM-086-observation-event-removal.md)
- [AM-085 entity-memory removal](exec-plans/completed/AM-085-entity-memory-removal.md)
- [AM-057 context freshness](exec-plans/completed/AM-057-context-freshness.md)
- [AM-053 context dirty queue](exec-plans/completed/AM-053-context-dirty-queue.md)
- [AM-070 task-project links](exec-plans/completed/AM-070-task-project-links.md)
- [AM-084 direct-chat identity](exec-plans/completed/AM-084-direct-chat-identity.md)
- [AM-095 read-only terminal workflow](exec-plans/completed/AM-095-terminal-workflow.md)
- [AM-055 durable background intelligence scheduling](exec-plans/completed/AM-055-background-intelligence.md)
- [AM-054 authoritative runtime status](exec-plans/completed/AM-054-runtime-status.md)
- [AM-113 Codex workflow guardrails](exec-plans/completed/AM-113-codex-workflow-guardrails.md)
- [AM-073 classification contract](exec-plans/completed/AM-073-classification-contract.md)
- [AM-092 engineering harness](exec-plans/completed/AM-092-engineering-harness.md)
