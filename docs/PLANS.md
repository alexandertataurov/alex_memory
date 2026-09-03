# Execution Plans

Notion is the sole authority for task work control. These ExecPlans are
synchronized repository implementation artifacts: they do not create,
authorize, promote, reprioritize, unblock, or close work. Read the linked
Notion task first; if its scope, status, dependencies, gates, or authorization
differs from a plan, Notion wins and the plan must be synchronized.

Use an ExecPlan when a change has a durable state transition or material
rollback risk: migrations, backfills, large derived-state rebuilds,
cross-cutting architecture changes, model/routing migrations, or non-obvious
deletion/refactoring work. Create or revise a plan only inside a
Notion-authorized task. A plan records the bounded implementation approach;
scope changes require a Notion decision before repository work proceeds.

Keep active plans in `docs/exec-plans/active/` and move completed plans to
`docs/exec-plans/completed/` with their final outcome and verification. A plan
must state the objective, current and target state, constraints, affected
modules, implementation sequence, risks/decisions, validation, progress,
discoveries, and final outcome. Do not create a plan for a small self-contained
fix.

## Active
- [AM-118 application remediation](exec-plans/active/AM-118-application-remediation.md)
- [AM-122 person profile](exec-plans/active/AM-122-person-profile.md)
- [AM-120 semantic graph projection](exec-plans/active/AM-120-semantic-graph-projection.md)

## Completed

- [AM-124 bounded shared connections](exec-plans/completed/AM-124-shared-connections.md)
- [AM-078 database integrity](exec-plans/completed/AM-078-database-integrity.md)
- [AM-074 repair](exec-plans/completed/AM-074.md)
- [AM-106 physical provider request ownership](exec-plans/completed/AM-106-provider-request-accounting.md)
- [AM-059 data-model truthfulness](exec-plans/completed/AM-059-data-model-truthfulness.md)
- [AM-058 routing fallbacks](exec-plans/completed/AM-058-routing-fallbacks.md)
- [AM-103 diagnostics truthfulness](exec-plans/completed/AM-103-diagnostics-truthfulness.md)
- [AM-072 project health](exec-plans/completed/AM-072-project-health.md)
- [AM-112 session reproducibility](exec-plans/completed/AM-112-deep-dive-sessions.md)
- [AM-111 multilingual Deep Dive](exec-plans/completed/AM-111-multilingual-deep-dive.md)
- [AM-110 conversation intervals](exec-plans/completed/AM-110-conversation-intervals.md)
- [AM-109 local graph repair](exec-plans/completed/AM-109-local-graph-repair.md)
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
