# Terminal UI

The primary interactive shell uses Textual. It autofocuses bounded people
search, supports keyboard selection, and shows a compact status line. Local
fuzzy discovery reads canonical people, aliases, usernames, and linked
projects without writing state. Ctrl+K opens the command palette; Ask Memory
remains separate from ordinary search.

People search debounces input and loads aliases, projects, companies, and
current facts through independent bounded reads, avoiding a one-to-many join
cross-product. Person detail uses the canonical bounded profile composition:
summary, current context, open items, projects, and exact evidence citations.

Person detail exposes the complete bounded profile reader through keyboard
sections: overview, contact briefing, work loops, projects, context,
connections, timeline, communication, exact evidence, scan state, and the
separately labelled private-direct and uncertain-claim views. The command
palette provides Ask Memory and access to the complete protected operations
workflow, including review, status, maintenance, and recovery actions.

Within a Person Profile, `0` shows Deep Scan state and `D` opens the explicit
queue screen. It reports eligible, completed, pending, and failed bounded
windows; Enter queues at most two exact-evidence windows and does not itself
change canonical profile state.

Alex Memory uses a small shared Rich component layer in `ui/components.py`. `AppPanel`, `DataTable`, `screen_header`, `notice`, status/priority labels, metric strips, and progress meters provide the common visual language across navigation, data screens, sync/AI progress, and Task Deep Dive.

All source-derived and model-derived content is rendered through `safe_text()`. It is literal `Text`, not Rich markup, and can be line-normalized and bounded at the display boundary. This applies to message snippets, AI diagnostics, profiles, search results, context packages, and Task Deep Dive evidence.

Tables progressively disclose columns in narrow terminals: task and retrieval views preserve identity, state, and evidence first, while secondary metadata is omitted. Tasks default to current actionable work (due or recently updated), with explicit all/waiting/done views. Entity and chat selection applies an optional text filter and discloses the displayed/total result count. Telegram sync combines chat and mode so an active worker remains understandable in constrained space. The home screen and Daily Brief switch from multi-column dashboards to stacked panels below their wide-layout thresholds. Empty, error, success, and warning states share concise titled notices.

Today, profiles, Search, Ask, and diagnostics are read-only. **Refresh operational state** is the explicit deterministic write action for follow-up and project-health evaluation. Task status updates show the current and proposed state before confirmation; review decisions display the complete payload and exact linked source message before a decision can be made. Search and Ask source selections open a bounded detail view with stable citations and exact message text when available.

**Daily Brief** is also read-only: it displays today's saved brief or explains
that one has not yet been generated. **Generate Daily brief** in Maintain is
the explicit write action that refreshes and stores today's payload.

The Tasks screen asks for a task ID and then presents a constrained action choice
(open, waiting, done, cancelled, Deep Dive, or back). It does not require an
operator to remember a compact command grammar.

Today selections and Follow-up IDs use the same detail path: the terminal opens
the linked canonical task or the exact message source when it is available.
After inspecting a Follow-up, an operator may set it to open, snoozed, done,
or cancelled. The change is confirmed and recorded as append-only manual
feedback; snoozed items remain in Follow-ups but stay out of Today until they
are reopened.

Automatic Follow-ups are a derived reminder of a task that has been waiting
past the configured threshold. An operational refresh cancels that automatic
reminder when the condition ends and can reopen it if the task becomes stale
waiting again; a recorded manual Follow-up state is never overwritten.
Review payloads support both direct and source-prefixed chat/message fields,
so operator decisions do not lose their source trail.

If Telegram fails after the local SQLite database has opened, the application
enters local-read mode. The home/status views expose the failed connection;
Search, Today, Tasks, Ask, Review, and diagnostics remain usable while sync and
analysis actions explain that they require Telegram.
