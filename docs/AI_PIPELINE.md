# AI Pipeline

AI work is bounded and source-backed. Telegram messages are normalized and first
receive durable metadata/context classification. Obvious metadata and noise are
handled locally; short updates use bounded open-task context. Useful messages
are grouped into provider-safe internal windows, then routed by workload,
capability, local quota state, and provider health. Results are locally
validated before they are saved; messages are marked analyzed only with a
successful persistence transaction.

`Analyze All History` is corpus-oriented, not window-oriented. It classifies
all currently eligible messages, processes chronological chat-local windows,
checkpoints committed work, and reports classification and semantic coverage. An
isolated failed request is deferred while the rest of the queued history
continues; only three consecutive provider failures trigger the safe pause and a
later run resumes unfinished work.

One background-intelligence scheduler owns automatic live and history
eligibility. After the SQLite writer commits new messages, it coalesces a short
burst of wakeups and creates bounded Daily jobs from the durable rows. Startup
and the configured maximum-delay check recheck durable messages and `ai_jobs`,
so an in-memory wakeup is never the only record of work. Optional automatic
history analysis remains quiet-time only: pending Daily work or an active
writer makes history yield before its next provider request, leaving its jobs
pending for a later eligible run. The separate history interval bounds history
attempts without reverting to competing callbacks.

When the archive writer accepts a source edit or first deletion, it preserves
the prior raw-message version and marks only that message's existing
classification and AI interpretation stale in the same transaction. Edited,
eligible messages re-enter the existing exact-membership job path; deleted
messages remain excluded from provider work rather than being reconstructed or
silently treated as current.

Per-chat policy is enforced in two stages. `exclude` skips both classification
and semantic work; `classify_only` retains local metadata for archive and
retrieval but never creates provider jobs; `news_only` creates semantic work
only after classification identifies `external_news`. `include` forces semantic
eligibility for a chat that automatic routing would otherwise exclude.
The terminal presents these as **FULL**, **ARCHIVE ONLY**, **NEWS ONLY**, and
**IGNORE**, while retaining stable internal values for existing policy records.

Classification version 2 keeps forwarded provenance separate from information
scope, treats private groups as private rather than public by default, and uses
bounded English/Russian/Georgian operational phrases before generic question
routing. It persists only source-time-stable date presence; callers derive
`current` versus `historical` relative age from their own `as_of` time. Existing
rows are selectively reclassified in the normal bounded queue when v1 defects
matter (unknown scope, high-value/stale/actionable-question, or forwarded rows);
approved manual classification reviews retain their authority.

In `AI_ROUTING_MODE=quota_aware`, context extraction, reconciliation, memory
Q&A, and Deep Dive work use Gemini 3.5 Flash Lite, then Gemini 3.1 Flash Lite,
then Groq. Short classification and simple extraction retain the configured
hosted Gemma route (`gemma-4-31b-it`) as a bounded fallback when its input guard
permits it. Structured-output requirements filter ineligible profiles before
quota/health admission, and route diagnostics retain the deterministic policy
reason for each selected profile.
The router estimates the system instruction, provider-required schema
instruction, and user prompt before each physical dispatch. It reserves the
final 20% of the primary daily quota for interactive/critical work, keeps
rolling RPM/TPM state locally, and persists aggregate daily attempts plus
estimated and actual token counts in `ai_model_usage`. Gemini and Groq response
metadata is normalized for extraction and grounded answers when the SDK returns
it. No prompt content or credential is stored in routing telemetry.

Providers perform one cancellable transport attempt only. The router owns every
retry, pacing interval, attempt event, quota write, and success/failure record
for both extraction and Q&A. Gemini model profiles are capped at the
conservative `GEMINI_REQUESTS_PER_MINUTE` margin (14.5 by default); the router
uses the same rolling-window interval for retry attempts. A short provider
quota delay (up to 60 seconds) receives one router-owned retry; bounded
connection and typed 5xx failures use the configured exponential retry limit.
Longer quota cooldowns use Groq, then make Gemini eligible again after the
cooldown. The quota reason is retained as fallback metadata rather than
creating repeated failed batches.

When a quota-aware alternative succeeds, that route is kept first for the rest
of the active history run. This avoids repeatedly probing a provider that has
already rejected the session; later eligible alternatives remain available.
When Google supplies it, the monitor names the quota category and retry delay
without retaining the raw provider response.

A Gemini DNS or network-connectivity failure is not treated as quota exhaustion.
The router places the Gemini provider on a five-minute in-process health cooldown,
skips its alternate model during that interval, and uses Groq directly. A successful
Groq route remains first for the rest of the active history run.

A reachable Gemini HTTP 500/502/503/504 response is instead a typed transient
server failure. It may use the normal bounded retry/fallback path, but it does
not mark the whole Gemini provider unhealthy or suppress sibling models.

The same provider-wide behavior applies to a Gemini quota response: its retry time
becomes the Gemini health cooldown, Gemini 3.1 is not probed, and Groq is selected
as the next request. This keeps a known rejected primary route from delaying the
fallback session.

