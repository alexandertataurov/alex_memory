# Intelligence Workflow

Historical analysis is expressed as one user-facing operation. It reports coverage,
remaining eligible messages, and provider failures; internal provider windows are
bounded implementation details and are not terminal workflow steps.

## Incremental coverage

`FullHistoryAnalyzer` first applies the local classifier to every eligible message
that has no current classification, then claims and processes durable history jobs.
Committed semantic work is retained after every successful provider response. An
isolated provider failure is retained and deferred while other queued history
continues. Three consecutive failures pause the operation safely rather than
retrying an unavailable provider indefinitely; a later explicit or scheduled run
continues from durable job and classification state.

The terminal announces semantic-analysis start immediately and prints a concise
committed-message/provider-request update after each successful request. This
keeps a rate-limited run visible without exposing provider window mechanics.

Coverage is tracked per conversation in `conversation_analysis_state`. A history
run is complete only when semantic coverage reaches the current eligible-message
count; new messages or messages made stale by new context naturally become work
for a later run.

## Message classification

`message_classifications` stores deterministic, contextual routing signals for a
source message: conversation and content type, actionability, importance, scope,
temporal relevance, topics, confidence, classifier version, and context version.
The stored version makes changes to the classifier safely re-runnable. High-value
classifications can also be marked context-stale after a graph change and are then
classified again without modifying raw Telegram evidence.

Classification is deliberately not semantic extraction. It helps bounded retrieval
rank actionable and important messages while AI extraction remains separately
validated and source-backed.

The classifier uses a small, bounded set of local signals—open linked tasks and
the most recent important updates in the same chat—to distinguish short replies,
business scope, decisions, and historical messages without treating context as
new evidence.

Conversation segments constrain project-scoped context to the matching period
in a chat. They prevent a past project anchor from making unrelated later
personal messages look operational.

## Conversation intelligence

`ConversationContextService` is a materialized contact-level perspective over
the existing context graph, not a second graph. After accepted observations are
projected, the affected canonical person's Telegram conversation is refreshed:
accepted task/item activity becomes time-bounded contact segments, open task
loops are represented without creating duplicate tasks, person/project pairs are
updated, and current plus long-term person summaries are refreshed.

The service also performs a bounded, conservative recent-message pass for
operational question/answer links. Both sides retain their original chat and
message IDs. A link never creates a fact by itself; it only resolves the
source-backed open loop.

Before semantic extraction, a dialog with exactly one previously resolved
person receives its compact current contact package (thread, current state,
open loops, active project contexts, and bounded canonical context). The prompt
continues to state that this is background only: every new observation must cite
one of the new `<MESSAGE>` records. Ambiguous dialogs keep the generic bounded
graph preamble instead of guessing an identity.

Contact context is incremental and bounded. It reads accepted observations,
canonical tasks, current facts, and at most 120 recent messages for
question/answer linking; it does not regenerate a lifetime summary from raw
message history. Historical requests select the matching contact segment, so a
later current thread is not injected into an earlier period.

Manual identity merges update this materialized contact state alongside the
existing canonical references. Conflicting contact rows are conservatively
deduplicated; raw evidence and its original source identity are never merged or
rewritten.

## Context-graph improvement

`ContextGraphImprover` only creates relationships between canonical entities that
are already anchored by accepted tasks and their source AI item. Each derived edge
retains the originating chat, message, and timestamp. Relationship insertion uses
the existing idempotent repository operation, so repeating a run does not create
duplicate links.

After an accepted AI batch is projected into canonical state, improvement runs only
for that batch's chat. It never guesses identities or auto-merges entities; those
decisions remain in the review workflow. When new edges are added, important
classifications in the affected chat are marked stale and the graph version is
bumped for a later incremental refresh.

High-confidence accepted items may create evidence-backed links directly. A
high-confidence item lacking a project only becomes a `graph_link` review
candidate when its source chat has exactly one canonical project; it is never
silently assigned or used to auto-merge identities.

Orphan tasks, events, and facts are repaired only from bounded source-chat
project consensus. A single plausible project is queued for manual approval;
temporal-fact interval repair corrects impossible or stale validity boundaries
without changing fact values or evidence.

Manual review acceptance applies its approved action to canonical state: entity
merges move references to the selected entity, task changes use the accepted
source item, and graph repairs attach their selected project. The decision is
also retained as append-only manual feedback.

## Storage and migration

Migration 5, `intelligence_coverage`, adds `message_classifications` and
`conversation_analysis_state`. It is additive and is applied through the ordered
SQLite migration ledger; see [Database Migrations](DATABASE_MIGRATIONS.md).

`HISTORY_INTERNAL_CONCURRENCY`, `HISTORY_INTERNAL_BATCH_MESSAGES`, and
`HISTORY_INTERNAL_BATCH_CHARS` bound the queued provider-safe history windows
without appearing in the normal product workflow. Only the window currently
being sent to a provider is marked `running`; the older `AI_HISTORY_*` names
remain fallback compatibility aliases for existing local configuration.
