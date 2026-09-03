from __future__ import annotations

import asyncio
import json
import signal
import sqlite3

from rich.console import Console
from rich.prompt import Prompt
from rich.text import Text
from telethon import TelegramClient

from .ai.service import analyze_daily_messages, analyze_history_messages
from .ai.scheduler import BackgroundIntelligenceScheduler
from .ai.routing import RequestPriority
from .config import Settings
from .chat_policy import set_chat_policy
from .database import connect, set_app_meta, update_known_chat_metadata
from .operational import (
    generate_daily_brief,
    load_daily_brief,
    manually_update_task,
    resolve_review_item,
    review_actions,
)
from .intelligence import (
    answer_question_with_ai,
    attention_items,
    manually_update_follow_up,
    profile,
    reject_task,
)
from .context.refresh import enqueue_context_refresh, refresh_pending_context
from .profile_summary import refresh_all_person_profiles
from .models import DialogInfo
from .retrieval import SearchResult
from .context import (
    ContextGraphImprover,
    ContextService,
    graph_diagnostics,
    list_temporal_conflicts,
    resolve_temporal_conflict,
)
from .tasks.deep_dive import TaskDeepDiveService
from .tasks.deep_dive.renderer import render_report
from .session_lock import SessionLock
from .runtime_status import RuntimeStatusService
from .telegram import TelegramSyncService, load_dialog_inventory
from .ui.components import AppPanel as Panel
from .ui.components import notice, safe_text
from .ui.ai_analytics import show_ai_analytics, show_ai_request_monitor
from .ui.profile import show_profile
from .ui.runtime_status import show_status
from .ui.navigation import resolve_maintenance_command, show_app_header, show_main_menu
from .ui.screens import (
    show_ai_diagnostics,
    show_ask_answer,
    show_attention,
    show_context_view,
    show_context_graph,
    show_chat_policies,
    show_daily_brief,
    show_entities,
    show_people,
    show_follow_up_detail,
    show_follow_ups,
    show_result_detail,
    show_review_detail,
    show_review_queue,
    show_settings,
    show_tasks,
    show_temporal_conflicts,
)