Every provider call is bounded by `AI_REQUEST_TIMEOUT_SECONDS` (45 by default),
so an unresponsive SDK request becomes a durable failed job instead of leaving
history analysis frozen. Groq uses its compatible JSON-object mode directly;
it does not make a strict-schema preflight that the configured model can reject.
After a Groq timeout, cancellation must settle before the router can retry or
fall back. If its bounded cancellation confirmation does not arrive, the one
physical attempt is recorded as failed and fallback is withheld rather than
overlapping an unconfirmed request.
History holds up to
`HISTORY_INTERNAL_CONCURRENCY` queued windows but marks only the request that
is actually at a provider as `running`.

Stopping history analysis is distinct from a provider failure. On an interrupt,
the active window returns to `pending`; no failed-batch diagnostic is created
and the remaining queue resumes on the next **Analyze all history** run.

The primary message window remains intact. Optional canonical and prior-message
context are each capped at 2,000 characters, and `AI_MAX_OUTPUT_TOKENS` defaults
to 1,200. Together these bounds keep a Gemini fallback below Groq's 8,000 TPM
allowance while retaining directly cited source messages.

Extraction contract version 2 is provider-neutral. Providers only parse the
transport response; the local contract owns the allowed response keys, item
keys, kinds, owners, status combinations, nullable fields, source references,
and confidence range. A malformed top-level response is retained as a failed
batch diagnostic and does not mark any message analyzed. A malformed item is
retained in `ai_item_rejections` while valid sibling observations remain
acceptable. `project_name` is required (nullable) on every item and is used as
an explicit source-backed task/project association.

Every extraction provider call receives one explicit router-authorized request
that names its provider and selected model. Gemini and Groq execute that
request directly; Groq passes the selected model to its API call. Extraction
and answer results both report provider/model identity and normalized usage.
Before success accounting or persistence, the router rejects a result whose
reported provider or model differs from the selected profile.

Jobs store their exact ordered source-message membership and a deterministic
selection fingerprint. Claiming rechecks deletion and chat-policy eligibility
against that stored membership; a changed selection is superseded rather than
silently narrowed or widened. New extraction starts at analysis version 2.
Older/stale results are eligible only through the explicit bounded history
operator path; normal daily scheduling does not replay the corpus.

Provider acceptance, observation persistence, canonical projection, and
materialized-context integration are separate durable phases. `process_ai_batch`
is the idempotent, transactional canonical projection entry point. It records
projection failures on the batch and never turns them into another provider
request. Accepted observation IDs make canonical events, conflicts,
relationships, and task lifecycle entries replay-safe; manual locks and Review
authority remain dominant.

Validated legacy observations persist an immutable semantic claim before the
linked compatibility observation in the same transaction. A claim records
extractor/provider/model provenance, bounded confidence, a structured payload,
exact submitted-message evidence, and its projection state. Claims are not
canonical truth. During accepted-batch projection, the sole graph writer emits
observed claim links and only allowlisted, unambiguous canonical relations;
everything else remains observed or goes to Review.

Projection writes coalesced revisioned invalidations for conversation, person,
project, company, task, and global scopes. `refresh_pending_context` performs
bounded summary, conversation, person, global-snapshot, and operational refresh
work. A refresh can only complete the revision it claimed, so later invalidation
is never cleared by an older worker. `ContactContextMaterializer` is the sole
writer of `person_context_state`; graph mutation remains outside this worker.

`ai_message_state` records analysis and context versions plus a stale flag.
Meaningful graph changes mark only affected high-importance evidence stale;
unrelated archive records are not globally reanalyzed.

Person invalidations may additionally make one bounded `SUMMARY` workload
request for the presentation-only Person Profile summary. Its input is a stable,
bounded package of displayable canonical rows plus their exact source messages;
the package hash skips provider work when neither changes. Output must cite
supplied message IDs, is locally validated, and only updates the existing
`person_context_state` materialization. It never creates observations or
canonical state, and a provider failure leaves the previous completed summary
in place while the invalidation remains retryable.

Manual Person Profile Deep Scan uses the isolated durable `profile` job lane.
Each job retains exact chronological source-message membership and is claimed
only from that person scope and extractor version; daily and general history
workers cannot consume it. A resolved person's full direct-conversation window is submitted as context,
along with self-authored messages in explicitly allowed related chats. This is
an authority boundary: owner and third-party wording can provide context or a
labelled third-party claim, but cannot automatically become current profile
facts, roles, capabilities, or relationships through Deep Scan.

Deep Person Profile extraction records nullable profile scope, assertion kind,
and effective dates on its immutable semantic claim. A direct item is eligible
for the normal allowlisted projection only when its cited message is authored
by the selected person. Third-party claims and strongly supported inferences
remain profile-only, labelled rows with exact evidence; they cannot mutate
current canonical person state. Ambiguous identity and conflicting direct
current claims remain Review work rather than overwrite history.

The Textual Deep Scan view starts that same bounded durable worker in a
background UI task, rather than awaiting provider work in a key handler. It
polls lightweight job state while a scan is active and refreshes full evidence
coverage only on entry and completion, avoiding repeated history-wide count
queries during visible progress. Its analysis audit is a bounded read of the
existing jobs, batches, semantic claims, and validation-rejection metadata
(including bounded rejection reasons);
raw message content and provider payloads are not diagnostic logs.
Evidence and window progress bars use that same current extractor-version job
scope, so prior extractor runs cannot be represented as current coverage.
