# Task Deep Dive

Task Deep Dive investigates one canonical task without turning the Telegram archive into an unbounded prompt. It begins with the task row and a `task_reconciliation` context request, then uses the linked people, projects, companies, relationships, current temporal facts, events, and summaries to establish scope.

Raw-message retrieval is a second, bounded layer. Round one expands explicit task words and a small reviewable domain vocabulary, queries FTS when available (with a SQL fallback), and validates every result locally. Later rounds use only bounded terms found in accepted prior-round evidence and stop as soon as no new evidence or concepts appear. A message must either name a task-linked entity, be from the task source chat with a task concept, or come from a graph-related chat and contain at least two distinct concepts. This prevents a generic personal message about “hedging” from being attributed to a project hedge task.

Each selected item has a stable display citation such as `E-message-200-14`, source chat/message IDs when available, relevance reasons, and a bounded same-chat conversation window. Events, current facts, and task lifecycle entries are separate evidence types. Current canonical state and historical `as_of` state remain distinct because the context builder applies temporal validity before retrieval.

## Sessions and user curation

Sessions store only task ID, selected evidence references, scores, concepts, and timestamps; raw Telegram content is not copied into session tables. `task_notes` stores user-authored task notes, and `task_deep_dive_pins` stores durable evidence references. All tables are additive and are created safely by `database.connect()`.

In the terminal, open **Tasks** and enter `ID dive`. The follow-up commands are `ask`, `search`, `deeper`, `improve`, `note`, `pin`, and `back`. `improve` runs the task-scoped graph pass. The answer mode prints only selected source-backed evidence; recommendations and unknowns are labelled separately rather than being presented as facts.

## Limits

`TASK_DEEP_DIVE_MAX_*` controls search-query, evidence, raw-message, graph-depth, conversation-window, and rendering budgets. The report never requires an AI provider. It therefore remains usable when a provider is unavailable, while preserving source references for a later AI-assisted summary if one is added.