class AlexMemoryApp:
    def __init__(self, settings: Settings, console: Console | None = None):
        self.settings = settings
        self.console = console or Console()
        self.conn: sqlite3.Connection | None = None
        self.client: TelegramClient | None = None
        self.dialogs_cache: list[DialogInfo] | None = None
        self.live_sync: TelegramSyncService | None = None
        self.runtime_status: RuntimeStatusService | None = None
        self.background_scheduler: BackgroundIntelligenceScheduler | None = None
        self.session_lock = SessionLock(settings.root / "alex_memory.session.lock")
        self.analysis_lock = asyncio.Lock()
        self.shutdown_error: Exception | None = None

    async def run(self) -> int:
        exit_code = 0
        try:
            await self.start()
            from .ui.textual_app import AlexMemoryTerminal

            terminal = AlexMemoryTerminal(self)
            await terminal.run_async()
            if terminal.operation_command is not None:
                await self.menu_loop(initial_command=terminal.operation_command)
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        except Exception as error:
            self.console.print()
            self.console.print(
                Panel(
                    safe_text(f"{type(error).__name__}\n\n{error}"),
                    title="Application error",
                    border_style="red",
                )
            )
            exit_code = 1
        finally:
            if await self.close() is not None:
                exit_code = 1
        return exit_code

    async def start(self) -> None:
        self.session_lock.acquire()
        conn = connect(self.settings)
        self.conn = conn
        self.runtime_status = RuntimeStatusService(conn, self.settings)
        self.runtime_status.mark_starting()
        self.console.clear()
        self._show_header()
        self.console.print(Text("\n● Connecting to Telegram…", style="cyan"))

        client = TelegramClient(
            str(self.settings.session_path),
            self.settings.telegram_api_id,
            self.settings.telegram_api_hash,
        )
        self.client = client
        try:
            await client.start()
            me = await client.get_me()
            set_app_meta(conn, "owner_telegram_user_id", str(me.id))
            conn.commit()
            identity = (
                f"@{me.username}" if me.username else (me.first_name or str(me.id))
            )
            connected = Text("● CONNECTED  ", style="bold green")
            connected.append(str(identity))
            self.console.print(connected)
            self.console.print(Text("● Synchronizing Telegram…", style="cyan"))
            await self.refresh_inventory()
            self.background_scheduler = BackgroundIntelligenceScheduler(
                conn,
                self.settings,
                run_daily=self._scheduled_daily_analysis,
                run_history=self._scheduled_history_analysis,
                writer_busy=lambda: bool(
                    self.live_sync
                    and self.live_sync.write_queue
                    and not self.live_sync.write_queue.empty()
                ),
                on_error=self._background_analysis_error,
            )
            self.live_sync = TelegramSyncService(
                client,
                conn,
                self.settings,
                background_scheduler=self.background_scheduler,
                on_daily_brief=self._auto_daily_brief,
            )
            assert self.dialogs_cache is not None
            await self.live_sync.start(self.dialogs_cache)
        except Exception as error:
            self.runtime_status.mark_startup_failed(error)
            failed_sync = self.live_sync
            self.live_sync = None
            self.background_scheduler = None
            if failed_sync is not None:
                try:
                    await failed_sync.close()
                except Exception as close_error:
                    self.console.print(
                        notice(
                            f"{type(close_error).__name__}: {close_error}",
                            title="Startup cleanup failed",
                            tone="warning",
                        )
                    )
            self.console.print(
                notice(
                    f"{type(error).__name__}: {error}\n\nLocal reads remain available. Sync and analysis are disabled until Telegram can start.",
                    title="Telegram unavailable — local mode",
                    tone="warning",
                )
            )

    async def run_daemon(self) -> int:
        exit_code = 0
        try:
            await self.start()
            if self.live_sync is None:
                return 1
            self.console.print(
                notice(
                    "Alex Memory is running unattended. Press Ctrl+C to stop safely.",
                    title="Daemon active",
                    tone="success",
                )
            )
            stop = asyncio.Event()
            loop = asyncio.get_running_loop()
            for signum in (signal.SIGINT, signal.SIGTERM):
                try:
                    loop.add_signal_handler(signum, stop.set)
                except NotImplementedError:
                    pass
            await stop.wait()
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            if await self.close() is not None:
                exit_code = 1
        return exit_code

    async def menu_loop(self, *, initial_command: str | None = None) -> None:
        assert self.conn is not None
        pending_command = initial_command
        while True:
            self.console.print()
            self._show_menu()
            if pending_command is None:
                people = show_people(self.conn, self.console)

                try:
                    selection = Prompt.ask(
                        "Search or person ID [dim](/ actions)[/dim]", default=""
                    ).strip()
                except (KeyboardInterrupt, EOFError):
                    return

                if selection != "/":
                    if selection:
                        try:
                            person_id = int(selection)
                        except ValueError:
                            await self._show_people_menu(query=selection)
                        else:
                            if person_id in people:
                                await self._show_person_profile(person_id)
                            else:
                                self.console.print(
                                    "[yellow]Choose an ID from the People list.[/yellow]"
                                )
                    continue

                command = self._command_search()
                if command is None:
                    continue
            else:
                command, pending_command = pending_command, None

            if command == "maintain":
                command = resolve_maintenance_command(
                    Prompt.ask(
                        "Maintenance command [dim](blank to return)[/dim]", default=""
                    )
                )
                if command is None:
                    continue
            if command is None:
                message = Text("Unknown command. ", style="bold yellow")
                message.append("Use a highlighted letter, command name, or :maintain.")
                self.console.print(message)
            elif command == "sync":
                await self.sync_telegram()
            elif command == "resync_profiles":
                await self.resync_all_data_and_refresh_profiles()
            elif command == "analyze_daily":
                await self.analyze_daily()
            elif command == "analyze_history":
                await self.analyze_history()
            elif command == "ask":
                question = Prompt.ask(
                    "Question [dim](blank to return)[/dim]", default=""
                ).strip()
                if not question:
                    continue
                answer, sources = await answer_question_with_ai(
                    self.conn, question, self.settings
                )
                show_ask_answer(answer, sources, self.console)
                self._inspect_retrieval_result(sources, "Source number")
            elif command == "today":
                attention = attention_items(self.conn, self.settings)
                show_attention(attention, self.console)
                self._inspect_retrieval_result(attention, "Today item number")
            elif command == "tasks":
                view = Prompt.ask(
                    "Task view",
                    choices=["current", "all", "waiting", "done"],
                    default="current",
                )
                show_tasks(self.conn, self.console, view=view)
                task_id_text = Prompt.ask(
                    "Task ID [dim](blank to return)[/dim]", default=""
                ).strip()
                if not task_id_text:
                    continue
                try:
                    task_id = int(task_id_text)
                except ValueError:
                    self.console.print(
                        notice(
                            "Enter a numeric canonical task ID.",
                            title="Invalid task ID",
                            tone="warning",
                        )
                    )
                    continue
                status = Prompt.ask(
                    "Task action",
                    choices=[
                        "open",
                        "waiting",
                        "blocked",
                        "done",
                        "canceled",
                        "dive",
                        "back",
                    ],
                    default="back",
                )
                if status == "back":
                    continue
                if status == "dive":
                    self._task_deep_dive(task_id)
                    continue
                if not self._confirm_task_update(task_id, status):
                    continue
                updated = (
                    reject_task(self.conn, task_id)
                    if status == "canceled"
                    else manually_update_task(self.conn, task_id, status)
                )
                if updated:
                    self.conn.commit()
                    self.console.print(
                        notice(
                            "Its status is now protected from AI changes.",
                            title="Task updated",
                            tone="success",
                        )
                    )
                else:
                    self.console.print(
                        notice(
                            "No canonical task has that ID.",
                            title="Task not found",
                            tone="warning",
                        )
                    )
            elif command == "follow_ups":
                show_follow_ups(self.conn, self.console)
                follow_up_id = Prompt.ask(
                    "Follow-up ID [dim](blank to return)[/dim]", default=""
                ).strip()
                if follow_up_id:
                    try:
                        if not show_follow_up_detail(
                            self.conn, int(follow_up_id), self.console
                        ):
                            continue
                        status = Prompt.ask(
                            "Follow-up action",
                            choices=["open", "snoozed", "done", "cancelled", "back"],
                            default="back",
                        )
                        if status == "back" or not self._confirm_follow_up_update(
                            int(follow_up_id), status
                        ):
                            continue
                        if manually_update_follow_up(
                            self.conn, int(follow_up_id), status
                        ):
                            self.conn.commit()
                            self.console.print(
                                notice(
                                    "Manual feedback is saved with this follow-up.",
                                    title="Follow-up updated",
                                    tone="success",
                                )
                            )
                        else:
                            self.console.print(
                                notice(
                                    "That follow-up no longer exists.",
                                    title="Follow-up not found",
                                    tone="warning",
                                )
                            )
                    except ValueError:
                        self.console.print(
                            notice(
                                "Enter a numeric follow-up ID.",
                                title="Invalid follow-up",
                                tone="warning",
                            )
                        )
            elif command == "projects":
                self._show_profile_menu("project")
            elif command == "contacts":
                await self._show_people_menu()
            elif command == "brief":
                try:
                    brief = load_daily_brief(self.conn)
                except ValueError as error:
                    self.console.print(
                        notice(str(error), title="Daily brief", tone="warning")
                    )
                    continue
                if brief is None:
                    self.console.print(
                        notice(
                            "No Daily Brief has been generated for today. Use Generate Daily brief in Maintain.",
                            title="Daily brief unavailable",
                            tone="info",
                        )
                    )
                    continue
                show_daily_brief(brief, self.console)
            elif command == "search":
                await self._show_people_menu()
            elif command == "review":
                show_review_queue(self.conn, self.console)
                review_id = Prompt.ask(
                    "Review item ID [dim](blank to skip)[/dim]", default=""
                ).strip()
                if review_id:
                    try:
                        row = self.conn.execute(
                            "SELECT review_type FROM review_queue WHERE review_id=? AND status='pending'",
                            (int(review_id),),
                        ).fetchone()
                        if row is None:
                            raise ValueError("That pending review item was not found.")
                        review_type = str(row[0])
                        if not show_review_detail(
                            self.conn, int(review_id), self.console
                        ):
                            continue
                        choices = review_actions(review_type)
                        action = Prompt.ask(
                            "Decision", choices=[*choices, "back"], default="back"
                        )
                        if action == "back":
                            continue
                        edited_payload: dict[str, object] | None = None
                        if review_type == "entity_merge" and action == "accept":
                            keep_entity_id = Prompt.ask(
                                "Canonical entity ID to keep"
                            ).strip()
                            edited_payload = {"keep_entity_id": int(keep_entity_id)}
                        elif (
                            review_type == "message_classification" and action == "edit"
                        ):
                            scope = Prompt.ask(
                                "Information scope",
                                choices=[
                                    "personal",
                                    "business",
                                    "project",
                                    "public_information",
                                    "external_news",
                                ],
                            )
                            content_type = Prompt.ask(
                                "Content type [dim](blank to keep)[/dim]", default=""
                            ).strip()
                            edited_payload = {
                                "information_scope": scope,
                                **(
                                    {"content_type": content_type}
                                    if content_type
                                    else {}
                                ),
                            }
                        if (
                            Prompt.ask(
                                "Apply this manual decision",
                                choices=["confirm", "back"],
                                default="back",
                            )
                            != "confirm"
                        ):
                            continue
                        resolve_review_item(
                            self.conn,
                            int(review_id),
                            action,
                            edited_payload=edited_payload,
                            settings=self.settings,
                        )
                        self.console.print(
                            notice(
                                "Manual decision saved as authoritative feedback.",
                                title="Review updated",
                                tone="success",
                            )
                        )
                    except ValueError as error:
                        self.console.print(
                            notice(str(error), title="Review", tone="warning")
                        )
                conflicts = list_temporal_conflicts(self.conn)
                show_temporal_conflicts(conflicts, self.console)
                if conflicts:
                    raw_id = Prompt.ask(
                        "Temporal conflict ID [dim](blank to return)[/dim]", default=""
                    ).strip()
                    if raw_id:
                        try:
                            conflict_id = int(raw_id)
                        except ValueError:
                            self.console.print(
                                notice(
                                    "Enter a numeric conflict ID.",
                                    title="Invalid conflict ID",
                                    tone="warning",
                                )
                            )
                            continue
                        choice = Prompt.ask(
                            "Decision",
                            choices=["keep", "accept", "ignore", "back"],
                            default="back",
                        )
                        if choice == "back":
                            continue
                        note = Prompt.ask(
                            "Decision note [dim](optional)[/dim]", default=""
                        )
                        selected = next(
                            (
                                item
                                for item in conflicts
                                if item["conflict_id"] == conflict_id
                            ),
                            None,
                        )
                        manual_value = manual_valid_from = None
                        if (
                            choice == "accept"
                            and selected
                            and selected["observation_value"] is None
                        ):
                            raw_value = Prompt.ask("Manual fact value (JSON object)")
                            try:
                                manual_value = json.loads(raw_value)
                            except json.JSONDecodeError:
                                self.console.print(
                                    notice(
                                        "Enter a JSON object.",
                                        title="Invalid value",
                                        tone="warning",
                                    )
                                )
                                continue
                            if not isinstance(manual_value, dict):
                                self.console.print(
                                    notice(
                                        "Enter a JSON object.",
                                        title="Invalid value",
                                        tone="warning",
                                    )
                                )
                                continue
                            manual_valid_from = (
                                Prompt.ask("Effective from (ISO date/time)", default="")
                                or None
                            )
                        if (
                            Prompt.ask(
                                "Apply this temporal decision",
                                choices=["confirm", "back"],
                                default="back",
                            )
                            != "confirm"
                        ):
                            continue
                        resolve_temporal_conflict(
                            self.conn,
                            conflict_id,
                            {
                                "keep": "keep_existing",
                                "accept": "accept_observation",
                                "ignore": "ignore",
                            }[choice],
                            note,
                            manual_value=manual_value,
                            manual_valid_from=manual_valid_from,
                        )
                        self.console.print(
                            notice(
                                "Temporal conflict decision saved.",
                                title="Review updated",
                                tone="success",
                            )
                        )
            elif command == "chat_policy":
                search = Prompt.ask(
                    "Chat search [dim](blank for all)[/dim]", default=""
                )
                if not show_chat_policies(self.conn, self.console, search):
                    continue
                editor = Prompt.ask(
                    "Edit policy",
                    choices=["guided", "compact", "back"],
                    default="guided",
                )
                if editor == "back":
                    continue
                try:
                    if editor == "guided":
                        chat_id_text = Prompt.ask("Chat ID").strip()
                        mode = Prompt.ask(
                            "Analysis policy",
                            choices=[
                                "auto",
                                "full",
                                "archive_only",
                                "news_only",
                                "ignore",
                            ],
                            default="auto",
                        )
                        reason_text = Prompt.ask(
                            "Reason [dim](optional)[/dim]", default=""
                        ).strip()
                    else:
                        raw_policy = Prompt.ask(
                            "Policy [dim](CHAT_ID auto|full|archive_only|news_only|ignore [reason])[/dim]",
                            default="",
                        ).strip()
                        if not raw_policy:
                            continue
                        chat_id_text, mode, *reason = raw_policy.split(maxsplit=2)
                        reason_text = reason[0] if reason else ""
                    set_chat_policy(
                        self.conn,
                        int(chat_id_text),
                        mode,
                        reason_text,
                    )
                    self.conn.commit()
                    self.console.print(
                        notice(
                            "Chat policy saved.", title="Chat analysis", tone="success"
                        )
                    )
                except ValueError as error:
                    self.console.print(
                        notice(str(error), title="Chat analysis", tone="warning")
                    )
            elif command == "diagnostics":
                assert self.runtime_status is not None
                show_status(self.runtime_status.snapshot(self.live_sync), self.console)
            elif command == "ai_diagnostics":
                show_ai_request_monitor(self.conn, self.settings, self.console)
                show_ai_diagnostics(self.conn, self.console)
                show_ai_analytics(self.conn, self.settings, self.console)
            elif command == "settings":
                show_settings(self.settings, self.console)
            elif command == "refresh":
                enqueue_context_refresh(self.conn, {("global", 0)})
                completed = await refresh_pending_context(self.conn, self.settings, 1)
                self.conn.commit()
                self.console.print(
                    notice(
                        f"Completed {completed} queued global refresh scope(s).",
                        title="Operational state refreshed",
                        tone="success",
                    )
                )
            elif command == "generate_brief":
                show_daily_brief(
                    generate_daily_brief(self.conn, settings=self.settings),
                    self.console,
                )
                self.conn.commit()
                self.console.print(
                    notice(
                        "Today's Daily Brief was generated and saved.",
                        title="Daily brief generated",
                        tone="success",
                    )
                )
            elif command == "context_graph":
                show_context_graph(graph_diagnostics(self.conn), self.console)
                action = (
                    Prompt.ask(
                        "Context graph [dim](improve, discover, status, blank to return)[/dim]",
                        default="",
                    )
                    .strip()
                    .lower()
                )
                if action == "improve":
                    report = ContextGraphImprover(self.conn).improve()
                    show_context_graph(
                        report.diagnostics, self.console, report.relationships_added
                    )
                elif action == "discover":
                    candidates = ContextGraphImprover(
                        self.conn
                    ).discover_cross_chat_candidates()
                    self.conn.commit()
                    self.console.print(
                        notice(
                            f"Queued {candidates} cross-chat candidate(s) for Review.",
                            title="Cross-chat discovery",
                            tone="success",
                        )
                    )
            elif command == "context_diagnostics":
                scope = Prompt.ask(
                    "Context scope",
                    choices=["query", "person", "project", "company", "global"],
                    default="query",
                )
                service = ContextService(self.conn, self.settings)
                if scope == "global":
                    context = service.get_global_context()
                elif scope == "query":
                    query = Prompt.ask(
                        "Context query [dim](blank to return)[/dim]", default=""
                    ).strip()
                    if not query:
                        continue
                    context = service.build_context_for_query(query)
                else:
                    search = Prompt.ask(
                        f"{scope.title()} search [dim](blank for all)[/dim]",
                        default="",
                    )
                    if not show_entities(self.conn, self.console, scope, search):
                        continue
                    entity_id = Prompt.ask(
                        f"{scope.title()} ID [dim](blank to return)[/dim]",
                        default="",
                    ).strip()
                    if not entity_id:
                        continue
                    try:
                        context = {
                            "person": service.get_person_context,
                            "project": service.get_project_context,
                            "company": service.get_company_context,
                        }[scope](int(entity_id))
                    except ValueError:
                        self.console.print(
                            notice(
                                "Enter a numeric canonical entity ID.",
                                title="Invalid entity ID",
                                tone="warning",
                            )
                        )
                        continue
                show_context_view(
                    context,
                    "Context diagnostics — ranked bounded model context",
                    self.console,
                    self.settings.context_max_chars,
                )
            elif command == "quit":
                return

    async def sync_telegram(self) -> None:
        assert self.conn is not None
        # The live service owns the writer and listener. Running the legacy
        # multi-worker full-sync alongside it can overload one MTProto session.
        if self.live_sync is not None:
            self.console.print(Text("● Synchronizing Telegram…", style="cyan"))
            await self.refresh_inventory()
            await self.live_sync.reconcile(self.dialogs_cache)
            self.console.print(Text("● SYNC COMPLETE", style="bold green"))
            return
        self._show_local_mode_notice("Sync")

    async def analyze_daily(self) -> None:
        assert self.conn is not None
        if self.live_sync is None:
            self._show_local_mode_notice("Daily analysis")
            return
        if self.dialogs_cache is None:
            self.console.print(Text("● Refreshing dialog metadata…", style="cyan"))
            await self.refresh_inventory()
        await self._run_daily_analysis()

    async def analyze_history(self) -> None:
        assert self.conn is not None
        if self.live_sync is None:
            self._show_local_mode_notice("History analysis")
            return
        if self.dialogs_cache is None:
            self.console.print(Text("● Refreshing dialog metadata…", style="cyan"))
            await self.refresh_inventory()
        async with self.analysis_lock:
            await analyze_history_messages(self.conn, self.settings, self.console)

    async def resync_all_data_and_refresh_profiles(self) -> None:
        """Run the explicit recovery path for current archive and profiles."""
        assert self.conn is not None
        if self.live_sync is None:
            self._show_local_mode_notice("Full resync")
            return
        self.console.print(
            Text("● Synchronizing the current Telegram archive…", style="cyan")
        )
        await self.sync_telegram()
        self.console.print(
            Text("● Completing eligible semantic history analysis…", style="cyan")
        )
        await self.analyze_history()
        self.console.print(
            Text("● Rebuilding all materialized person profiles…", style="cyan")
        )
        outcome = await refresh_all_person_profiles(self.conn, self.settings)
        self.console.print(
            notice(
                f"{outcome['refreshed']} of {outcome['people']} profiles rebuilt; "
                f"{outcome['summaries']} presentation summaries refreshed; "
                f"{outcome['failed']} retryable summary/materialization failures.",
                title="Full resync and profile refresh complete",
                tone="warning" if outcome["failed"] else "success",
            )
        )

    async def refresh_inventory(self, show_result: bool = False) -> None:
        assert self.client is not None
        assert self.conn is not None
        dialogs = await load_dialog_inventory(
            self.client,
            self.console,
        )
        self.dialogs_cache = dialogs
        update_known_chat_metadata(self.conn, dialogs)

        if show_result:
            users = sum(1 for d in dialogs if d.chat_type == "user")
            groups = sum(1 for d in dialogs if d.chat_type == "group")
            channels = sum(1 for d in dialogs if d.chat_type == "channel")
            self.console.print(
                "[green]Inventory refreshed:[/green] "
                f"{len(dialogs):,} dialogs | "
                f"{users:,} personal | {groups:,} groups | "
                f"{channels:,} channels skipped"
            )

    async def close(self) -> Exception | None:
        errors: list[Exception] = []
        if self.live_sync is not None:
            try:
                await self.live_sync.close()
            except Exception as error:
                errors.append(error)
            self.live_sync = None
        self.background_scheduler = None
        if self.runtime_status is not None:
            self.runtime_status.mark_offline()
        if self.conn is not None:
            try:
                self.conn.commit()
            except Exception as error:
                errors.append(error)
            try:
                self.conn.close()
            except Exception as error:
                errors.append(error)

        if self.client is not None and self.client.is_connected():
            try:
                await self.client.disconnect()
            except Exception as error:
                errors.append(error)

        self.session_lock.release()
        if errors:
            self.shutdown_error = errors[0]
            self.console.print(
                notice(
                    "; ".join(f"{type(error).__name__}: {error}" for error in errors),
                    title="Shutdown incomplete",
                    tone="warning",
                )
            )
            return errors[0]
        self.shutdown_error = None
        self.console.print(Text("\n● Alex Memory closed cleanly.", style="dim"))
        return None

    def _show_header(self) -> None:
        show_app_header(self.settings, self.console)

    def _show_menu(self) -> None:
        assert self.runtime_status is not None
        show_main_menu(self.console, self.runtime_status.snapshot(self.live_sync))

    def _command_search(self) -> str | None:
        """Search the small action palette; command text is never normal navigation."""
        actions: tuple[tuple[str, str, str], ...] = (
            ("review", "Review", "Resolve identity and claim decisions"),
            ("diagnostics", "System Status", "Sync, AI, and database health"),
            ("quit", "Quit", "Close Alex Memory"),
        )
        query = Prompt.ask("Search actions", default="").strip().casefold()
        if query.startswith("maint"):
            actions += (
                ("maintain", "Maintenance", "Recovery and development operations"),
            )
        matches = [
            action
            for action in actions
            if not query
            or query in action[1].casefold()
            or query in action[2].casefold()
        ]
        if not matches:
            self.console.print("[dim]No actions match that search.[/dim]")
            return None
        choices = "\n".join(
            f"[bright_cyan]{index}[/bright_cyan]  {label} [dim]— {detail}[/dim]"
            for index, (_, label, detail) in enumerate(matches, start=1)
        )
        self.console.print(
            Panel(choices, title="Action search", border_style="bright_blue")
        )
        selected = Prompt.ask("Select action", default="").strip()
        try:
            index = int(selected)
        except ValueError:
            return None
        return matches[index - 1][0] if 1 <= index <= len(matches) else None

    async def _show_people_menu(self, *, query: str = "") -> None:
        assert self.conn is not None
        rows = show_people(self.conn, self.console, query)
        if not rows:
            return
        value = Prompt.ask("Person ID", default="").strip()
        if not value:
            return
        try:
            person_id = int(value)
        except ValueError:
            return
        if person_id not in rows:
            return
        await self._show_person_profile(person_id)

    async def _show_person_profile(self, person_id: int) -> None:
        assert self.conn is not None
        profile_data = profile(self.conn, "person", person_id)
        sections = (
            "overview",
            "contact",
            "scan_status",
            "deep_scan",
            "loops",
            "projects",
            "context",
            "private",
            "uncertain",
            "connections",
            "timeline",
            "communication",
            "evidence",
        )
        view = "overview"
        while True:
            show_profile(profile_data, "person", self.console, section=view)
            choices = {
                "1": "contact",
                "2": "deep_scan",
                "3": "scan_status",
                "4": "loops",
                "5": "projects",
                "6": "context",
                "7": "connections",
                "8": "timeline",
                "9": "communication",
                "10": "evidence",
                "11": "private",
                "12": "uncertain",
                "0": "back",
            }
            choice = Prompt.ask(
                "Choose [dim](1 Brief · 2 Deep Scan · 3 Scan status · 4 Loops · 5 Projects · 6 Context · 7 Connections · 8 Timeline · 9 Communication · 10 Evidence · 11 Private · 12 Uncertain · 0 Back)[/dim]",
                default="0",
            ).strip()
            view = choices.get(choice, "overview")
            if view == "back":
                return
            if view == "deep_scan":
                from .profile_enrichment import enrich_person

                outcome = await enrich_person(
                    self.conn, self.settings, self.console, person_id
                )
                self.console.print(
                    notice(
                        str(outcome["outcome"]),
                        title="Deep Scan",
                        tone="success" if outcome["queued"] else "info",
                    )
                )
                profile_data = profile(self.conn, "person", person_id)
                view = "scan_status"
                continue
            if view not in sections:
                self.console.print("[yellow]Choose a listed profile section.[/yellow]")
                view = "overview"

    async def _scheduled_daily_analysis(self) -> None:
        assert self.conn is not None
        self.console.print(Text("● Automatic daily analysis started…", style="dim"))
        await self._run_daily_analysis(priority=RequestPriority.BACKGROUND)

    async def _scheduled_history_analysis(self, should_continue) -> None:
        assert self.conn is not None
        self.console.print(Text("● Automatic history analysis started…", style="dim"))
        async with self.analysis_lock:
            await analyze_history_messages(
                self.conn,
                self.settings,
                self.console,
                should_continue=should_continue,
            )

    def _background_analysis_error(self, lane: str, error: Exception) -> None:
        if self.live_sync is not None:
            self.live_sync.state.last_error = f"{lane}: {type(error).__name__}: {error}"

    async def _auto_daily_brief(self, brief_date: str) -> None:
        assert self.conn is not None
        self.console.print(
            safe_text(
                f"● Generating scheduled Daily Brief for {brief_date}…",
                style="dim",
            )
        )
        if self.live_sync is not None:
            try:
                await self.live_sync.reconcile()
            except Exception as error:
                self.live_sync.state.last_error = (
                    f"scheduled brief reconciliation: {type(error).__name__}: {error}"
                )
                self.console.print(
                    notice(
                        "The scheduled brief was skipped because Telegram reconciliation failed.",
                        title="Scheduled brief unavailable",
                        tone="warning",
                    )
                )
                return
        await self._run_daily_analysis(priority=RequestPriority.BACKGROUND)
        generate_daily_brief(self.conn, brief_date, self.settings)
        self.conn.commit()

    async def _run_daily_analysis(
        self, *, priority: RequestPriority = RequestPriority.INTERACTIVE
    ) -> None:
        assert self.conn is not None
        async with self.analysis_lock:
            await analyze_daily_messages(
                self.conn, self.settings, self.console, priority=priority
            )

    def _show_profile_menu(self, entity_type: str) -> None:
        assert self.conn is not None
        search = Prompt.ask(
            f"{entity_type.title()} search [dim](blank for all)[/dim]", default=""
        )
        if not show_entities(self.conn, self.console, entity_type, search):
            return
        entity_id = Prompt.ask(
            f"{entity_type.title()} ID [dim](blank to return)[/dim]", default=""
        ).strip()
        if not entity_id:
            return
        try:
            show_profile(
                profile(self.conn, entity_type, int(entity_id)),
                entity_type,
                self.console,
            )
        except ValueError:
            self.console.print(
                notice(
                    "Enter a numeric canonical entity ID.",
                    title="Invalid entity ID",
                    tone="warning",
                )
            )

    def _confirm_task_update(self, task_id: int, status: str) -> bool:
        assert self.conn is not None
        if status not in {"open", "waiting", "blocked", "done", "canceled"}:
            return True
        row = self.conn.execute(
            """SELECT t.title,t.details,t.status,t.manual_status_locked,t.due_date,
                      t.source_chat_id,i.source_message_id
               FROM tasks AS t
               LEFT JOIN ai_items AS i ON i.item_id=t.source_item_id
               WHERE t.task_id=?""",
            (task_id,),
        ).fetchone()
        if row is None:
            self.console.print(
                notice(
                    "No canonical task has that ID.",
                    title="Task not found",
                    tone="warning",
                )
            )
            return False
        title, details, current_status, locked, due_date, chat_id, message_id = row
        show_result_detail(
            self.conn,
            SearchResult(
                "task",
                str(title),
                str(details or ""),
                str(due_date) if due_date else None,
                0,
                task_id=task_id,
                source_id=task_id,
            ),
            self.console,
        )
        if chat_id is not None and message_id is not None:
            show_result_detail(
                self.conn,
                SearchResult(
                    "message",
                    "Task source evidence",
                    "",
                    None,
                    0,
                    chat_id=int(chat_id),
                    message_id=int(message_id),
                ),
                self.console,
            )
        self.console.print(
            Panel(
                safe_text(
                    f"{title}\n\nCurrent: {current_status}\nNew: {status}\n\n"
                    "This manual status will override later AI inference"
                    f"{'; it is already manually locked' if locked else ''}.",
                    1_000,
                ),
                title=f"Confirm task #{task_id}",
                border_style="yellow",
            )
        )
        return (
            Prompt.ask("Apply this manual status", choices=["yes", "no"], default="no")
            == "yes"
        )

    def _confirm_follow_up_update(self, follow_up_id: int, status: str) -> bool:
        assert self.conn is not None
        row = self.conn.execute(
            "SELECT title,status FROM follow_ups WHERE follow_up_id=?", (follow_up_id,)
        ).fetchone()
        if row is None:
            self.console.print(
                notice(
                    "That follow-up was not found.",
                    title="Follow-up",
                    tone="warning",
                )
            )
            return False
        title, current_status = row
        effect = (
            "A snoozed follow-up stays out of Today until it is reopened."
            if status == "snoozed"
            else "This manual decision is retained as operator feedback."
        )
        self.console.print(
            Panel(
                safe_text(
                    f"{title}\n\nCurrent: {current_status}\nNew: {status}\n\n" + effect,
                    1_000,
                ),
                title=f"Confirm follow-up #{follow_up_id}",
                border_style="yellow",
            )
        )
        return (
            Prompt.ask("Apply this manual status", choices=["yes", "no"], default="no")
            == "yes"
        )

    def _inspect_retrieval_result(
        self, results: list[SearchResult], prompt: str
    ) -> None:
        if not results:
            return
        raw_index = Prompt.ask(
            f"{prompt} [dim](blank to return)[/dim]", default=""
        ).strip()
        if not raw_index:
            return
        try:
            index = int(raw_index)
            if index < 1 or index > len(results):
                raise ValueError
        except ValueError:
            self.console.print(
                notice(
                    f"Enter a result number from 1 to {len(results)}.",
                    title="Invalid result",
                    tone="warning",
                )
            )
            return
        assert self.conn is not None
        show_result_detail(self.conn, results[index - 1], self.console)

    def _show_local_mode_notice(self, operation: str) -> None:
        self.console.print(
            notice(
                f"{operation} needs an active Telegram session. Search, Today, Tasks, Ask, Review, and diagnostics still use the local database.",
                title="Local mode",
                tone="warning",
            )
        )

    def _task_deep_dive(self, task_id: int) -> None:
        assert self.conn is not None
        service = TaskDeepDiveService(self.conn, self.settings)
        try:
            report = service.build(task_id)
        except ValueError as error:
            self.console.print(notice(error, title="Task Deep Dive", tone="warning"))
            return
        render_report(report, self.console)
        while True:
            action = (
                Prompt.ask(
                    "Deep Dive [dim](lookup, search, deeper, improve, note, pin, back)[/dim]",
                    default="back",
                )
                .strip()
                .lower()
            )
            if action in {"", "back"}:
                return
            if action == "deeper":
                render_report(service.build(task_id, deeper=True), self.console)
            elif action == "improve":
                graph_report = ContextGraphImprover(self.conn).improve_task(task_id)
                self.console.print(
                    notice(
                        f"Added {graph_report.relationships_added} source-backed link(s).",
                        title="Task context improved",
                        tone="success",
                    )
                )
                render_report(service.build(task_id), self.console)
            elif action in {"lookup", "search"}:
                query = Prompt.ask("Evidence query or search", default="").strip()
                if query:
                    if action == "lookup":
                        evidence, sources = service.lookup_evidence(task_id, query)
                        self.console.print(
                            Panel(
                                safe_text(evidence),
                                title="Deep Dive evidence lookup",
                                border_style="cyan",
                            )
                        )
                        self.console.print(
                            safe_text(
                                f"Sources: {', '.join(item.citation for item in sources)}",
                                style="dim",
                            )
                        )
                    else:
                        render_report(service.search(task_id, query), self.console)
            elif action == "note":
                note = Prompt.ask("Note", default="").strip()
                if note:
                    service.add_note(task_id, note)
                    self.console.print(
                        notice(
                            "The note is attached to this canonical task.",
                            title="Task note saved",
                            tone="success",
                        )
                    )
            elif action == "pin":
                evidence_id = Prompt.ask("Evidence ID", default="").strip()
                if evidence_id:
                    service.pin_evidence(task_id, evidence_id)
                    self.console.print(
                        notice(
                            "The evidence will remain prominent in future sessions.",
                            title="Evidence pinned",
                            tone="success",
                        )
                    )
            else:
                self.console.print(
                    notice(
                        "Use ask, search, deeper, improve, note, pin, or back.",
                        title="Unknown Deep Dive action",
                        tone="warning",
                    )
                )
