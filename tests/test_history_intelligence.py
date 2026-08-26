from __future__ import annotations

import asyncio
import tempfile
import unittest
from datetime import datetime
from io import StringIO
from pathlib import Path

from rich.console import Console

from alex_memory.ai.history import FullHistoryAnalyzer
from alex_memory.ai.repository import history_coverage
from alex_memory.classification import (
    _context_signals,
    classify_message,
    processing_route,
    save_classification,
    temporal_relevance_as_of,
)
from alex_memory.context import ContextGraphImprover, graph_diagnostics
from alex_memory.context.segments import ConversationSegmenter
from alex_memory.database import connect
from alex_memory.models import AIAnalysisResult, AIMessage
from alex_memory.operational import (
    EntityResolver,
    normalize_task_title,
    resolve_review_item,
)

from test_ai_pipeline import make_settings


class FakeRouter:
    def __init__(self, failures: int = 0):
        self.requests = 0
        self.fallbacks = 0
        self.failures = failures

    async def analyze(self, _batch):
        self.requests += 1
        if self.requests <= self.failures:
            raise RuntimeError("provider temporarily unavailable")
        return AIAnalysisResult("test", "test", "No durable change.", [])


class PausingRouter(FakeRouter):
    def __init__(self):
        super().__init__()
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def analyze(self, _batch):
        self.requests += 1
        self.started.set()
        await self.release.wait()
        return AIAnalysisResult("test", "test", "No durable change.", [])


class HistoryIntelligenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_full_history_continues_after_one_failure_without_duplicate_coverage(
        self,
    ):
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(
                Path(directory),
                history_internal_batch_messages=2,
                history_internal_batch_chars=2000,
            )
            conn = connect(settings)
            self.addAsyncCleanup(_close, conn)
            conn.execute(
                "INSERT INTO chats(chat_id,title,chat_type) VALUES (1,'Michael','user')"
            )
            conn.executemany(
                "INSERT INTO messages(chat_id,message_id,date,text) VALUES (1,?,?,?)",
                [
                    (number, f"2025-01-0{number}T10:00:00+00:00", f"Message {number}")
                    for number in range(1, 6)
                ],
            )
            conn.commit()
            console = Console(file=StringIO(), force_terminal=False)

            first = await FullHistoryAnalyzer(
                conn, settings, console, FakeRouter(1)
            ).analyze_all()
            self.assertTrue(first.complete)
            self.assertEqual(5, first.coverage["classified"])
            self.assertEqual(5, first.coverage["semantic"])
            self.assertEqual(
                5, conn.execute("SELECT COUNT(*) FROM ai_message_state").fetchone()[0]
            )
            self.assertEqual(5, history_coverage(conn, settings)["classified"])
            output = console.file.getvalue()
            self.assertIn("Provider request in flight", output)
            self.assertIn("History AI monitor", output)
            self.assertIn("Request state", output)
            self.assertIn("Elapsed", output)
            self.assertIn("Committed", output)
            self.assertIn("History analysis continuing", output)

    async def test_history_pauses_after_three_consecutive_provider_failures(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory), history_internal_batch_messages=2)
            conn = connect(settings)
            self.addAsyncCleanup(_close, conn)
            conn.execute(
                "INSERT INTO chats(chat_id,title,chat_type) VALUES (1,'Michael','user')"
            )
            conn.executemany(
                "INSERT INTO messages(chat_id,message_id,date,text) VALUES (1,?,?,?)",
                [(number, "2026-08-22", "Message") for number in range(1, 6)],
            )
            output = StringIO()
            router = FakeRouter(3)

            report = await FullHistoryAnalyzer(
                conn, settings, Console(file=output, force_terminal=False), router
            ).analyze_all()

            self.assertFalse(report.complete)
            self.assertEqual(3, report.failures)
            self.assertEqual(3, router.requests)
            self.assertIn("Three provider failures recorded", output.getvalue())

    async def test_history_yields_before_provider_work_when_live_queue_is_busy(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory), history_internal_batch_messages=2)
            conn = connect(settings)
            self.addAsyncCleanup(_close, conn)
            conn.execute(
                "INSERT INTO chats(chat_id,title,chat_type) VALUES (1,'Michael','user')"
            )
            conn.execute(
                "INSERT INTO messages(chat_id,message_id,date,text) VALUES (1,1,'2026-08-22','Message')"
            )
            conn.commit()
            router = FakeRouter()
            report = await FullHistoryAnalyzer(
                conn,
                settings,
                Console(file=StringIO(), force_terminal=False),
                router,
                should_continue=lambda: False,
            ).analyze_all()
            self.assertFalse(report.complete)
            self.assertEqual(0, router.requests)
            self.assertEqual(
                0,
                conn.execute(
                    "SELECT COUNT(*) FROM ai_jobs WHERE lane='history'"
                ).fetchone()[0],
            )

    async def test_history_marks_only_the_active_provider_job_running(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(
                Path(directory),
                history_internal_concurrency=2,
                history_internal_batch_messages=1,
            )
            conn = connect(settings)
            self.addAsyncCleanup(_close, conn)
            conn.execute(
                "INSERT INTO chats(chat_id,title,chat_type) VALUES (1,'Michael','user')"
            )
            conn.executemany(
                "INSERT INTO messages(chat_id,message_id,date,text) VALUES (1,?,?,?)",
                [(number, "2026-08-22", "Message") for number in range(1, 4)],
            )
            conn.commit()
            router = PausingRouter()
            analysis = asyncio.create_task(
                FullHistoryAnalyzer(
                    conn,
                    settings,
                    Console(file=StringIO(), force_terminal=False),
                    router,
                ).analyze_all()
            )

            await asyncio.wait_for(router.started.wait(), timeout=1)
            active = conn.execute(
                "SELECT status, COUNT(*) FROM ai_jobs GROUP BY status ORDER BY status"
            ).fetchall()
            self.assertEqual([("pending", 1), ("running", 1)], active)

            router.release.set()
            report = await asyncio.wait_for(analysis, timeout=2)
            self.assertTrue(report.complete)

    async def test_interrupting_live_request_requeues_without_a_false_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory), history_internal_batch_messages=1)
            conn = connect(settings)
            self.addAsyncCleanup(_close, conn)
            conn.execute(
                "INSERT INTO chats(chat_id,title,chat_type) VALUES (1,'Michael','user')"
            )
            conn.execute(
                "INSERT INTO messages(chat_id,message_id,date,text) VALUES (1,1,'2026-08-22','Message')"
            )
            conn.commit()
            router = PausingRouter()
            analysis = asyncio.create_task(
                FullHistoryAnalyzer(
                    conn,
                    settings,
                    Console(file=StringIO(), force_terminal=False),
                    router,
                ).analyze_all()
            )

            await asyncio.wait_for(router.started.wait(), timeout=1)
            analysis.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await analysis

            self.assertEqual(
                "pending",
                conn.execute(
                    "SELECT status FROM ai_jobs WHERE lane='history'"
                ).fetchone()[0],
            )
            self.assertEqual(
                0,
                conn.execute(
                    "SELECT COUNT(*) FROM ai_batches WHERE error IS NOT NULL"
                ).fetchone()[0],
            )


class ClassificationAndGraphTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.settings = make_settings(Path(self.directory.name))
        self.conn = connect(self.settings)

    def tearDown(self):
        self.conn.close()
        self.directory.cleanup()

    def test_waiting_context_disambiguates_short_state_change(self):
        self.conn.execute(
            "INSERT INTO chats(chat_id,title,chat_type) VALUES (1,'Michael','user')"
        )
        self.conn.execute(
            """INSERT INTO tasks(title,normalized_title,status,owner,source_chat_id,confidence,created_at,updated_at)
               VALUES ('Corporate documents','corporate documents','waiting','other',1,1.0,'2026-01-01','2026-01-01')"""
        )
        result = classify_message(
            self.conn,
            AIMessage(1, 2, 8, "2026-01-02", "sent", False, "Michael", "user"),
        )
        self.assertEqual("update", result.content_type)
        self.assertEqual("high", result.importance)
        self.assertTrue(result.potential_state_change)

    def test_context_changes_business_scope_and_historical_relevance(self):
        self.conn.execute(
            "INSERT INTO chats(chat_id,title,chat_type) VALUES (1,'Michael','user')"
        )
        self.conn.execute(
            """INSERT INTO tasks(title,normalized_title,status,owner,source_chat_id,related_project_id,confidence,created_at,updated_at)
               VALUES ('Project work','project work','open','me',1,1,1.0,'2026-01-01','2026-01-01')"""
        )
        result = classify_message(
            self.conn,
            AIMessage(
                1,
                2,
                8,
                "2024-01-02T00:00:00+00:00",
                "Approved",
                False,
                "Michael",
                "user",
            ),
        )
        self.assertEqual("business", result.content_scope)
        self.assertEqual("dated", result.temporal_relevance)
        self.assertEqual(
            "historical",
            temporal_relevance_as_of(
                "2024-01-02T00:00:00+00:00",
                datetime.fromisoformat("2026-01-02T00:00:00+00:00"),
            ),
        )
        self.assertEqual("decision", result.content_type)

    def test_forwarded_news_isolated_from_project_state_routing(self):
        self.conn.execute(
            "INSERT INTO chats(chat_id,title,chat_type) VALUES (9,'Michael','user')"
        )
        self.conn.execute(
            """INSERT INTO messages(chat_id,message_id,date,text,is_forwarded,forward_source)
               VALUES (9,1,'2026-01-02','Bank announces new policy.',1,'News desk')"""
        )
        result = classify_message(
            self.conn,
            AIMessage(
                9,
                1,
                8,
                "2026-01-02",
                "Bank announces new policy.",
                False,
                "Michael",
                "user",
            ),
        )
        self.assertEqual("news", result.content_type)
        self.assertEqual("external_news", result.information_scope)
        self.assertFalse(result.potential_state_change)

    def test_forwarded_private_request_keeps_its_evidence_scope_and_route(self):
        self.conn.execute(
            "INSERT INTO chats(chat_id,title,chat_type) VALUES (10,'Private','user')"
        )
        self.conn.execute(
            """INSERT INTO messages(chat_id,message_id,date,text,is_forwarded)
               VALUES (10,1,'2026-01-02','Please send the signed contract.',1)"""
        )
        result = classify_message(
            self.conn,
            AIMessage(
                10,
                1,
                8,
                "2026-01-02",
                "Please send the signed contract.",
                False,
                "Private",
                "user",
            ),
        )
        self.assertTrue(result.is_forwarded)
        self.assertEqual("business", result.information_scope)
        self.assertEqual("request", result.content_type)

    def test_actionable_questions_and_private_group_messages_are_not_misrouted(self):
        self.conn.execute(
            "INSERT INTO chats(chat_id,title,chat_type) VALUES (11,'Team','group')"
        )
        request = classify_message(
            self.conn,
            AIMessage(
                11,
                1,
                8,
                "2026-01-02",
                "Can you send the contract?",
                False,
                "Team",
                "group",
            ),
        )
        short_group_message = classify_message(
            self.conn,
            AIMessage(
                11,
                2,
                8,
                "2026-01-02",
                "Thanks",
                False,
                "Team",
                "group",
            ),
        )
        self.assertEqual("request", request.content_type)
        self.assertEqual("operational", processing_route(request))
        self.assertEqual("private_group", short_group_message.information_scope)

    def test_russian_and_georgian_operational_phrases_are_classified_locally(self):
        russian = classify_message(
            self.conn,
            AIMessage(
                12,
                1,
                8,
                "2026-01-02",
                "Пожалуйста, отправьте счёт.",
                False,
                "Contact",
                "user",
            ),
        )
        georgian = classify_message(
            self.conn,
            AIMessage(
                12,
                2,
                8,
                "2026-01-02",
                "გადახდა შესრულებულია.",
                False,
                "Contact",
                "user",
            ),
        )
        self.assertEqual("request", russian.content_type)
        self.assertEqual("payment", georgian.content_type)
        self.assertEqual("operational", processing_route(georgian))

    def test_hand_reviewed_classification_fixture_has_no_unknown_operational_cases(
        self,
    ):
        fixtures = [
            ("Please send the contract.", "request"),
            ("I will share the final version.", "promise"),
            ("We agreed to proceed.", "decision"),
            ("The payment was transferred.", "payment"),
            ("Meeting tomorrow at 10.", "meeting"),
            ("Пожалуйста, отправьте счёт.", "request"),
            ("გადახდა შესრულებულია.", "payment"),
        ]
        results = [
            classify_message(
                self.conn,
                AIMessage(
                    14,
                    index,
                    8,
                    "2026-01-02",
                    text,
                    False,
                    "Contact",
                    "user",
                ),
            )
            for index, (text, _) in enumerate(fixtures, start=1)
        ]
        self.assertEqual(
            [expected for _, expected in fixtures],
            [result.content_type for result in results],
        )
        self.assertEqual(
            0, sum(result.information_scope == "unknown" for result in results)
        )

    def test_context_signals_use_source_time_not_reclassification_time(self):
        self.conn.execute(
            "INSERT INTO chats(chat_id,title,chat_type) VALUES (13,'Michael','user')"
        )
        self.conn.executemany(
            """INSERT INTO messages(chat_id,message_id,date,text)
               VALUES (13,?,?,?)""",
            [
                (1, "2024-01-01", "Old request"),
                (2, "2026-01-01", "New request"),
            ],
        )
        self.conn.executemany(
            """INSERT INTO message_classifications(
                   chat_id,message_id,conversation_type,content_type,actionability,
                   importance,content_scope,information_scope,temporal_relevance,
                   potential_state_change,is_forwarded,topic_json,classifier_type,
                   confidence,classification_version,context_version,context_stale,
                   classified_at
               ) VALUES (13,?,'personal','request','actionable','high','personal',
                         'personal','dated',1,0,'[]','test',1.0,2,1,0,?)""",
            [(1, "2026-08-24"), (2, "2024-01-01")],
        )
        self.assertEqual(
            1,
            _context_signals(self.conn, 13, "2026-01-01", 2)["recent_high_updates"],
        )

    def test_graph_diagnostics_report_routes_and_unclassified_backlog(self):
        self.conn.execute(
            "INSERT INTO chats(chat_id,title,chat_type) VALUES (7,'News','user')"
        )
        self.conn.executemany(
            "INSERT INTO messages(chat_id,message_id,text,is_forwarded) VALUES (7,?,?,?)",
            [(1, "Bank announces policy", 1), (2, "Not yet classified", 0)],
        )
        news = AIMessage(
            7, 1, None, None, "Bank announces policy", False, "News", "user"
        )
        save_classification(self.conn, news, classify_message(self.conn, news))

        diagnostics = graph_diagnostics(self.conn)
        self.assertEqual(1, diagnostics["route_news_memory"])
        self.assertEqual(1, diagnostics["unclassified_messages"])

    def test_temporal_segments_scope_only_the_matching_chat_period(self):
        resolver = EntityResolver(self.conn)
        first = resolver.entity("project", "Project A", source="manual")
        second = resolver.entity("project", "Project B", source="manual")
        assert first and second
        self.conn.execute(
            "INSERT INTO chats(chat_id,title,chat_type) VALUES (9,'Michael','user')"
        )
        self.conn.executemany(
            """INSERT INTO tasks(title,normalized_title,status,owner,related_project_id,
               source_chat_id,confidence,created_at,updated_at)
               VALUES (?,?,'open','me',?,9,1.0,?,?)""",
            [
                ("A January", "a january", first, "2024-01-01", "2024-01-01"),
                ("B May", "b may", second, "2026-05-01", "2026-05-01"),
                ("A August", "a august", first, "2026-08-01", "2026-08-01"),
            ],
        )
        self.assertEqual(3, ConversationSegmenter(self.conn).rebuild_chat(9))
        may = classify_message(
            self.conn,
            AIMessage(
                9, 1, 8, "2026-05-15T00:00:00+00:00", "Sent.", False, "Michael", "user"
            ),
        )
        inactive = classify_message(
            self.conn,
            AIMessage(
                9, 2, 8, "2025-06-15T00:00:00+00:00", "Sent.", False, "Michael", "user"
            ),
        )
        self.assertEqual("project", may.information_scope)
        self.assertEqual("personal", inactive.information_scope)

    def test_graph_improvement_is_provenance_backed_and_idempotent(self):
        now = "2026-01-01T00:00:00+00:00"
        resolver = EntityResolver(self.conn)
        person = resolver.person("Michael", source="manual")
        project = resolver.entity("project", "Georgia LP", source="manual")
        assert person and project
        self.conn.execute(
            "INSERT INTO chats(chat_id,title,chat_type) VALUES (1,'Michael','user')"
        )
        self.conn.execute(
            "INSERT INTO messages(chat_id,message_id,date,text) VALUES (1,1,?,'Docs sent')",
            (now,),
        )
        self.conn.execute(
            """INSERT INTO tasks(title,normalized_title,status,owner,related_person_id,related_project_id,
               source_chat_id,confidence,created_at,updated_at)
               VALUES ('Receive docs',?,'waiting','other',?,?,1,1.0,?,?)""",
            (normalize_task_title("Receive docs"), person, project, now, now),
        )
        self.conn.commit()
        first = ContextGraphImprover(self.conn).improve()
        second = ContextGraphImprover(self.conn).improve()
        self.assertEqual(2, first.relationships_added)
        self.assertEqual(0, second.relationships_added)
        self.assertEqual(2, graph_diagnostics(self.conn)["relationships"])

    def test_graph_uses_accepted_item_links_and_queues_ambiguous_chat_links(self):
        now = "2026-01-01T00:00:00+00:00"
        resolver = EntityResolver(self.conn)
        person = resolver.person("Michael", source="manual")
        project = resolver.entity("project", "Georgia LP", source="manual")
        assert person and project
        self.conn.execute(
            "INSERT INTO chats(chat_id,title,chat_type) VALUES (1,'Michael','user')"
        )
        self.conn.executemany(
            "INSERT INTO messages(chat_id,message_id,date,text) VALUES (1,?,?,?)",
            [(1, now, "Approved"), (2, now, "Documents")],
        )
        self.conn.execute(
            """INSERT INTO tasks(title,normalized_title,status,owner,related_project_id,source_chat_id,confidence,created_at,updated_at)
               VALUES ('Georgia task','georgia task','open','me',?,1,1.0,?,?)""",
            (project, now, now),
        )
        self.conn.executemany(
            """INSERT INTO message_classifications(chat_id,message_id,conversation_type,content_type,actionability,importance,
               content_scope,temporal_relevance,potential_state_change,topic_json,classifier_type,confidence,classification_version,
               context_version,context_stale,classified_at)
               VALUES (1,?,'personal','decision','reference','high','business','current',1,'[]','test',1.0,1,1,0,?)""",
            [(1, now), (2, now)],
        )
        self.conn.executemany(
            """INSERT INTO ai_items(batch_id,kind,title,details,status,owner,confidence,source_chat_id,source_message_id,
               source_date,created_at,dedupe_key,person_id,project_id)
               VALUES (1,'important_fact',?,'detail','informational','unknown',0.95,1,?,?,?, ?,?,?)""",
            [
                (
                    "Direct project evidence",
                    1,
                    now,
                    now,
                    "direct-link",
                    person,
                    project,
                ),
                (
                    "Ambiguous project evidence",
                    2,
                    now,
                    now,
                    "review-link",
                    person,
                    None,
                ),
            ],
        )
        self.conn.commit()
        report = ContextGraphImprover(self.conn).improve(source_chat_id=1)
        self.assertGreaterEqual(report.relationships_added, 1)
        self.assertEqual(1, report.review_candidates_created)
        self.assertEqual(1, graph_diagnostics(self.conn)["graph_link_candidates"])

    def test_graph_repairs_strongly_anchored_orphan_task_event_and_fact(self):
        now = "2026-01-01T00:00:00+00:00"
        resolver = EntityResolver(self.conn)
        person = resolver.person("Michael", source="manual")
        project = resolver.entity("project", "Georgia LP", source="manual")
        assert person and project
        self.conn.execute(
            "INSERT INTO chats(chat_id,title,chat_type) VALUES (1,'Michael','user')"
        )
        self.conn.executemany(
            """INSERT INTO tasks(title,normalized_title,status,owner,related_project_id,
               source_chat_id,confidence,created_at,updated_at)
               VALUES (?,?,'open','me',?,1,1.0,?,?)""",
            [
                ("Anchor one", "anchor one", project, now, now),
                ("Anchor two", "anchor two", project, now, now),
            ],
        )
        orphan_task = self.conn.execute(
            """INSERT INTO tasks(title,normalized_title,status,owner,source_chat_id,
               confidence,created_at,updated_at)
               VALUES ('Unlinked work','unlinked work','open','me',1,1.0,?,?)""",
            (now, now),
        ).lastrowid
        event_id = self.conn.execute(
            """INSERT INTO context_events(event_type,title,observed_at,source_chat_id,confidence,created_at)
               VALUES ('update','Unlinked event',?,1,1.0,?)""",
            (now, now),
        ).lastrowid
        self.conn.execute(
            """INSERT INTO context_facts(subject_type,subject_id,predicate,value_json,valid_from,
               observed_at,confidence,source_chat_id,created_at,updated_at)
               VALUES ('person',?,'topic','{}',?,?,1.0,1,?,?)""",
            (person, now, now, now, now),
        )
        self.conn.commit()

        first = ContextGraphImprover(self.conn).improve(source_chat_id=1)
        second = ContextGraphImprover(self.conn).improve(source_chat_id=1)

        self.assertEqual(
            project,
            self.conn.execute(
                "SELECT related_project_id FROM tasks WHERE task_id=?", (orphan_task,)
            ).fetchone()[0],
        )
        self.assertEqual(
            1,
            self.conn.execute(
                """SELECT COUNT(*) FROM relationships
                   WHERE from_type='task' AND from_id=? AND to_type='project'
                     AND to_id=? AND relationship_type='supports'""",
                (orphan_task, project),
            ).fetchone()[0],
        )
        self.assertEqual(
            project,
            self.conn.execute(
                "SELECT project_id FROM context_events WHERE event_id=?", (event_id,)
            ).fetchone()[0],
        )
        self.assertGreaterEqual(first.relationships_added, 5)
        self.assertEqual(0, second.relationships_added)

    def test_graph_queues_single_anchor_orphan_repairs_for_review(self):
        now = "2026-01-01T00:00:00+00:00"
        resolver = EntityResolver(self.conn)
        project = resolver.entity("project", "Georgia LP", source="manual")
        assert project
        self.conn.execute(
            "INSERT INTO chats(chat_id,title,chat_type) VALUES (1,'Michael','user')"
        )
        self.conn.execute(
            """INSERT INTO tasks(title,normalized_title,status,owner,related_project_id,
               source_chat_id,confidence,created_at,updated_at)
               VALUES ('Anchor','anchor','open','me',?,1,1.0,?,?)""",
            (project, now, now),
        )
        orphan_task = self.conn.execute(
            """INSERT INTO tasks(title,normalized_title,status,owner,source_chat_id,
               confidence,created_at,updated_at)
               VALUES ('Unlinked work','unlinked work','open','me',1,1.0,?,?)""",
            (now, now),
        ).lastrowid
        self.conn.commit()

        report = ContextGraphImprover(self.conn).improve(source_chat_id=1)

        self.assertEqual(1, report.review_candidates_created)
        self.assertIsNone(
            self.conn.execute(
                "SELECT related_project_id FROM tasks WHERE task_id=?", (orphan_task,)
            ).fetchone()[0]
        )
        self.assertEqual(
            "graph_task_link",
            self.conn.execute("SELECT review_type FROM review_queue").fetchone()[0],
        )
        review_id = self.conn.execute("SELECT review_id FROM review_queue").fetchone()[
            0
        ]
        resolve_review_item(self.conn, review_id, "accept")
        self.assertEqual(
            project,
            self.conn.execute(
                "SELECT related_project_id FROM tasks WHERE task_id=?", (orphan_task,)
            ).fetchone()[0],
        )

    def test_graph_repairs_unambiguous_temporal_fact_intervals(self):
        resolver = EntityResolver(self.conn)
        person = resolver.person("Michael", source="manual")
        assert person
        self.conn.executemany(
            """INSERT INTO context_facts(subject_type,subject_id,predicate,value_json,valid_from,
               observed_at,valid_to,is_current,confidence,created_at,updated_at)
               VALUES ('person',?,'availability_status','{}',?,?,?,?,?,?,?)""",
            [
                (person, "2026-01-01", "now", None, 1, 1.0, "now", "now"),
                (
                    person,
                    "2026-02-01",
                    "now",
                    "2026-03-01",
                    0,
                    1.0,
                    "now",
                    "now",
                ),
            ],
        )

        ContextGraphImprover(self.conn).improve()

        rows = self.conn.execute(
            "SELECT valid_from,valid_to,is_current FROM context_facts ORDER BY valid_from"
        ).fetchall()
        self.assertEqual(
            [("2026-01-01", "2026-02-01", 0), ("2026-02-01", None, 1)], rows
        )


async def _close(conn) -> None:
    conn.close()
