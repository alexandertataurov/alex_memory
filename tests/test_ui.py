from __future__ import annotations

import tempfile
import time
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from rich.console import Console
from test_ai_pipeline import make_settings

from alex_memory.database import connect
from alex_memory.app import AlexMemoryApp
from alex_memory.retrieval import SearchResult
from alex_memory.tasks.deep_dive.models import EvidenceItem, TaskDeepDiveReport
from alex_memory.tasks.deep_dive.renderer import render_report
from alex_memory.ui.ai import render_ai_progress
from alex_memory.ui.ai_analytics import show_ai_request_monitor
from alex_memory.ui.components import safe_text
from alex_memory.ui.navigation import (
    resolve_command,
    resolve_maintenance_command,
    show_app_header,
    show_main_menu,
)
from alex_memory.runtime_status import RuntimeStatusService
from alex_memory.ui.screens import (
    show_attention,
    show_chat_policies,
    show_daily_brief,
    show_entities,
    show_people,
    show_follow_up_detail,
    show_result_detail,
    show_retrieval_results,
    show_review_queue,
    show_review_detail,
    show_settings,
)


def capture_console(width: int = 120) -> tuple[Console, StringIO]:
    output = StringIO()
    return Console(file=output, force_terminal=False, width=width), output


class NavigationTests(unittest.TestCase):
    def test_command_lookup_keeps_maintenance_out_of_normal_navigation(self) -> None:
        self.assertEqual("contacts", resolve_command("p"))
        self.assertEqual("contacts", resolve_command("people"))
        self.assertEqual("search", resolve_command("s"))
        self.assertEqual("review", resolve_command("r"))
        self.assertEqual("diagnostics", resolve_command("status"))
        self.assertEqual("maintain", resolve_command(":maintain"))
        self.assertIsNone(resolve_command("ask"))
        self.assertIsNone(resolve_command("tasks"))
        self.assertIsNone(resolve_command("today"))
        self.assertEqual("quit", resolve_command("exit"))
        self.assertIsNone(resolve_command("not-a-command"))
        self.assertEqual("resync_profiles", resolve_maintenance_command("full_refresh"))

    def test_home_screen_groups_commands_and_shows_live_health(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            conn = connect(settings)
            try:
                console, output = capture_console()
                show_main_menu(
                    console, RuntimeStatusService(conn, settings).snapshot(None)
                )
                rendered = output.getvalue()
            finally:
                conn.close()
        self.assertIn("STARTING", rendered)
        self.assertIn("People", rendered)
        self.assertIn("Find a person", rendered)
        self.assertIn("Type / to search actions.", rendered)
        self.assertNotIn("Today", rendered)
        self.assertNotIn("Ask Alex Memory", rendered)
        self.assertNotIn(":maintain", rendered)

    def test_header_explains_product_without_configuration_dump(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            console, output = capture_console()
            show_app_header(settings, console)
        rendered = output.getvalue()
        self.assertIn("ALEX MEMORY", rendered)
        self.assertIn("source-backed relationship memory", rendered)
        self.assertNotIn(settings.telegram_api_hash, rendered)


class ScreenStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.settings = make_settings(Path(self.directory.name))
        self.conn = connect(self.settings)

    def tearDown(self) -> None:
        self.conn.close()
        self.directory.cleanup()

    def test_empty_search_and_attention_have_clear_states(self) -> None:
        console, output = capture_console()
        show_retrieval_results([], "unknown thing", console)
        show_attention([], console)
        rendered = output.getvalue()
        self.assertIn("No source-backed results", rendered)
        self.assertIn("Nothing currently needs attention", rendered)

    def test_people_discovery_matches_alias_and_is_person_only(self) -> None:
        now = "2026-08-24T10:00:00+00:00"
        person_id = self.conn.execute(
            "INSERT INTO people(canonical_name,telegram_username,created_at,updated_at) VALUES ('Anna','anna',?,?)",
            (now, now),
        ).lastrowid
        self.conn.execute(
            "INSERT INTO entity_aliases(entity_type,entity_id,alias,normalized_alias,created_at) VALUES ('person',?,'Anya','anya',?)",
            (person_id, now),
        )
        self.conn.execute(
            "INSERT INTO companies(canonical_name,created_at,updated_at) VALUES ('Anya Holdings',?,?)",
            (now, now),
        )
        console, output = capture_console()
        self.assertEqual([person_id], show_people(self.conn, console, "anya"))
        self.assertIn("Anna", output.getvalue())
        self.assertNotIn("Anya Holdings", output.getvalue())

    def test_chat_policy_uses_operator_facing_labels(self) -> None:
        self.conn.execute(
            "INSERT INTO chats(chat_id,title,chat_type) VALUES (7,'Project chat','group')"
        )
        self.conn.execute(
            "INSERT INTO chat_ai_policy(chat_id,mode,reason,updated_at) VALUES (7,'classify_only','archive','now')"
        )
        console, output = capture_console()
        self.assertTrue(show_chat_policies(self.conn, console))
        rendered = output.getvalue()
        self.assertIn("ARCHIVE ONLY", rendered)
        self.assertIn("NEWS ONLY", rendered)

    def test_request_monitor_shows_route_pace_and_request_errors(self) -> None:
        self.conn.execute(
            "INSERT INTO chats(chat_id,title,chat_type) VALUES (7,'Project chat','group')"
        )
        self.conn.execute(
            """INSERT INTO ai_jobs(lane,chat_id,first_message_id,last_message_id,message_count,
               analysis_version,selection_fingerprint,status,provider,model,attempt_count,created_at)
               VALUES ('history',7,1,2,2,2,'fixture-monitor','running','gemini','gemini-test',1,'2026-08-22T10:00:00+00:00')"""
        )
        self.conn.execute(
            """INSERT INTO ai_batches(model,created_at,completed_at,message_count,chat_id,error,
               lane,provider,fallback_used,job_id)
               VALUES ('gemini-test','2026-08-22T10:00:00+00:00','2026-08-22T10:01:00+00:00',2,7,
               'RESOURCE_EXHAUSTED','history','gemini',0,1)"""
        )
        console, output = capture_console()
        show_ai_request_monitor(self.conn, self.settings, console)
        rendered = output.getvalue()
        self.assertIn("AI request monitor", rendered)
        self.assertIn("Eligible routes", rendered)
        self.assertIn("gemini-test", rendered)
        self.assertIn("RESOURCE_EXHAUSTED", rendered)
        self.assertIn("Gemini · 1h", rendered)
        self.assertNotIn("gemma-4-31b-it", rendered)
        self.assertIn("Quota snapshot", rendered)
        self.assertNotIn("Today's model quotas", rendered)

    def test_review_queue_shows_rationale_and_message_provenance(self) -> None:
        self.conn.execute(
            """INSERT INTO review_queue(review_type,subject_type,payload_json,confidence,created_at)
               VALUES ('graph_link','ai_item',
               '{"reason":"project ambiguity","chat_id":8,"message_id":4}',0.8,'now')"""
        )
        console, output = capture_console()
        show_review_queue(self.conn, console)
        rendered = output.getvalue()
        self.assertIn("Rationale / evidence", rendered)
        self.assertIn("project ambiguity", rendered)
        self.assertIn("chat 8 / msg 4", rendered)

    def test_review_detail_resolves_source_prefixed_message_fields(self) -> None:
        self.conn.execute(
            "INSERT INTO chats(chat_id,title,chat_type) VALUES (8,'Review source','user')"
        )
        self.conn.execute(
            "INSERT INTO messages(chat_id,message_id,date,text) VALUES (8,4,'2026-08-22','Exact review source')"
        )
        review_id = self.conn.execute(
            """INSERT INTO review_queue(review_type,subject_type,payload_json,confidence,created_at)
               VALUES ('graph_link','ai_item',?,0.8,'now')""",
            (
                '{"reason":"project ambiguity","source_chat_id":8,"source_message_id":4}',
            ),
        ).lastrowid
        console, output = capture_console()
        self.assertTrue(show_review_detail(self.conn, int(review_id), console))
        self.assertIn("Exact review source", output.getvalue())

    def test_entity_picker_only_shows_requested_type(self) -> None:
        now = "2026-08-22T10:00:00+00:00"
        self.conn.execute(
            "INSERT INTO people(canonical_name,created_at,updated_at) "
            "VALUES ('Alice',?,?)",
            (now, now),
        )
        self.conn.execute(
            "INSERT INTO projects(canonical_name,created_at,updated_at) "
            "VALUES ('Atlas',?,?)",
            (now, now),
        )
        self.conn.commit()
        console, output = capture_console()
        show_entities(self.conn, console, "project")
        rendered = output.getvalue()
        self.assertIn("Atlas", rendered)
        self.assertNotIn("Alice", rendered)

    def test_entity_picker_filters_and_discloses_the_bounded_result_count(self) -> None:
        now = "2026-08-22T10:00:00+00:00"
        self.conn.executemany(
            "INSERT INTO people(canonical_name,created_at,updated_at) VALUES (?,?,?)",
            [(f"Alice {index}", now, now) for index in range(3)],
        )
        console, output = capture_console()
        self.assertTrue(show_entities(self.conn, console, "person", "Alice", limit=2))
        rendered = output.getvalue()
        self.assertIn("2 of 3 canonical records", rendered)
        self.assertIn("Refine the search", rendered)

    def test_entity_and_chat_pickers_are_filterable_and_disclose_bounds(self) -> None:
        now = "2026-08-22T10:00:00+00:00"
        self.conn.executemany(
            "INSERT INTO people(canonical_name,created_at,updated_at) VALUES (?,?,?)",
            [(f"Person {index:03}", now, now) for index in range(62)],
        )
        self.conn.execute(
            "INSERT INTO people(canonical_name,created_at,updated_at) VALUES ('Target',?,?)",
            (now, now),
        )
        self.conn.executemany(
            "INSERT INTO chats(chat_id,title,chat_type) VALUES (?,?,'user')",
            [(index, f"Chat {index:03}") for index in range(62)],
        )
        console, output = capture_console()
        self.assertTrue(show_entities(self.conn, console, "person", "target"))
        self.assertTrue(show_chat_policies(self.conn, console, "chat"))
        rendered = output.getvalue()
        self.assertIn("1 of 1 canonical records", rendered)
        self.assertIn("60 of 62 chats", rendered)
        self.assertIn("Refine the search", rendered)

    def test_selected_message_result_shows_exact_source_text(self) -> None:
        self.conn.execute(
            "INSERT INTO chats(chat_id,title,chat_type) VALUES (7,'Source chat','user')"
        )
        self.conn.execute(
            "INSERT INTO messages(chat_id,message_id,date,text) VALUES (7,3,'2026-08-22','Exact source text')"
        )
        from alex_memory.retrieval import SearchResult

        console, output = capture_console()
        show_result_detail(
            self.conn,
            SearchResult("message", "Snippet", "short", "2026-08-22", 1, 7, 3),
            console,
        )
        self.assertIn("Exact source text", output.getvalue())

    def test_follow_up_detail_opens_its_linked_task(self) -> None:
        now = "2026-08-22T10:00:00+00:00"
        task_id = self.conn.execute(
            """INSERT INTO tasks(title,normalized_title,details,status,owner,confidence,created_at,updated_at)
               VALUES ('Call client','call client','Awaiting a reply','waiting','me',1,?,?)""",
            (now, now),
        ).lastrowid
        follow_up_id = self.conn.execute(
            """INSERT INTO follow_ups(title,status,priority,task_id,reason,confidence,dedupe_key,created_at,updated_at)
               VALUES ('Follow up: Call client','open','high',?,'waiting task',1,'test-follow-up',?,?)""",
            (task_id, now, now),
        ).lastrowid
        console, output = capture_console()
        self.assertTrue(show_follow_up_detail(self.conn, int(follow_up_id), console))
        self.assertIn("Awaiting a reply", output.getvalue())

    def test_settings_table_is_rendered(self) -> None:
        console, output = capture_console()
        show_settings(self.settings, console)
        rendered = output.getvalue()
        self.assertIn("Read-only runtime configuration", rendered)
        self.assertIn("Primary AI", rendered)

    def test_deep_dive_uses_safe_text_in_a_narrow_terminal(self) -> None:
        report = TaskDeepDiveReport(
            task={"task_id": 8, "title": "[red]Untrusted task[/red]"},
            session_id=4,
            as_of="2026-08-22T12:00:00+00:00",
            concepts=["hedge"],
            executive_summary="[bold]Untrusted summary[/bold]",
            origin=["chat 10"],
            current_state=["Status: open"],
            people=[],
            projects=[],
            companies=[],
            known_facts=["[green]raw fact[/green]"],
            unknowns=["No due date"],
            open_loops=[],
            recommendations=[],
            timeline=[
                EvidenceItem(
                    "E-message-10-2",
                    "message",
                    "Chat",
                    "[blue]raw source text[/blue]",
                    "2026-08-22",
                    10,
                    2,
                )
            ],
            evidence=[],
            notes=[],
            pinned_evidence_ids={"E-message-10-2"},
            diagnostics={"selected_evidence": 1},
        )
        console, output = capture_console(width=52)
        render_report(report, console)
        rendered = output.getvalue()
        self.assertIn("[red]Untrusted task[/red]", rendered)
        self.assertIn("Task Deep Dive #8", rendered)
        wide_console, wide_output = capture_console()
        render_report(report, wide_console)
        wide_rendered = wide_output.getvalue()
        self.assertIn("[blue]raw source text[/blue]", wide_rendered)

    def test_untrusted_text_has_no_rich_markup_spans(self) -> None:
        rendered = safe_text("[bold red]source text[/bold red]")
        self.assertEqual("[bold red]source text[/bold red]", rendered.plain)
        self.assertEqual([], rendered.spans)

    def test_task_confirmation_shows_canonical_and_source_evidence(self) -> None:
        self.conn.execute(
            "INSERT INTO chats(chat_id,title,chat_type) VALUES (1,'Ilya','user')"
        )
        self.conn.execute(
            "INSERT INTO messages(chat_id,message_id,date,text) "
            "VALUES (1,1,'2026-08-24','Please send the signed invoice.')"
        )
        task_id = self.conn.execute(
            """INSERT INTO tasks(
                    title,normalized_title,details,status,owner,source_chat_id,
                    due_date,confidence,created_at,updated_at
                ) VALUES ('Send invoice','send invoice','Requested invoice','open','me',1,
                          '2026-08-25',0.9,'2026-08-24','2026-08-24')"""
        ).lastrowid
        batch_id = self.conn.execute(
            """INSERT INTO ai_batches(model,created_at,message_count,chat_id)
               VALUES ('test','2026-08-24',1,1)"""
        ).lastrowid
        item_id = self.conn.execute(
            """INSERT INTO ai_items(
                   batch_id,kind,title,details,status,owner,confidence,source_chat_id,
                   source_message_id,created_at,dedupe_key
               ) VALUES (?, 'task', 'Send invoice', 'Requested invoice', 'open', 'me',
                         0.9, 1, 1, '2026-08-24', 'task-source')""",
            (batch_id,),
        ).lastrowid
        self.conn.execute(
            "UPDATE tasks SET source_item_id=? WHERE task_id=?", (item_id, task_id)
        )
        console, output = capture_console()
        app = AlexMemoryApp(self.settings, console)
        app.conn = self.conn

        with patch("alex_memory.app.Prompt.ask", return_value="back"):
            self.assertFalse(app._confirm_task_update(int(task_id), "done"))

        rendered = output.getvalue()
        self.assertIn("Evidence detail", rendered)
        self.assertIn("Requested invoice", rendered)
        self.assertIn("Please send the signed invoice.", rendered)

    def test_result_drill_down_uses_the_selected_source_number(self) -> None:
        self.conn.execute(
            "INSERT INTO messages(chat_id,message_id,date,text) "
            "VALUES (2,1,'2026-08-24','Exact source text.')"
        )
        console, output = capture_console()
        app = AlexMemoryApp(self.settings, console)
        app.conn = self.conn
        result = SearchResult(
            "message", "Source", "", "2026-08-24", 1, chat_id=2, message_id=1
        )

        with patch("alex_memory.app.Prompt.ask", return_value="1"):
            app._inspect_retrieval_result([result], "Result number")

        self.assertIn("Exact source text.", output.getvalue())

    def test_daily_brief_is_responsive_and_keeps_source_text_literal(self) -> None:
        brief = {
            "new_tasks": [
                {
                    "task_id": 3,
                    "title": "[red]Call Michael[/red]",
                    "status": "open",
                    "due_date": "2026-08-23",
                }
            ],
            "updates": [],
            "open_tasks": [],
            "follow_ups": [],
            "stale_projects": [],
            "facts": [],
        }
        for width in (64, 120):
            console, output = capture_console(width=width)
            show_daily_brief(brief, console)
            rendered = output.getvalue()
            self.assertIn("Daily brief", rendered)
            self.assertIn("[red]Call Michael[/red]", rendered)
            self.assertIn("Open & waiting", rendered)

    def test_progress_views_show_completion_and_fit_narrow_terminals(self) -> None:
        console, output = capture_console(width=72)
        console.print(
            render_ai_progress(
                4,
                2,
                20,
                10,
                3,
                0,
                time.monotonic() - 2,
                self.settings,
            )
        )
        rendered = output.getvalue()
        self.assertIn("2/4", rendered)
        self.assertIn("10/20", rendered)


class LocalModeTests(unittest.IsolatedAsyncioTestCase):
    async def test_telegram_startup_failure_keeps_local_reads_available(self) -> None:
        class FailedClient:
            async def start(self) -> None:
                raise RuntimeError("network unavailable")

            def is_connected(self) -> bool:
                return False

        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            console, output = capture_console()
            app = AlexMemoryApp(settings, console)
            with patch("alex_memory.app.TelegramClient", return_value=FailedClient()):
                await app.start()
            try:
                self.assertIsNotNone(app.conn)
                self.assertIsNone(app.live_sync)
                self.assertIn("Local reads remain available", output.getvalue())
            finally:
                await app.close()
