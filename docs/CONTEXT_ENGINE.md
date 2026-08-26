# Context Engine

The context subsystem converts source-backed observations into events, temporal facts, relationships, snapshots, and bounded context bundles. `ContextRequest` declares a purpose, entity/chat/task seeds, an `as_of` time, and whether limited raw evidence is appropriate. `ContextBuilder` returns structured records with source provenance, deterministic score, and inclusion reasons before a renderer produces diagnostic or extraction background.

A changed current fact closes the prior validity interval instead of overwriting history. An `as_of` query selects the state valid at that time and keeps prior transitions separately, preventing present-day fact leakage into historical context.

## Ranking and traversal

Pinned context, current facts, and open/waiting tasks rank above relationships, events, summaries, and raw evidence. Scores add direct entity/chat matches, waiting state, confidence, recency, and bounded graph distance. Relationship expansion uses the current `relationships` table and `CONTEXT_MAX_GRAPH_DEPTH` (default 2); it is not an unbounded graph walk.

Unresolved rows in `context_conflicts` are included as explicitly labelled conflicts. The builder does not silently select one value when non-state facts disagree. Pinned memory remains attached to the canonical entity and is rendered before weaker inferred context.

The **Review** command presents each pending temporal conflict with its current
and proposed values plus chat/message provenance. Manual keep, accept, and ignore
decisions are appended to an audit log. Accepting a newer fact closes the prior
validity interval; an older accepted observation is retained as historical rather
than rewriting the current state. See [Temporal Conflict Review](TEMPORAL_CONFLICT_REVIEW.md).

The generic Review queue exposes the review type, rationale, confidence, and
available chat/message provenance. Accepted entity merges update canonical
references and aliases without changing raw evidence; task reviews go through
the normal reconciler; and accepted graph links create canonical relationships.
Classification edits are validated and update the persisted routing dimensions.
Every decision is retained as manual feedback.

Context budgets limit entities, facts, tasks, events, summaries, and raw messages independently. Lower-ranked evidence is removed first. The builder only uses indexed, limited SQL queries and does not scan Telegram history in Python.

Query alias resolution runs as a bounded SQL filter over `entity_aliases` (at most
48 matching aliases) rather than iterating every known alias in Python. This keeps
retrieval work proportional to the question, not the size of the contact graph.

## Extraction and diagnostics

Every claimed AI job builds `message_analysis` context before provider routing. The `<MEMORY_CONTEXT>` prompt section is explicitly background: new observations must be supported by the new `<MESSAGE>` window and cite only its IDs. This lets context resolve implicit projects and commitments without restating old facts as newly observed. Ask Alex Memory uses `ask_memory` context, and application-triggered daily briefs persist global context counts and diagnostics alongside their task/follow-up state.

The terminal's **Context diagnostics** command supports query, person, project, company, and global views. Its renderer includes scores, inclusion reasons, and provenance so unexpected context can be debugged.

Context-graph diagnostics also expose actionable maintenance signals: orphan
tasks and important messages, pending identity/graph reviews, stale
classification and semantic-analysis state, unclassified message backlog, the
persisted processing-route mix, and derived conversation segments that no
longer have matching task evidence.

This keeps retrieval explainable and prevents unbounded Telegram history from being sent to an AI provider.

## Temporal conversation segments

`ConversationSegmenter` derives chat/project periods from dated tasks that are
already linked to a canonical project. Consecutive anchors for one project form
one period; a return to that project starts a new one. Each period expires 90
days after its last anchor (or at the next period's start), so a historical
topic never turns into a permanent whole-chat project assignment.

Periods are derived state, not raw evidence: rebuilding replaces only rows
marked `task_anchors`. Classification assigns `project` scope only when the
message timestamp falls inside a matching period. Context and Deep Dive use
active periods to find relevant chat evidence, while general search gives a
bounded score boost to a matching project-period message. The canonical task
links remain the source of truth for graph repair.

## Context graph improvement

`ContextGraphImprover` is a conservative maintenance pass, not a second AI
pipeline. It derives temporal relationships only when accepted canonical tasks
already connect people, companies, projects, and source evidence. It never
auto-merges identities: ambiguous aliases remain in the review queue. Existing
links are checked before insertion, so repeated passes are idempotent; affected
high-importance classifications and semantic analyses are marked stale for
selective refresh.
High-confidence accepted items can add directly provenanced links. An ambiguous
chat-to-project suggestion is placed in the regular review queue only when the
chat has one unambiguous canonical project; the candidate does not change graph
state until manually reviewed.

The improver exposes global and person/company/project/task-scoped entry points.
Task-scoped improvement starts from the task's linked entities and source chat,
so a Deep Dive can repair its local evidence neighbourhood without a full pass.
For orphan tasks, entity-free events, and person/company facts, it requires two
independently anchored task links to the same project in the source chat before
applying a project connection. A single anchor becomes a review candidate; a
competing project consensus remains untouched.

## Task-specific investigation

`tasks.deep_dive.TaskDeepDiveService` composes (rather than replaces) `ContextBuilder` with a bounded raw-evidence search. The service uses `task_reconciliation` context and applies a smaller task-specific graph-depth limit. It reports canonical current state, current facts, historical `as_of` state through the builder, timeline evidence, unknowns, and explicitly labelled recommendations. See [Task Deep Dive](TASK_DEEP_DIVE.md) for the relevance rule and persistence model.
