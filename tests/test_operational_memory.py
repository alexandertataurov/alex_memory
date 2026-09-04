from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from alex_memory.ai.repository import history_coverage, save_ai_success
from alex_memory.ai.context import add_contextual_preamble
from alex_memory.classification import classify_message, save_classification
from alex_memory.context.refresh import enqueue_context_refresh, refresh_pending_context
from alex_memory.database import connect
from alex_memory.models import AIBatch, AIMessage
from alex_memory.operational import (
    _likely_duplicate_projects,
    EntityResolver,
    TaskReconciler,
    backfill_direct_chat_identities,
    backfill_task_project_links,
    direct_chat_person,
    generate_daily_brief,
    identity_reconciliation_preview,
    load_daily_brief,
    manually_update_task,
    normalize_alias,
    process_ai_batch,
    resolve_review_item,
    resolve_task_project,
)
from alex_memory.repair import (
    apply_context_repair,
    apply_fts_repair,
    apply_project_health_repair,
    apply_segment_repair,
    apply_task_lifecycle_repair,
    apply_task_project_repair,
    derived_state_repair_dry_run,
    derived_state_repair_inventory,
)
from alex_memory.schema_support import fts_index_health

from test_ai_pipeline import make_settings


class OperationalMemoryTests(unittest.TestCase):
    def test_explicit_global_refresh_uses_the_invalidation_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            conn = connect(settings)
            try:
                enqueue_context_refresh(conn, {("global", 0)})

                self.assertEqual(
                    ("pending", 1),
                    conn.execute(
                        """SELECT status,requested_revision FROM context_invalidations
                           WHERE scope_type='global' AND scope_id=0"""
                    ).fetchone(),
                )
                self.assertEqual(
                    1, asyncio.run(refresh_pending_context(conn, settings))
                )
                self.assertEqual(
                    ("clean", 1, 1),
                    conn.execute(
                        """SELECT status,requested_revision,completed_revision
                           FROM context_invalidations
                           WHERE scope_type='global' AND scope_id=0"""
                    ).fetchone(),
                )
                self.assertEqual(
                    1,
                    conn.execute(
                        "SELECT COUNT(*) FROM global_state_snapshots"
                    ).fetchone()[0],
                )
            finally:
                conn.close()

    def test_global_invalidation_coalesces_across_restart_and_retries_failure(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            conn = connect(settings)
            try:
                enqueue_context_refresh(conn, {("global", 0)})
                enqueue_context_refresh(conn, {("global", 0)})
                self.assertEqual(
                    ("pending", 2, 0),
                    conn.execute(
                        """SELECT status,requested_revision,completed_revision
                           FROM context_invalidations
                           WHERE scope_type='global' AND scope_id=0"""
                    ).fetchone(),
                )
                conn.commit()
            finally:
                conn.close()

            conn = connect(settings)
            try:
                with patch(
                    "alex_memory.context.service.ContextService.snapshot_global_state",
                    side_effect=RuntimeError("injected global refresh failure"),
                ):
                    self.assertEqual(
                        0, asyncio.run(refresh_pending_context(conn, settings))
                    )
                self.assertEqual(
                    ("failed", 2, 0),
                    conn.execute(
                        """SELECT status,requested_revision,completed_revision
                           FROM context_invalidations
                           WHERE scope_type='global' AND scope_id=0"""
                    ).fetchone(),
                )
                self.assertEqual(
                    1, asyncio.run(refresh_pending_context(conn, settings))
                )
                self.assertEqual(
                    ("clean", 2, 2),
                    conn.execute(
                        """SELECT status,requested_revision,completed_revision
                           FROM context_invalidations
                           WHERE scope_type='global' AND scope_id=0"""
                    ).fetchone(),
                )
            finally:
                conn.close()

    def test_new_global_revision_stays_pending_when_older_refresh_finishes(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            conn = connect(settings)
            try:
                enqueue_context_refresh(conn, {("global", 0)})

                async def refresh_and_requeue(*_args) -> None:
                    enqueue_context_refresh(conn, {("global", 0)})

                with patch(
                    "alex_memory.context.refresh._refresh_scope",
                    side_effect=refresh_and_requeue,
                ):
                    self.assertEqual(
                        1, asyncio.run(refresh_pending_context(conn, settings))
                    )
                self.assertEqual(
                    ("pending", 2, 1),
                    conn.execute(
                        """SELECT status,requested_revision,completed_revision
                           FROM context_invalidations
                           WHERE scope_type='global' AND scope_id=0"""
                    ).fetchone(),
                )
            finally:
                conn.close()

    def test_non_global_invalidation_does_not_refresh_global_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            conn = connect(settings)
            try:
                enqueue_context_refresh(conn, {("conversation", 112)})

                self.assertEqual(
                    1, asyncio.run(refresh_pending_context(conn, settings))
                )

                self.assertEqual(
                    0,
                    conn.execute(
                        "SELECT COUNT(*) FROM global_state_snapshots"
                    ).fetchone()[0],
                )
            finally:
                conn.close()

    def test_derived_state_repair_inventory_is_bounded_and_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            conn = connect(make_settings(Path(directory)))
            try:
                conn.execute(
                    "INSERT INTO chats(chat_id,title,chat_type) VALUES (110,'Work','group')"
                )
                for item_id in (1, 2):
                    conn.execute(
                        """INSERT INTO ai_items(item_id,batch_id,kind,title,details,status,owner,
                           confidence,source_chat_id,source_message_id,source_date,created_at,dedupe_key)
                           VALUES (?,1,'task','Follow up','','open','me',0.96,110,?,
                           '2026-08-28T09:00:00+00:00','now',?)""",
                        (item_id, item_id, f"repair-inventory-{item_id}"),
                    )
                    conn.execute(
                        """INSERT INTO tasks(title,normalized_title,status,owner,source_chat_id,
                           source_item_id,confidence,created_at,updated_at)
                           VALUES ('Follow up','follow up','open','me',110,?,0.96,'now','now')""",
                        (item_id,),
                    )
                before = conn.total_changes

                inventory = derived_state_repair_inventory(conn, limit=1)

                self.assertEqual(before, conn.total_changes)
                self.assertEqual(1, inventory["task_project_candidates"])
                self.assertTrue(inventory["task_project_truncated"])
                self.assertEqual(0, inventory["segment_chat_candidates"])
                self.assertFalse(inventory["segment_chat_truncated"])
                self.assertEqual(0, inventory["pending_context_candidates"])
                with self.assertRaisesRegex(ValueError, "limit"):
                    derived_state_repair_inventory(conn, limit=0)
                report = derived_state_repair_dry_run(
                    conn, operations={"task-project"}, limit=1
                )
                self.assertEqual(before, conn.total_changes)
                self.assertEqual("dry-run", report["mode"])
                self.assertEqual({"task-project"}, set(report["operations"]))
                self.assertEqual(
                    1, report["operations"]["task-project"]["eligible_units"]
                )
                self.assertTrue(report["operations"]["task-project"]["truncated"])
                self.assertRegex(
                    str(report["operations"]["task-project"]["unit_fingerprint"]),
                    r"^[0-9a-f]{64}$",
                )
                self.assertRegex(str(report["fingerprint"]), r"^[0-9a-f]{64}$")
                with self.assertRaisesRegex(ValueError, "at least one"):
                    derived_state_repair_dry_run(conn, operations=set())
                with self.assertRaisesRegex(ValueError, "unsupported"):
                    derived_state_repair_dry_run(conn, operations={"lifecycle"})
            finally:
                conn.close()

    def test_task_project_repair_requires_matching_dry_run_and_is_resumable(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            settings = make_settings(path)
            conn = connect(settings)
            try:
                project_id = EntityResolver(conn).entity("project", "Georgia LP")
                assert project_id is not None
                conn.execute(
                    "INSERT INTO chats(chat_id,title,chat_type) VALUES (111,'Work','group')"
                )
                conn.execute(
                    """INSERT INTO ai_items(batch_id,kind,title,details,status,owner,confidence,
                       source_chat_id,source_message_id,source_date,project_id,created_at,dedupe_key)
                       VALUES (3,'project','Georgia LP','','informational','unknown',0.96,
                       111,1,'2026-08-22T09:00:00+00:00',?,'now','repair-apply-project')""",
                    (project_id,),
                )
                item_id = conn.execute(
                    """INSERT INTO ai_items(batch_id,kind,title,details,status,owner,confidence,
                       source_chat_id,source_message_id,source_date,created_at,dedupe_key)
                       VALUES (3,'task','Send docs','','open','me',0.96,111,1,
                       '2026-08-22T09:00:00+00:00','now','repair-apply-task')"""
                ).lastrowid
                conn.execute(
                    """INSERT INTO tasks(title,normalized_title,status,owner,source_chat_id,
                       source_item_id,confidence,created_at,updated_at)
                       VALUES ('Send docs','send docs','open','me',111,?,0.96,'now','now')""",
                    (item_id,),
                )
                report = derived_state_repair_dry_run(
                    conn, operations={"task-project"}, limit=1
                )
                receipt = path / "recovery-receipt.sqlite"
                receipt.touch()

                def partial_failure(*_args, **_kwargs) -> tuple[int, int]:
                    conn.execute(
                        "UPDATE tasks SET related_project_id=? WHERE task_id=1",
                        (project_id,),
                    )
                    raise RuntimeError("injected repair failure")

                with (
                    patch(
                        "alex_memory.repair.backfill_task_project_links",
                        side_effect=partial_failure,
                    ),
                    self.assertRaisesRegex(RuntimeError, "injected"),
                ):
                    apply_task_project_repair(
                        conn,
                        settings,
                        dry_run_fingerprint=str(report["fingerprint"]),
                        recovery_receipt=receipt,
                        limit=1,
                    )
                self.assertIsNone(
                    conn.execute("SELECT related_project_id FROM tasks").fetchone()[0]
                )
                self.assertEqual(
                    "failed",
                    json.loads(
                        conn.execute(
                            "SELECT value FROM app_meta WHERE key=?",
                            (f"derived_state_repair:{report['fingerprint']}",),
                        ).fetchone()[0]
                    )["status"],
                )

                outcome = apply_task_project_repair(
                    conn,
                    settings,
                    dry_run_fingerprint=str(report["fingerprint"]),
                    recovery_receipt=receipt,
                    limit=1,
                )

                self.assertEqual("completed", outcome["status"])
                self.assertEqual(1, outcome["linked"])
                self.assertEqual(
                    project_id,
                    conn.execute("SELECT related_project_id FROM tasks").fetchone()[0],
                )
                self.assertEqual(
                    "completed",
                    json.loads(
                        conn.execute(
                            "SELECT value FROM app_meta WHERE key=?",
                            (f"derived_state_repair:{report['fingerprint']}",),
                        ).fetchone()[0]
                    )["status"],
                )
                self.assertEqual(
                    [1],
                    json.loads(
                        conn.execute(
                            "SELECT value FROM app_meta WHERE key=?",
                            (f"derived_state_repair:{report['fingerprint']}",),
                        ).fetchone()[0]
                    )["task_ids"],
                )
                self.assertEqual(
                    "already-complete",
                    apply_task_project_repair(
                        conn,
                        settings,
                        dry_run_fingerprint=str(report["fingerprint"]),
                        recovery_receipt=receipt,
                        limit=1,
                    )["status"],
                )
                with self.assertRaisesRegex(ValueError, "fingerprint"):
                    apply_task_project_repair(
                        conn,
                        settings,
                        dry_run_fingerprint="not-the-report",
                        recovery_receipt=receipt,
                        limit=1,
                    )
            finally:
                conn.close()

    def test_task_lifecycle_repair_preserves_manual_authority_and_terminal_state(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            settings = make_settings(path)
            conn = connect(settings)
            try:
                conn.execute(
                    "INSERT INTO chats(chat_id,title,chat_type) VALUES (113,'Work','group')"
                )
                conn.executemany(
                    "INSERT INTO messages(chat_id,message_id,date,text) VALUES (113,?,?,?)",
                    [
                        (1, "2026-08-22T09:00:00+00:00", "Send invoice."),
                        (2, "2026-08-22T10:00:00+00:00", "Report completed."),
                    ],
                )
                conn.executemany(
                    """INSERT INTO semantic_claims(batch_id,claim_type,statement,payload_json,
                           extractor_version,provider,model,confidence,authority_status,dedupe_key,created_at)
                       VALUES (1,'action_candidate',?,'{}',1,'test','test',0.96,'observed',?,'now')""",
                    [
                        ("Send invoice", "lifecycle-claim-open"),
                        ("Report completed", "lifecycle-claim-done"),
                    ],
                )
                claim_ids = [
                    row[0]
                    for row in conn.execute(
                        "SELECT claim_id FROM semantic_claims ORDER BY claim_id"
                    ).fetchall()
                ]
                conn.executemany(
                    """INSERT INTO semantic_claim_evidence(
                           claim_id,ordinal,source_chat_id,source_message_id,created_at
                       ) VALUES (?,0,113,?,'now')""",
                    [(claim_ids[0], 1), (claim_ids[1], 2)],
                )
                conn.executemany(
                    """INSERT INTO ai_items(batch_id,kind,title,details,status,owner,confidence,
                           source_chat_id,source_message_id,source_date,source_claim_id,created_at,dedupe_key)
                       VALUES (1,'task',?,'',?,'me',0.96,113,?,?,?,'now',?)""",
                    [
                        (
                            "Send invoice",
                            "open",
                            1,
                            "2026-08-22T09:00:00+00:00",
                            claim_ids[0],
                            "lifecycle-open",
                        ),
                        (
                            "Send report",
                            "done",
                            2,
                            "2026-08-22T10:00:00+00:00",
                            claim_ids[1],
                            "lifecycle-done",
                        ),
                    ],
                )
                manual_task = conn.execute(
                    """INSERT INTO tasks(title,normalized_title,status,owner,source_chat_id,
                           manual_status_locked,confidence,created_at,updated_at)
                       VALUES ('Send invoice','send invoice','waiting','me',113,1,1.0,'now','now')"""
                ).lastrowid
                terminal_task = conn.execute(
                    """INSERT INTO tasks(title,normalized_title,status,owner,source_chat_id,
                           confidence,created_at,updated_at)
                       VALUES ('Send report','send report','open','me',113,1.0,'now','now')"""
                ).lastrowid
                unrelated_task = conn.execute(
                    """INSERT INTO tasks(title,normalized_title,status,owner,source_chat_id,
                           confidence,created_at,updated_at)
                       VALUES ('Unrelated','unrelated','open','me',114,1.0,'now','now')"""
                ).lastrowid
                assert (
                    manual_task is not None
                    and terminal_task is not None
                    and unrelated_task is not None
                )
                report = derived_state_repair_dry_run(
                    conn, operations={"task-lifecycle"}, limit=10
                )
                self.assertEqual(
                    2, report["operations"]["task-lifecycle"]["eligible_units"]
                )
                receipt = path / "recovery-receipt.sqlite"
                receipt.touch()

                outcome = apply_task_lifecycle_repair(
                    conn,
                    settings,
                    dry_run_fingerprint=str(report["fingerprint"]),
                    recovery_receipt=receipt,
                    limit=10,
                )

                self.assertEqual("completed", outcome["status"])
                self.assertEqual(2, outcome["source_items"])
                self.assertEqual(
                    ("waiting", 1),
                    conn.execute(
                        "SELECT status,manual_status_locked FROM tasks WHERE task_id=?",
                        (manual_task,),
                    ).fetchone(),
                )
                self.assertEqual(
                    "open",
                    conn.execute(
                        "SELECT status FROM tasks WHERE task_id=?", (unrelated_task,)
                    ).fetchone()[0],
                )
                self.assertEqual(
                    "done",
                    conn.execute(
                        "SELECT status FROM tasks WHERE task_id=?", (terminal_task,)
                    ).fetchone()[0],
                )
                checkpoint = json.loads(
                    conn.execute(
                        "SELECT value FROM app_meta WHERE key=?",
                        (f"derived_state_repair:{report['fingerprint']}",),
                    ).fetchone()[0]
                )
                self.assertEqual("completed", checkpoint["status"])
                self.assertEqual(
                    {claim_ids[0], claim_ids[1]},
                    {item["source_claim_id"] for item in checkpoint["source_items"]},
                )
                self.assertEqual(
                    "already-complete",
                    apply_task_lifecycle_repair(
                        conn,
                        settings,
                        dry_run_fingerprint=str(report["fingerprint"]),
                        recovery_receipt=receipt,
                        limit=10,
                    )["status"],
                )
            finally:
                conn.close()

    def test_task_lifecycle_repair_rejects_stale_scope_and_retries_exact_items(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            settings = make_settings(path)
            conn = connect(settings)
            try:
                conn.execute(
                    "INSERT INTO chats(chat_id,title,chat_type) VALUES (115,'Work','group')"
                )
                conn.execute(
                    "INSERT INTO messages(chat_id,message_id,date,text) VALUES (115,1,'2026-08-22T09:00:00+00:00','Send invoice.')"
                )
                claim_id = conn.execute(
                    """INSERT INTO semantic_claims(batch_id,claim_type,statement,payload_json,
                           extractor_version,provider,model,confidence,authority_status,dedupe_key,created_at)
                       VALUES (1,'action_candidate','Send invoice','{}',1,'test','test',0.96,
                               'observed','lifecycle-retry-claim','now')"""
                ).lastrowid
                assert claim_id is not None
                conn.execute(
                    "INSERT INTO semantic_claim_evidence(claim_id,ordinal,source_chat_id,source_message_id,created_at) VALUES (?,0,115,1,'now')",
                    (claim_id,),
                )
                item_id = conn.execute(
                    """INSERT INTO ai_items(batch_id,kind,title,details,status,owner,confidence,
                           source_chat_id,source_message_id,source_date,source_claim_id,created_at,dedupe_key)
                       VALUES (1,'task','Send invoice','','open','me',0.96,115,1,
                               '2026-08-22T09:00:00+00:00',?,'now','lifecycle-retry')""",
                    (claim_id,),
                ).lastrowid
                assert item_id is not None
                receipt = path / "recovery-receipt.sqlite"
                receipt.touch()
                stale = derived_state_repair_dry_run(
                    conn, operations={"task-lifecycle"}, limit=1
                )
                conn.execute(
                    "UPDATE ai_items SET title='Changed title' WHERE item_id=?",
                    (item_id,),
                )
                with self.assertRaisesRegex(ValueError, "fingerprint"):
                    apply_task_lifecycle_repair(
                        conn,
                        settings,
                        dry_run_fingerprint=str(stale["fingerprint"]),
                        recovery_receipt=receipt,
                        limit=1,
                    )
                report = derived_state_repair_dry_run(
                    conn, operations={"task-lifecycle"}, limit=1
                )

                def partial_failure(*_args, **_kwargs) -> dict[str, object]:
                    conn.execute(
                        "INSERT INTO tasks(title,normalized_title,status,owner,source_chat_id,confidence,created_at,updated_at) VALUES ('Partial','partial','open','me',115,1.0,'now','now')"
                    )
                    raise RuntimeError("injected lifecycle failure")

                with (
                    patch(
                        "alex_memory.repair._reconcile_task_lifecycle_rows",
                        side_effect=partial_failure,
                    ),
                    self.assertRaisesRegex(RuntimeError, "injected lifecycle failure"),
                ):
                    apply_task_lifecycle_repair(
                        conn,
                        settings,
                        dry_run_fingerprint=str(report["fingerprint"]),
                        recovery_receipt=receipt,
                        limit=1,
                    )
                self.assertEqual(
                    0,
                    conn.execute(
                        "SELECT COUNT(*) FROM tasks WHERE title='Partial'"
                    ).fetchone()[0],
                )
                self.assertEqual(
                    "failed",
                    json.loads(
                        conn.execute(
                            "SELECT value FROM app_meta WHERE key=?",
                            (f"derived_state_repair:{report['fingerprint']}",),
                        ).fetchone()[0]
                    )["status"],
                )
                self.assertEqual(
                    "completed",
                    apply_task_lifecycle_repair(
                        conn,
                        settings,
                        dry_run_fingerprint=str(report["fingerprint"]),
                        recovery_receipt=receipt,
                        limit=1,
                    )["status"],
                )
            finally:
                conn.close()

    def test_task_lifecycle_repair_does_not_re_resolve_missing_project_context(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            settings = make_settings(path)
            conn = connect(settings)
            try:
                conn.execute(
                    "INSERT INTO chats(chat_id,title,chat_type) VALUES (116,'Work','group')"
                )
                conn.execute(
                    "INSERT INTO messages(chat_id,message_id,date,text) VALUES (116,1,'2026-08-22T09:00:00+00:00','Prepare Georgia documents.')"
                )
                for name in ("Georgia LP", "Georgia Fund"):
                    EntityResolver(conn).entity("project", name, source="manual")
                claim_id = conn.execute(
                    """INSERT INTO semantic_claims(batch_id,claim_type,statement,payload_json,
                           extractor_version,provider,model,confidence,authority_status,dedupe_key,created_at)
                       VALUES (1,'action_candidate','Prepare Georgia documents','{}',1,'test','test',0.96,
                               'observed','lifecycle-unresolved-claim','now')"""
                ).lastrowid
                assert claim_id is not None
                conn.execute(
                    "INSERT INTO semantic_claim_evidence(claim_id,ordinal,source_chat_id,source_message_id,created_at) VALUES (?,0,116,1,'now')",
                    (claim_id,),
                )
                conn.execute(
                    """INSERT INTO ai_items(batch_id,kind,title,details,status,owner,confidence,
                           source_chat_id,source_message_id,source_date,source_claim_id,created_at,dedupe_key)
                       VALUES (1,'task','Prepare Georgia documents','','open','me',0.96,116,1,
                               '2026-08-22T09:00:00+00:00',?,'now','lifecycle-unresolved')""",
                    (claim_id,),
                )
                receipt = path / "recovery-receipt.sqlite"
                receipt.touch()
                report = derived_state_repair_dry_run(
                    conn, operations={"task-lifecycle"}, limit=1
                )

                apply_task_lifecycle_repair(
                    conn,
                    settings,
                    dry_run_fingerprint=str(report["fingerprint"]),
                    recovery_receipt=receipt,
                    limit=1,
                )

                self.assertIsNone(
                    conn.execute(
                        "SELECT related_project_id FROM tasks WHERE title='Prepare Georgia documents'"
                    ).fetchone()[0]
                )
                self.assertEqual(
                    0,
                    conn.execute(
                        "SELECT COUNT(*) FROM review_queue WHERE review_type='graph_task_link'"
                    ).fetchone()[0],
                )
            finally:
                conn.close()

    def test_segment_repair_requires_matching_dry_run_and_is_resumable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            settings = make_settings(path)
            conn = connect(settings)
            try:
                project_id = EntityResolver(conn).entity("project", "Georgia LP")
                assert project_id is not None
                conn.execute(
                    "INSERT INTO chats(chat_id,title,chat_type) VALUES (112,'Work','group')"
                )
                item_id = conn.execute(
                    """INSERT INTO ai_items(batch_id,kind,title,details,status,owner,confidence,
                       source_chat_id,source_message_id,source_date,created_at,dedupe_key)
                       VALUES (4,'task','Send docs','','open','me',0.96,112,1,
                       '2026-08-22T09:00:00+00:00','now','repair-segments-task')"""
                ).lastrowid
                conn.execute(
                    """INSERT INTO tasks(title,normalized_title,status,owner,source_chat_id,
                       source_item_id,related_project_id,confidence,created_at,updated_at)
                       VALUES ('Send docs','send docs','open','me',112,?,?,0.96,'now','now')""",
                    (item_id, project_id),
                )
                conn.execute(
                    """INSERT INTO conversation_segments(
                       chat_id,project_id,started_at,ended_at,anchor_count,confidence,
                       source,created_at,updated_at
                   ) VALUES (112,?,'2020-01-01T00:00:00+00:00',NULL,1,0.75,
                             'task_anchors','now','now')""",
                    (project_id,),
                )
                report = derived_state_repair_dry_run(
                    conn, operations={"segments"}, limit=1
                )
                self.assertRegex(
                    str(report["operations"]["segments"]["unit_fingerprint"]),
                    r"^[0-9a-f]{64}$",
                )
                receipt = path / "recovery-receipt.sqlite"
                receipt.touch()

                def partial_failure(_chat_ids: set[int]) -> int:
                    conn.execute(
                        "DELETE FROM conversation_segments WHERE chat_id=112 AND source='task_anchors'"
                    )
                    raise RuntimeError("injected segment repair failure")

                with (
                    patch(
                        "alex_memory.repair.ConversationSegmenter.rebuild_chats",
                        side_effect=partial_failure,
                    ),
                    self.assertRaisesRegex(RuntimeError, "injected"),
                ):
                    apply_segment_repair(
                        conn,
                        settings,
                        dry_run_fingerprint=str(report["fingerprint"]),
                        recovery_receipt=receipt,
                        limit=1,
                    )
                self.assertEqual(
                    1,
                    conn.execute(
                        "SELECT COUNT(*) FROM conversation_segments WHERE chat_id=112"
                    ).fetchone()[0],
                )
                outcome = apply_segment_repair(
                    conn,
                    settings,
                    dry_run_fingerprint=str(report["fingerprint"]),
                    recovery_receipt=receipt,
                    limit=1,
                )
                self.assertEqual(
                    {"status": "completed", "chats": 1, "segments": 1},
                    {key: outcome[key] for key in ("status", "chats", "segments")},
                )
                self.assertEqual(
                    "2026-08-22T09:00:00+00:00",
                    conn.execute(
                        "SELECT started_at FROM conversation_segments WHERE chat_id=112"
                    ).fetchone()[0],
                )
                self.assertEqual(
                    "already-complete",
                    apply_segment_repair(
                        conn,
                        settings,
                        dry_run_fingerprint=str(report["fingerprint"]),
                        recovery_receipt=receipt,
                        limit=1,
                    )["status"],
                )
            finally:
                conn.close()

    def test_fts_repair_rejects_stale_scope_and_is_retry_safe(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            settings = make_settings(path)
            conn = connect(settings)
            try:
                if not fts_index_health(conn)["available"]:
                    self.skipTest("SQLite was built without optional FTS5")
                resolver = EntityResolver(conn)
                resolver.entity("person", "Ari", source="manual")
                first = derived_state_repair_dry_run(conn, operations={"fts"})
                self.assertRegex(
                    str(first["operations"]["fts"]["unit_fingerprint"]),
                    r"^[0-9a-f]{64}$",
                )
                resolver.entity("company", "Beta", source="manual")
                receipt = path / "recovery-receipt.sqlite"
                receipt.touch()
                with self.assertRaisesRegex(ValueError, "fingerprint"):
                    apply_fts_repair(
                        conn,
                        settings,
                        dry_run_fingerprint=str(first["fingerprint"]),
                        recovery_receipt=receipt,
                    )

                report = derived_state_repair_dry_run(conn, operations={"fts"})
                conn.execute(
                    "DELETE FROM entities_fts WHERE name='Beta' AND entity_type='company'"
                )
                self.assertFalse(fts_index_health(conn)["healthy"])
                outcome = apply_fts_repair(
                    conn,
                    settings,
                    dry_run_fingerprint=str(report["fingerprint"]),
                    recovery_receipt=receipt,
                )
                self.assertEqual("completed", outcome["status"])
                self.assertTrue(fts_index_health(conn)["healthy"])
                self.assertEqual(
                    "already-complete",
                    apply_fts_repair(
                        conn,
                        settings,
                        dry_run_fingerprint=str(report["fingerprint"]),
                        recovery_receipt=receipt,
                    )["status"],
                )
            finally:
                conn.close()

    def test_context_repair_refreshes_exact_conversation_revision_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            settings = make_settings(path)
            conn = connect(settings)
            try:
                conn.execute(
                    "INSERT INTO chats(chat_id,title,chat_type) VALUES (113,'Work','group')"
                )
                person_id = EntityResolver(conn).entity(
                    "person", "Ari", source="manual"
                )
                assert person_id is not None
                enqueue_context_refresh(
                    conn, {("conversation", 113), ("person", person_id)}
                )
                first = derived_state_repair_dry_run(
                    conn, operations={"context"}, limit=1
                )
                self.assertEqual(1, first["operations"]["context"]["eligible_units"])
                self.assertRegex(
                    str(first["operations"]["context"]["unit_fingerprint"]),
                    r"^[0-9a-f]{64}$",
                )
                enqueue_context_refresh(conn, {("conversation", 113)})
                receipt = path / "recovery-receipt.sqlite"
                receipt.touch()
                with self.assertRaisesRegex(ValueError, "fingerprint"):
                    apply_context_repair(
                        conn,
                        settings,
                        dry_run_fingerprint=str(first["fingerprint"]),
                        recovery_receipt=receipt,
                        limit=1,
                    )

                report = derived_state_repair_dry_run(
                    conn, operations={"context"}, limit=1
                )
                outcome = apply_context_repair(
                    conn,
                    settings,
                    dry_run_fingerprint=str(report["fingerprint"]),
                    recovery_receipt=receipt,
                    limit=1,
                )
                self.assertEqual(
                    {"status": "completed", "conversations": 1},
                    {key: outcome[key] for key in ("status", "conversations")},
                )
                self.assertEqual(
                    (2, 2, "clean"),
                    conn.execute(
                        """SELECT requested_revision,completed_revision,status
                           FROM context_invalidations
                           WHERE scope_type='conversation' AND scope_id=113"""
                    ).fetchone(),
                )
                self.assertEqual(
                    "pending",
                    conn.execute(
                        """SELECT status FROM context_invalidations
                           WHERE scope_type='person' AND scope_id=?""",
                        (person_id,),
                    ).fetchone()[0],
                )
                self.assertEqual(
                    "already-complete",
                    apply_context_repair(
                        conn,
                        settings,
                        dry_run_fingerprint=str(report["fingerprint"]),
                        recovery_receipt=receipt,
                        limit=1,
                    )["status"],
                )
            finally:
                conn.close()

    def test_project_health_repair_binds_inputs_and_suppresses_notifications(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            settings = make_settings(path)
            conn = connect(settings)
            try:
                resolver = EntityResolver(conn)
                project_id = resolver.entity("project", "Georgia LP", source="manual")
                terminal_id = resolver.entity("project", "Closed LP", source="manual")
                assert project_id is not None and terminal_id is not None
                conn.execute(
                    "UPDATE projects SET status='completed' WHERE project_id=?",
                    (terminal_id,),
                )
                first = derived_state_repair_dry_run(
                    conn, operations={"project-health"}, limit=1
                )
                self.assertEqual(
                    1, first["operations"]["project-health"]["eligible_units"]
                )
                conn.execute(
                    "UPDATE projects SET updated_at='changed' WHERE project_id=?",
                    (project_id,),
                )
                receipt = path / "recovery-receipt.sqlite"
                receipt.touch()
                with self.assertRaisesRegex(ValueError, "fingerprint"):
                    apply_project_health_repair(
                        conn,
                        settings,
                        dry_run_fingerprint=str(first["fingerprint"]),
                        recovery_receipt=receipt,
                        limit=1,
                    )

                report = derived_state_repair_dry_run(
                    conn, operations={"project-health"}, limit=1
                )
                with patch("alex_memory.intelligence._notify") as notify:
                    outcome = apply_project_health_repair(
                        conn,
                        settings,
                        dry_run_fingerprint=str(report["fingerprint"]),
                        recovery_receipt=receipt,
                        limit=1,
                    )
                notify.assert_not_called()
                self.assertEqual(
                    {"status": "completed", "projects": 1},
                    {key: outcome[key] for key in ("status", "projects")},
                )
                self.assertEqual(
                    "completed",
                    conn.execute(
                        "SELECT status FROM projects WHERE project_id=?", (terminal_id,)
                    ).fetchone()[0],
                )
                self.assertEqual(
                    "already-complete",
                    apply_project_health_repair(
                        conn,
                        settings,
                        dry_run_fingerprint=str(report["fingerprint"]),
                        recovery_receipt=receipt,
                        limit=1,
                    )["status"],
                )
            finally:
                conn.close()

    def test_load_daily_brief_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            conn = connect(make_settings(Path(directory)))
            try:
                created = generate_daily_brief(conn, "2026-08-25")
                before = conn.total_changes
                self.assertEqual(created, load_daily_brief(conn, "2026-08-25"))
                self.assertEqual(before, conn.total_changes)
                self.assertIsNone(load_daily_brief(conn, "2026-08-26"))
            finally:
                conn.close()

    def test_entity_identity_and_ambiguous_aliases_are_safe(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            conn = connect(make_settings(Path(directory)))
            resolver = EntityResolver(conn)
            first = resolver.person(
                "Ilya Guttovsky", telegram_user_id=42, telegram_username="ilya"
            )
            self.assertEqual(
                first, resolver.person("Different spelling", telegram_user_id=42)
            )
            self.assertEqual(first, resolver.person("Ilya", telegram_username="@ilya"))
            resolver._alias("person", first, "Ilya", "test", 1.0)
            second = resolver.person("Another Ilya")
            resolver._alias("person", second, "Ilya", "test", 1.0)
            self.assertIsNone(resolver.person("Ilya"))
            self.assertEqual(normalize_alias(" @Ілля   Guttovsky "), "ілля guttovsky")
            self.assertEqual(
                1,
                conn.execute("SELECT COUNT(*) FROM entity_merge_candidates").fetchone()[
                    0
                ],
            )

    def test_distinct_telegram_peers_with_the_same_name_remain_separate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            conn = connect(make_settings(Path(directory)))
            resolver = EntityResolver(conn)

            first = resolver.person("David", telegram_user_id=101)
            second = resolver.person("David", telegram_user_id=202)

            self.assertIsNotNone(first)
            self.assertIsNotNone(second)
            self.assertNotEqual(first, second)
            self.assertEqual(
                [101, 202],
                [
                    row[0]
                    for row in conn.execute(
                        "SELECT telegram_user_id FROM people ORDER BY telegram_user_id"
                    )
                ],
            )

    def test_direct_chat_peer_id_is_canonical_and_title_matches_are_reviewed(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            conn = connect(make_settings(Path(directory)))
            resolver = EntityResolver(conn)
            historical = resolver.person("Alice", source="manual")
            assert historical is not None
            conn.execute(
                "INSERT INTO chats(chat_id,title,username,chat_type) VALUES (77,'Alice','alice','user')"
            )

            peer = direct_chat_person(conn, 77)

            self.assertNotEqual(historical, peer)
            self.assertEqual(
                77,
                conn.execute(
                    "SELECT telegram_user_id FROM people WHERE person_id=?", (peer,)
                ).fetchone()[0],
            )
            self.assertEqual(
                1,
                conn.execute(
                    "SELECT COUNT(*) FROM entity_merge_candidates WHERE normalized_alias='alice'"
                ).fetchone()[0],
            )

    def test_unique_username_claims_an_existing_person(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            conn = connect(make_settings(Path(directory)))
            resolver = EntityResolver(conn)
            person_id = resolver.person(
                "Alice Cooper", telegram_username="@alicec", source="manual"
            )
            assert person_id is not None
            conn.execute(
                "INSERT INTO chats(chat_id,title,username,chat_type) VALUES (78,'A. C.','alicec','user')"
            )

            self.assertEqual(person_id, direct_chat_person(conn, 78))
            self.assertEqual(
                78,
                conn.execute(
                    "SELECT telegram_user_id FROM people WHERE person_id=?",
                    (person_id,),
                ).fetchone()[0],
            )
            self.assertEqual(
                1,
                conn.execute(
                    """SELECT COUNT(*) FROM entity_aliases
                       WHERE entity_type='person' AND entity_id=? AND normalized_alias='a. c.'""",
                    (person_id,),
                ).fetchone()[0],
            )

    def test_direct_chat_title_conflict_preserves_manual_alias_and_requests_review(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            conn = connect(make_settings(Path(directory)))
            resolver = EntityResolver(conn)
            target = resolver.person("Alice Cooper", telegram_username="alicec")
            manual = resolver.person("Manual Alice", source="manual")
            assert target is not None and manual is not None
            resolver._alias("person", manual, "A. C.", "manual", 1.0)
            conn.execute(
                "INSERT INTO chats(chat_id,title,username,chat_type) VALUES (79,'A. C.','alicec','user')"
            )

            self.assertEqual(target, direct_chat_person(conn, 79))
            self.assertEqual(
                manual,
                conn.execute(
                    """SELECT entity_id FROM entity_aliases WHERE entity_type='person'
                       AND normalized_alias='a. c.'"""
                ).fetchone()[0],
            )
            self.assertEqual(
                1,
                conn.execute(
                    """SELECT COUNT(*) FROM entity_merge_candidates
                       WHERE normalized_alias='a. c.'"""
                ).fetchone()[0],
            )
            self.assertEqual(
                2, conn.execute("SELECT COUNT(*) FROM people").fetchone()[0]
            )

    def test_direct_identity_backfill_is_bounded_and_refreshes_only_processed_chats(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            conn = connect(settings)
            conn.executemany(
                """INSERT INTO chats(chat_id,title,chat_type,updated_at)
                   VALUES (?,?,'user',?)""",
                [(79, "Alice", "2026-08-20"), (80, "Bob", "2026-08-21")],
            )

            self.assertEqual(
                1, backfill_direct_chat_identities(conn, settings, limit=1)
            )
            self.assertEqual(
                [79],
                [
                    row[0]
                    for row in conn.execute(
                        "SELECT telegram_user_id FROM people ORDER BY telegram_user_id"
                    ).fetchall()
                ],
            )
            self.assertEqual(
                1,
                conn.execute(
                    "SELECT COUNT(*) FROM current_conversation_context WHERE conversation_id='79'"
                ).fetchone()[0],
            )
            with self.assertRaises(ValueError):
                backfill_direct_chat_identities(conn, settings, limit=0)

    def test_direct_chat_uses_peer_owner_for_prompt_and_materialization(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            conn = connect(settings)
            resolver = EntityResolver(conn)
            third_party = resolver.person("Chris", source="manual")
            assert third_party is not None
            conn.execute(
                "INSERT INTO chats(chat_id,title,username,chat_type) VALUES (88,'Alice','alice','user')"
            )
            conn.execute(
                """INSERT INTO ai_items(batch_id,kind,title,details,status,owner,confidence,
                   source_chat_id,source_message_id,source_date,person_id,created_at,dedupe_key)
                   VALUES (1,'fact','Chris update','Third-party mention','informational','unknown',0.9,
                   88,1,'2026-08-22T09:00:00+00:00',?,'now','direct-owner')""",
                (third_party,),
            )
            batch = AIBatch(
                88,
                "Alice",
                [
                    AIMessage(
                        88,
                        2,
                        None,
                        "2026-08-22T10:00:00+00:00",
                        "Hello",
                        False,
                        "Alice",
                        "user",
                    )
                ],
                "prompt",
            )

            add_contextual_preamble(conn, batch, settings)
            peer = direct_chat_person(conn, 88)

            self.assertIsNotNone(peer)
            self.assertNotEqual(third_party, peer)
            self.assertEqual(
                1,
                conn.execute(
                    """SELECT COUNT(*) FROM current_conversation_context
                       WHERE person_id=? AND conversation_id='88'""",
                    (peer,),
                ).fetchone()[0],
            )
            self.assertEqual(
                0,
                conn.execute(
                    """SELECT COUNT(*) FROM current_conversation_context
                       WHERE person_id=? AND conversation_id='88'""",
                    (third_party,),
                ).fetchone()[0],
            )
            summary = conn.execute(
                """SELECT recent_summary FROM current_conversation_context
                   WHERE person_id=? AND conversation_id='88'""",
                (peer,),
            ).fetchone()[0]
            self.assertIn("Chris update", summary)

    def test_tasks_memory_and_brief_are_created_from_successful_batch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            conn = connect(settings)
            conn.execute(
                "INSERT INTO chats(chat_id, title, chat_type, updated_at) VALUES (100, 'Ilya', 'user', 'now')"
            )
            conn.execute(
                "INSERT INTO messages(chat_id, message_id, date, text, is_outgoing, has_media) VALUES (100, 1, '2026-08-22T09:00:00+00:00', 'Send the invoice tomorrow', 0, 0)"
            )
            batch = AIBatch(
                100,
                "Ilya",
                [
                    AIMessage(
                        100,
                        1,
                        2,
                        "2026-08-22T09:00:00+00:00",
                        "Send the invoice tomorrow",
                        False,
                        "Ilya",
                        "user",
                    )
                ],
                "prompt",
            )
            item = {
                "kind": "promise_by_me",
                "title": "Send invoice",
                "details": "Promised to Ilya.",
                "status": "open",
                "owner": "me",
                "due_date": "2026-08-23",
                "person": "Chris",
                "company": None,
                "project_name": None,
                "amount": None,
                "currency": None,
                "confidence": 0.96,
                "source_chat_id": 100,
                "source_message_id": 1,
            }
            saved = save_ai_success(
                conn,
                batch,
                {"summary": "I will send Ilya the invoice.", "items": [item]},
                settings,
            )
            with conn:
                process_ai_batch(conn, saved.batch_id, settings)
            self.assertTrue(process_ai_batch(conn, saved.batch_id, settings))
            asyncio.run(refresh_pending_context(conn, settings))
            self.assertGreater(
                conn.execute(
                    "SELECT COUNT(*) FROM ai_message_context_dependencies WHERE batch_id=?",
                    (saved.batch_id,),
                ).fetchone()[0],
                0,
            )
            self.assertEqual(1, history_coverage(conn, settings)["current_enough"])
            self.assertEqual(
                1,
                conn.execute(
                    "SELECT COUNT(*) FROM tasks WHERE status='open'"
                ).fetchone()[0],
            )
            self.assertEqual(
                1, conn.execute("SELECT COUNT(*) FROM memory_chunks").fetchone()[0]
            )
            self.assertEqual(
                0, conn.execute("SELECT COUNT(*) FROM entity_memory").fetchone()[0]
            )
            direct_person = conn.execute(
                "SELECT person_id FROM people WHERE telegram_user_id=100"
            ).fetchone()[0]
            mentioned_person = conn.execute(
                "SELECT person_id FROM ai_items WHERE batch_id=?", (saved.batch_id,)
            ).fetchone()[0]
            self.assertNotEqual(direct_person, mentioned_person)
            self.assertEqual(
                1,
                conn.execute(
                    """SELECT COUNT(*) FROM current_conversation_context
                       WHERE person_id=? AND conversation_id='100'""",
                    (direct_person,),
                ).fetchone()[0],
            )
            self.assertEqual(
                1,
                conn.execute(
                    """SELECT COUNT(*) FROM current_conversation_context
                       WHERE person_id=? AND conversation_id='100'""",
                    (mentioned_person,),
                ).fetchone()[0],
            )
            self.assertEqual(
                1,
                conn.execute("SELECT COUNT(*) FROM chat_daily_summaries").fetchone()[0],
            )
            # The task's current source pointer may later be replaced by an
            # update. The Daily Brief must retain the creation evidence date.
            conn.execute("UPDATE tasks SET source_item_id=NULL")
            brief = generate_daily_brief(conn, "2026-08-22")
            self.assertEqual("Send invoice", brief["new_tasks"][0]["title"])

    def test_task_uses_same_message_project_observation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            conn = connect(settings)
            conn.execute(
                "INSERT INTO chats(chat_id,title,chat_type) VALUES (101,'Work','group')"
            )
            conn.execute(
                """INSERT INTO messages(chat_id,message_id,date,text,is_outgoing,has_media)
                   VALUES (101,1,'2026-08-22T09:00:00+00:00','Georgia documents',0,0)"""
            )
            batch = AIBatch(
                101,
                "Work",
                [
                    AIMessage(
                        101,
                        1,
                        None,
                        "2026-08-22T09:00:00+00:00",
                        "Georgia documents",
                        False,
                        "Work",
                        "group",
                    )
                ],
                "prompt",
            )
            saved = save_ai_success(
                conn,
                batch,
                {
                    "summary": "Georgia documents are needed.",
                    "items": [
                        {
                            "kind": "project",
                            "title": "Georgia LP",
                            "details": "",
                            "status": "informational",
                            "owner": "unknown",
                            "due_date": None,
                            "person": None,
                            "company": None,
                            "project_name": None,
                            "amount": None,
                            "currency": None,
                            "confidence": 0.96,
                            "source_chat_id": 101,
                            "source_message_id": 1,
                        },
                        {
                            "kind": "task",
                            "title": "Send documents",
                            "details": "For the Georgia LP request.",
                            "status": "open",
                            "owner": "me",
                            "due_date": None,
                            "person": None,
                            "company": None,
                            "project_name": "Georgia LP",
                            "amount": None,
                            "currency": None,
                            "confidence": 0.96,
                            "source_chat_id": 101,
                            "source_message_id": 1,
                        },
                    ],
                },
                settings,
            )

            with conn:
                process_ai_batch(conn, saved.batch_id, settings)
            asyncio.run(refresh_pending_context(conn, settings))

            project_id = conn.execute(
                "SELECT project_id FROM ai_items WHERE batch_id=? AND kind='project'",
                (saved.batch_id,),
            ).fetchone()[0]
            self.assertEqual(
                project_id,
                conn.execute("SELECT related_project_id FROM tasks").fetchone()[0],
            )
            self.assertEqual(
                1,
                conn.execute(
                    "SELECT COUNT(*) FROM conversation_segments WHERE chat_id=101"
                ).fetchone()[0],
            )

    def test_casual_project_item_remains_an_observation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            conn = connect(settings)
            conn.execute(
                "INSERT INTO chats(chat_id,title,chat_type) VALUES (103,'Friends','group')"
            )
            conn.execute(
                """INSERT INTO messages(chat_id,message_id,date,text,is_outgoing,has_media)
                   VALUES (103,1,'2026-08-22T09:00:00+00:00','BBQ this weekend',0,0)"""
            )
            batch = AIBatch(
                103,
                "Friends",
                [
                    AIMessage(
                        103,
                        1,
                        None,
                        "2026-08-22T09:00:00+00:00",
                        "BBQ this weekend",
                        False,
                        "Friends",
                        "group",
                    )
                ],
                "prompt",
            )
            saved = save_ai_success(
                conn,
                batch,
                {
                    "summary": "A social plan was mentioned.",
                    "items": [
                        {
                            "kind": "project",
                            "title": "Weekend BBQ",
                            "details": "Friends plan a barbecue.",
                            "status": "informational",
                            "owner": "unknown",
                            "due_date": None,
                            "person": None,
                            "company": None,
                            "project_name": None,
                            "amount": None,
                            "currency": None,
                            "confidence": 0.99,
                            "source_chat_id": 103,
                            "source_message_id": 1,
                        }
                    ],
                },
                settings,
            )

            self.assertTrue(process_ai_batch(conn, saved.batch_id, settings))
            self.assertEqual(
                0, conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
            )
            self.assertIsNone(
                conn.execute("SELECT project_id FROM ai_items").fetchone()[0]
            )
            conn.close()

    def test_event_project_reference_cannot_create_a_project(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            conn = connect(settings)
            conn.execute(
                "INSERT INTO chats(chat_id,title,chat_type) VALUES (105,'Friends','group')"
            )
            conn.execute(
                "INSERT INTO messages(chat_id,message_id,date,text,is_outgoing,has_media) VALUES (105,1,'2026-08-22','Birthday plans',0,0)"
            )
            batch = AIBatch(
                105,
                "Friends",
                [
                    AIMessage(
                        105,
                        1,
                        None,
                        "2026-08-22",
                        "Birthday plans",
                        False,
                        "Friends",
                        "group",
                    )
                ],
                "prompt",
            )
            saved = save_ai_success(
                conn,
                batch,
                {
                    "summary": "Birthday plan.",
                    "items": [
                        {
                            "kind": "project",
                            "title": "Birthday",
                            "details": "Personal event.",
                            "status": "informational",
                            "owner": "unknown",
                            "due_date": None,
                            "person": None,
                            "company": None,
                            "project_name": None,
                            "amount": None,
                            "currency": None,
                            "confidence": 0.99,
                            "source_chat_id": 105,
                            "source_message_id": 1,
                        },
                        {
                            "kind": "event",
                            "title": "Birthday",
                            "details": "A birthday is planned.",
                            "status": "informational",
                            "owner": "unknown",
                            "due_date": None,
                            "person": None,
                            "company": None,
                            "project_name": "Birthday",
                            "amount": None,
                            "currency": None,
                            "confidence": 0.99,
                            "source_chat_id": 105,
                            "source_message_id": 1,
                        },
                    ],
                },
                settings,
            )

            self.assertTrue(process_ai_batch(conn, saved.batch_id, settings))
            self.assertEqual(
                0, conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
            )
            conn.close()

    def test_near_duplicate_project_requires_manual_review(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            conn = connect(settings)
            existing = EntityResolver(conn).entity(
                "project", "Georgia LP", source="manual"
            )
            assert existing is not None
            conn.execute(
                "INSERT INTO chats(chat_id,title,chat_type) VALUES (104,'Work','group')"
            )
            conn.execute(
                """INSERT INTO messages(chat_id,message_id,date,text,is_outgoing,has_media)
                   VALUES (104,1,'2026-08-22T09:00:00+00:00','Georgia L.P. documents',0,0)"""
            )
            batch = AIBatch(
                104,
                "Work",
                [
                    AIMessage(
                        104,
                        1,
                        None,
                        "2026-08-22T09:00:00+00:00",
                        "Georgia L.P. documents",
                        False,
                        "Work",
                        "group",
                    )
                ],
                "prompt",
            )
            items = [
                {
                    "kind": "project",
                    "title": "Georgia L.P.",
                    "details": "Document work.",
                    "status": "informational",
                    "owner": "unknown",
                    "due_date": None,
                    "person": None,
                    "company": None,
                    "project_name": None,
                    "amount": None,
                    "currency": None,
                    "confidence": 0.96,
                    "source_chat_id": 104,
                    "source_message_id": 1,
                },
                {
                    "kind": "task",
                    "title": "Send documents",
                    "details": "For Georgia L.P.",
                    "status": "open",
                    "owner": "me",
                    "due_date": None,
                    "person": None,
                    "company": None,
                    "project_name": "Georgia L.P.",
                    "amount": None,
                    "currency": None,
                    "confidence": 0.96,
                    "source_chat_id": 104,
                    "source_message_id": 1,
                },
            ]
            saved = save_ai_success(
                conn, batch, {"summary": "Georgia documents.", "items": items}, settings
            )

            self.assertTrue(process_ai_batch(conn, saved.batch_id, settings))
            self.assertEqual(
                1, conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
            )
            review_id = conn.execute(
                "SELECT review_id FROM review_queue WHERE review_type='project_duplicate'"
            ).fetchone()[0]
            resolve_review_item(conn, review_id, "accept")
            self.assertEqual(
                existing,
                conn.execute(
                    "SELECT project_id FROM ai_items WHERE kind='project'"
                ).fetchone()[0],
            )
            self.assertEqual(
                existing,
                EntityResolver(conn).entity(
                    "project", "Georgia L.P.", allow_create=False
                ),
            )
            conn.close()

    def test_ambiguous_duplicate_projects_queue_review_alternatives(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            conn = connect(settings)
            first = EntityResolver(conn).entity(
                "project", "Georgia LP Alpha", source="manual"
            )
            second = EntityResolver(conn).entity(
                "project", "Georgia LP Alpah", source="manual"
            )
            assert first is not None and second is not None
            conn.execute(
                "INSERT INTO chats(chat_id,title,chat_type) VALUES (106,'Work','group')"
            )
            conn.execute(
                """INSERT INTO messages(chat_id,message_id,date,text,is_outgoing,has_media)
                   VALUES (106,1,'2026-08-22T09:00:00+00:00','Georgia LP Alpa documents',0,0)"""
            )
            batch = AIBatch(
                106,
                "Work",
                [
                    AIMessage(
                        106,
                        1,
                        None,
                        "2026-08-22T09:00:00+00:00",
                        "Georgia LP Alpa documents",
                        False,
                        "Work",
                        "group",
                    )
                ],
                "prompt",
            )
            items = [
                {
                    "kind": "project",
                    "title": "Georgia LP Alpa",
                    "details": "Document work.",
                    "status": "informational",
                    "owner": "unknown",
                    "due_date": None,
                    "person": None,
                    "company": None,
                    "project_name": None,
                    "amount": None,
                    "currency": None,
                    "confidence": 0.96,
                    "source_chat_id": 106,
                    "source_message_id": 1,
                },
                {
                    "kind": "task",
                    "title": "Send documents",
                    "details": "For Georgia LP Alpa.",
                    "status": "open",
                    "owner": "me",
                    "due_date": None,
                    "person": None,
                    "company": None,
                    "project_name": "Georgia LP Alpa",
                    "amount": None,
                    "currency": None,
                    "confidence": 0.96,
                    "source_chat_id": 106,
                    "source_message_id": 1,
                },
            ]
            saved = save_ai_success(
                conn, batch, {"summary": "Georgia documents.", "items": items}, settings
            )

            self.assertTrue(process_ai_batch(conn, saved.batch_id, settings))
            self.assertEqual(
                2, conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
            )
            reviews = conn.execute(
                """SELECT payload_json FROM review_queue
                   WHERE review_type='project_duplicate' ORDER BY review_id"""
            ).fetchall()
            self.assertEqual(2, len(reviews))
            self.assertEqual(
                {first, second},
                {
                    project_id
                    for row in reviews
                    for project_id in json.loads(row[0])["candidate_project_ids"]
                },
            )
            conn.close()

    def test_duplicate_project_scan_includes_candidates_beyond_recent_window(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            conn = connect(make_settings(Path(directory)))
            resolver = EntityResolver(conn)
            earliest = resolver.entity("project", "Georgia LP", source="manual")
            assert earliest is not None
            for index in range(80):
                resolver.entity(
                    "project", f"Unrelated project {index}", source="manual"
                )

            self.assertEqual(
                (earliest,), _likely_duplicate_projects(conn, "Georgia L.P.")
            )
            conn.close()

    def test_single_batch_project_is_reviewed_without_stronger_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            conn = connect(settings)
            resolver = EntityResolver(conn)
            project_id = resolver.entity("project", "Georgia LP", source="manual")
            assert project_id is not None
            conn.execute(
                "INSERT INTO chats(chat_id,title,chat_type) VALUES (102,'Work','group')"
            )
            conn.execute(
                """INSERT INTO ai_items(batch_id,kind,title,details,status,owner,confidence,
                   source_chat_id,source_message_id,source_date,project_id,created_at,dedupe_key)
                   VALUES (2,'project','Georgia LP','','informational','unknown',0.96,
                   102,1,'2026-08-22T09:00:00+00:00',?,'now','batch-project')""",
                (project_id,),
            )
            reconciler = TaskReconciler(conn, settings)
            resolution = resolve_task_project(
                conn,
                chat_id=102,
                message_id=2,
                occurred_at="2026-08-22T09:05:00+00:00",
                title="Send documents",
                details="Unrelated wording",
                person_id=None,
                company_id=None,
                message_projects=set(),
                batch_projects={project_id},
            )
            task_id = reconciler.process_item(
                (3, "task", "Send documents", "", "open", "me", None, 0.96, 102),
                None,
                None,
                None,
            )
            assert task_id is not None
            self.assertTrue(
                reconciler.queue_project_review(task_id, 3, resolution, 102)
            )
            self.assertFalse(
                reconciler.queue_project_review(task_id, 3, resolution, 102)
            )

            self.assertIsNone(
                conn.execute(
                    "SELECT related_project_id FROM tasks WHERE task_id=?", (task_id,)
                ).fetchone()[0]
            )
            self.assertEqual(
                "graph_task_link",
                conn.execute("SELECT review_type FROM review_queue").fetchone()[0],
            )

    def test_matched_task_enriches_missing_project_without_replacing_existing_link(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            conn = connect(settings)
            resolver = EntityResolver(conn)
            first = resolver.entity("project", "Georgia LP", source="manual")
            second = resolver.entity("project", "Dubai LP", source="manual")
            assert first and second
            task_id = conn.execute(
                """INSERT INTO tasks(title,normalized_title,status,owner,source_chat_id,confidence,
                   created_at,updated_at) VALUES ('Send documents','send documents','open','me',103,0.9,'now','now')"""
            ).lastrowid
            assert task_id is not None
            reconciler = TaskReconciler(conn, settings)

            reconciler.process_item(
                (4, "task", "Send documents", "", "open", "me", None, 0.96, 103),
                None,
                None,
                first,
            )
            self.assertEqual(
                first,
                conn.execute(
                    "SELECT related_project_id FROM tasks WHERE task_id=?", (task_id,)
                ).fetchone()[0],
            )
            reconciler.process_item(
                (5, "task", "Send documents", "", "open", "me", None, 0.96, 103),
                None,
                None,
                second,
            )
            self.assertEqual(
                first,
                conn.execute(
                    "SELECT related_project_id FROM tasks WHERE task_id=?", (task_id,)
                ).fetchone()[0],
            )

    def test_task_project_backfill_is_bounded_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            conn = connect(settings)
            project_id = EntityResolver(conn).entity("project", "Georgia LP")
            assert project_id is not None
            conn.execute(
                "INSERT INTO chats(chat_id,title,chat_type) VALUES (104,'Work','group')"
            )
            conn.execute(
                """INSERT INTO ai_items(batch_id,kind,title,details,status,owner,confidence,
                   source_chat_id,source_message_id,source_date,project_id,created_at,dedupe_key)
                   VALUES (3,'project','Georgia LP','','informational','unknown',0.96,
                   104,1,'2026-08-22T09:00:00+00:00',?,'now','repair-project')""",
                (project_id,),
            )
            item_id = conn.execute(
                """INSERT INTO ai_items(batch_id,kind,title,details,status,owner,confidence,
                   source_chat_id,source_message_id,source_date,created_at,dedupe_key)
                   VALUES (3,'task','Send docs','','open','me',0.96,104,1,
                   '2026-08-22T09:00:00+00:00','now','repair-task')"""
            ).lastrowid
            conn.execute(
                """INSERT INTO tasks(title,normalized_title,status,owner,source_chat_id,
                   source_item_id,confidence,created_at,updated_at)
                   VALUES ('Send docs','send docs','open','me',104,?,0.96,'now','now')""",
                (item_id,),
            )

            self.assertEqual(
                (1, 0), backfill_task_project_links(conn, settings, limit=1)
            )
            self.assertEqual(
                (0, 0), backfill_task_project_links(conn, settings, limit=1)
            )
            self.assertEqual(
                project_id,
                conn.execute("SELECT related_project_id FROM tasks").fetchone()[0],
            )

    def test_low_confidence_and_manual_task_are_queued_for_review(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            conn = connect(settings)
            conn.execute(
                "INSERT INTO tasks(title, normalized_title, status, owner, source_chat_id, confidence, manual_status_locked, created_at, updated_at) VALUES ('Send invoice', 'send invoice', 'open', 'me', 100, 1, 1, '2026-08-20T00:00:00+00:00', '2026-08-20T00:00:00+00:00')"
            )
            # A low-confidence candidate is reviewable but cannot create a task.
            from alex_memory.operational import TaskReconciler

            reconciler = TaskReconciler(conn, settings)
            reconciler.process_item(
                (1, "task", "Send invoice", "", "done", "me", None, 0.70, 100),
                None,
                None,
                None,
            )
            self.assertEqual(
                "open", conn.execute("SELECT status FROM tasks").fetchone()[0]
            )
            self.assertEqual(
                1, conn.execute("SELECT COUNT(*) FROM review_queue").fetchone()[0]
            )
            self.assertTrue(manually_update_task(conn, 1, "done"))
            self.assertEqual(
                ("done", 1),
                conn.execute(
                    "SELECT status, manual_status_locked FROM tasks"
                ).fetchone(),
            )

    def test_blocked_task_lifecycle_preserves_manual_authority(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            conn = connect(settings)
            conn.execute(
                """INSERT INTO tasks(title,normalized_title,status,owner,source_chat_id,
                   confidence,created_at,updated_at)
                   VALUES ('Await regulator','await regulator','open','me',100,1,'now','now')"""
            )

            self.assertTrue(manually_update_task(conn, 1, "blocked"))
            TaskReconciler(conn, settings).process_item(
                (1, "task", "Await regulator", "", "open", "me", None, 0.96, 100),
                None,
                None,
                None,
            )

            self.assertEqual(
                ("blocked", 1),
                conn.execute(
                    "SELECT status,manual_status_locked FROM tasks WHERE task_id=1"
                ).fetchone(),
            )
            self.assertEqual(
                1,
                conn.execute(
                    "SELECT COUNT(*) FROM task_events WHERE task_id=1 AND event_type='manual_update'"
                ).fetchone()[0],
            )
            self.assertEqual(
                1, conn.execute("SELECT COUNT(*) FROM review_queue").fetchone()[0]
            )
            TaskReconciler(conn, settings).process_item(
                (
                    2,
                    "task",
                    "Supplier unavailable",
                    "",
                    "blocked",
                    "me",
                    None,
                    0.96,
                    101,
                ),
                None,
                None,
                None,
            )
            self.assertEqual(
                "blocked",
                conn.execute(
                    "SELECT status FROM tasks WHERE normalized_title='supplier unavailable'"
                ).fetchone()[0],
            )
            conn.close()

    def test_unanchored_similar_tasks_do_not_merge(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            conn = connect(settings)
            conn.execute(
                """INSERT INTO tasks(title,normalized_title,status,owner,source_chat_id,
                   confidence,created_at,updated_at) VALUES
                   ('Send invoice','send invoice','open','me',105,1.0,'now','now')"""
            )
            TaskReconciler(conn, settings).process_item(
                (6, "task", "Send invoices", "", "open", "me", None, 0.96, 105),
                None,
                None,
                None,
            )
            self.assertEqual(
                2, conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
            )

    def test_conflicting_known_anchor_prevents_same_title_merge(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            conn = connect(settings)
            resolver = EntityResolver(conn)
            first = resolver.person("Ari", source="manual")
            second = resolver.person("Mariam", source="manual")
            assert first is not None
            assert second is not None
            conn.execute(
                """INSERT INTO tasks(title,normalized_title,status,owner,
                   related_person_id,source_chat_id,confidence,created_at,updated_at)
                   VALUES ('Send invoice','send invoice','open','me',?,107,1.0,'now','now')""",
                (first,),
            )

            TaskReconciler(conn, settings).process_item(
                (8, "task", "Send invoice", "", "open", "me", None, 0.96, 107),
                second,
                None,
                None,
            )

            self.assertEqual(
                2, conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
            )
            self.assertEqual(
                {first, second},
                {
                    row[0]
                    for row in conn.execute(
                        "SELECT related_person_id FROM tasks WHERE source_chat_id=107"
                    ).fetchall()
                },
            )

    def test_matching_known_anchor_permits_terminal_title_match(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            conn = connect(settings)
            person_id = EntityResolver(conn).person("Ari", source="manual")
            assert person_id is not None
            task_id = conn.execute(
                """INSERT INTO tasks(title,normalized_title,status,owner,
                   related_person_id,source_chat_id,confidence,created_at,updated_at)
                   VALUES ('Send invoice','send invoice','waiting','me',?,108,1.0,'now','now')""",
                (person_id,),
            ).lastrowid
            assert task_id is not None

            TaskReconciler(conn, settings).process_item(
                (9, "task", "Send invoice", "Paid", "done", "me", None, 0.96, 108),
                person_id,
                None,
                None,
            )

            self.assertEqual(
                "done",
                conn.execute(
                    "SELECT status FROM tasks WHERE task_id=?", (task_id,)
                ).fetchone()[0],
            )

    def test_conflicting_company_or_project_anchor_prevents_merge(self) -> None:
        for anchor_type, column in (
            ("company", "related_company_id"),
            ("project", "related_project_id"),
        ):
            with (
                self.subTest(anchor_type=anchor_type),
                tempfile.TemporaryDirectory() as directory,
            ):
                settings = make_settings(Path(directory))
                conn = connect(settings)
                resolver = EntityResolver(conn)
                first = resolver.entity(anchor_type, "First", source="manual")
                second = resolver.entity(anchor_type, "Second", source="manual")
                assert first is not None
                assert second is not None
                conn.execute(
                    f"""INSERT INTO tasks(title,normalized_title,status,owner,{column},
                       source_chat_id,confidence,created_at,updated_at)
                       VALUES ('Send invoice','send invoice','open','me',?,109,1.0,'now','now')""",
                    (first,),
                )

                TaskReconciler(conn, settings).process_item(
                    (10, "task", "Send invoice", "", "open", "me", None, 0.96, 109),
                    None,
                    second if anchor_type == "company" else None,
                    second if anchor_type == "project" else None,
                )

                self.assertEqual(
                    2, conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
                )

    def test_distant_fuzzy_anchored_task_does_not_merge(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            conn = connect(settings)
            person_id = EntityResolver(conn).person("Ari", source="manual")
            assert person_id is not None
            source_item_id = conn.execute(
                """INSERT INTO ai_items(batch_id,kind,title,details,status,owner,confidence,
                   source_chat_id,source_message_id,source_date,created_at,dedupe_key)
                   VALUES (1,'task','Send invoice','','open','me',0.96,110,1,
                   '2026-01-01T10:00:00+00:00','now','old-task-evidence')"""
            ).lastrowid
            assert source_item_id is not None
            conn.execute(
                """INSERT INTO tasks(title,normalized_title,status,owner,
                   related_person_id,source_chat_id,source_item_id,confidence,
                   created_at,updated_at)
                   VALUES ('Send invoice','send invoice','open','me',?,110,?,1.0,
                   '2026-01-01T10:00:00+00:00','2026-01-01T10:00:00+00:00')""",
                (person_id, source_item_id),
            )

            TaskReconciler(conn, settings).process_item(
                (11, "task", "Send invoices", "", "open", "me", None, 0.96, 110),
                person_id,
                None,
                None,
                source_at="2026-08-01T10:00:00+00:00",
            )

            self.assertEqual(
                2, conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
            )

    def test_terminal_item_updates_the_matching_anchored_task(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            conn = connect(settings)
            person_id = EntityResolver(conn).person("Michael")
            assert person_id is not None
            task_id = conn.execute(
                """INSERT INTO tasks(title,normalized_title,status,owner,related_person_id,
                   source_chat_id,confidence,created_at,updated_at)
                   VALUES ('Receive documents','receive documents','waiting','other',?,106,
                   1.0,'now','now')""",
                (person_id,),
            ).lastrowid
            TaskReconciler(conn, settings).process_item(
                (
                    7,
                    "task",
                    "Receive documents",
                    "Confirmed",
                    "done",
                    "other",
                    None,
                    0.96,
                    106,
                ),
                person_id,
                None,
                None,
            )
            self.assertEqual(
                "done",
                conn.execute(
                    "SELECT status FROM tasks WHERE task_id=?", (task_id,)
                ).fetchone()[0],
            )
            self.assertEqual(
                "completed",
                conn.execute(
                    "SELECT event_type FROM task_events WHERE task_id=? ORDER BY event_id DESC",
                    (task_id,),
                ).fetchone()[0],
            )

    def test_terminal_cancellation_links_to_matching_anchored_task(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            conn = connect(settings)
            project_id = EntityResolver(conn).entity("project", "Amber")
            assert project_id is not None
            task_id = conn.execute(
                """INSERT INTO tasks(title,normalized_title,status,owner,
                   related_project_id,source_chat_id,confidence,created_at,updated_at)
                   VALUES ('Send invoice','send invoice','open','me',?,111,1.0,'now','now')""",
                (project_id,),
            ).lastrowid
            assert task_id is not None

            TaskReconciler(conn, settings).process_item(
                (
                    12,
                    "task",
                    "Send invoice",
                    "Cancelled",
                    "canceled",
                    "me",
                    None,
                    0.96,
                    111,
                ),
                None,
                None,
                project_id,
            )

            self.assertEqual(
                ("canceled", "canceled"),
                conn.execute(
                    """SELECT t.status,e.event_type FROM tasks AS t
                       JOIN task_events AS e ON e.task_id=t.task_id
                       WHERE t.task_id=? ORDER BY e.event_id DESC LIMIT 1""",
                    (task_id,),
                ).fetchone(),
            )

    def test_generic_review_decision_is_durable_feedback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            conn = connect(make_settings(Path(directory)))
            cursor = conn.execute(
                """INSERT INTO review_queue(review_type,subject_type,subject_id,payload_json,created_at)
                   VALUES ('task_update','task',12,'{"candidate":"done"}','2026-01-01')"""
            )
            resolve_review_item(conn, int(cursor.lastrowid), "reject")
            self.assertEqual(
                "rejected",
                conn.execute("SELECT status FROM review_queue").fetchone()[0],
            )
            feedback = conn.execute(
                "SELECT feedback_type,payload_json FROM user_feedback"
            ).fetchone()
            self.assertEqual("review:task_update", feedback[0])
            self.assertIn('"action": "reject"', feedback[1])

    def test_entity_merge_review_moves_canonical_references(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            conn = connect(make_settings(Path(directory)))
            resolver = EntityResolver(conn)
            keep = resolver.person("Ilya One")
            discard = resolver.person("Ilya Two")
            assert keep and discard
            conn.execute(
                """INSERT INTO tasks(title,normalized_title,status,owner,related_person_id,
                   confidence,created_at,updated_at)
                   VALUES ('Call Ilya','call ilya','open','me',?,1.0,'now','now')""",
                (discard,),
            )
            entity_ids = json.dumps([keep, discard])
            cursor = conn.execute(
                """INSERT INTO review_queue(review_type,subject_type,payload_json,created_at)
                   VALUES ('entity_merge','person',?,'now')""",
                (json.dumps({"alias": "ilya", "entity_ids": [keep, discard]}),),
            )
            conn.execute(
                """INSERT INTO entity_merge_candidates(entity_type,normalized_alias,entity_ids_json,
                   reason,created_at) VALUES ('person','ilya',?,'test','now')""",
                (entity_ids,),
            )

            resolve_review_item(
                conn,
                int(cursor.lastrowid),
                "accept",
                edited_payload={"keep_entity_id": keep},
            )

            self.assertEqual(
                keep,
                conn.execute("SELECT related_person_id FROM tasks").fetchone()[0],
            )
            self.assertEqual(
                "merged",
                conn.execute(
                    "SELECT status FROM people WHERE person_id=?", (discard,)
                ).fetchone()[0],
            )
            self.assertEqual(
                "resolved",
                conn.execute("SELECT status FROM entity_merge_candidates").fetchone()[
                    0
                ],
            )
            conn.close()

    def test_identity_reconciliation_preview_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            conn = connect(make_settings(Path(directory)))
            resolver = EntityResolver(conn)
            first = resolver.person("David", telegram_user_id=11)
            second = resolver.person("David", telegram_user_id=22)
            assert first is not None and second is not None
            review_id = conn.execute(
                """INSERT INTO review_queue(review_type,subject_type,payload_json,created_at)
                   VALUES ('entity_merge','person',?,'now')""",
                (
                    json.dumps(
                        {
                            "alias": "david",
                            "entity_ids": [first, second],
                            "reason": "test",
                        }
                    ),
                ),
            ).lastrowid
            assert review_id is not None
            before = conn.total_changes

            preview = identity_reconciliation_preview(conn, int(review_id))

            self.assertEqual(before, conn.total_changes)
            self.assertEqual(
                [first, second], [row["person_id"] for row in preview["candidates"]]
            )
            self.assertEqual(
                [11, 22], [row["telegram_user_id"] for row in preview["candidates"]]
            )

    def test_identity_review_can_link_alias_only_to_a_reviewed_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            conn = connect(make_settings(Path(directory)))
            resolver = EntityResolver(conn)
            first = resolver.person("David One", telegram_user_id=11)
            second = resolver.person("David Two", telegram_user_id=22)
            assert first is not None and second is not None
            resolver._alias("person", first, "David", "test", 1.0)
            resolver._alias("person", second, "David", "test", 1.0)
            review_id = conn.execute(
                """INSERT INTO review_queue(review_type,subject_type,payload_json,created_at)
                   VALUES ('entity_merge','person',?,'now')""",
                (
                    json.dumps(
                        {
                            "alias": "david",
                            "entity_ids": [first, second],
                            "reason": "test",
                        }
                    ),
                ),
            ).lastrowid
            assert review_id is not None

            resolve_review_item(
                conn,
                int(review_id),
                "link_alias",
                edited_payload={"target_entity_id": second},
            )

            self.assertEqual(
                [second],
                [
                    row[0]
                    for row in conn.execute(
                        "SELECT entity_id FROM entity_aliases WHERE entity_type='person' AND normalized_alias='david'"
                    )
                ],
            )
            self.assertEqual(
                "approved",
                conn.execute("SELECT status FROM review_queue").fetchone()[0],
            )

    def test_identity_review_does_not_replace_manual_alias_owner(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            conn = connect(make_settings(Path(directory)))
            resolver = EntityResolver(conn)
            first = resolver.person("David One", telegram_user_id=11)
            second = resolver.person("David Two", telegram_user_id=22)
            assert first is not None and second is not None
            resolver._alias("person", first, "David", "manual", 1.0)
            resolver._alias("person", second, "David", "test", 1.0)
            review_id = conn.execute(
                """INSERT INTO review_queue(review_type,subject_type,payload_json,created_at)
                   VALUES ('entity_merge','person',?,'now')""",
                (json.dumps({"alias": "david", "entity_ids": [first, second]}),),
            ).lastrowid
            assert review_id is not None
            conn.commit()

            with self.assertRaisesRegex(ValueError, "manually owned"):
                resolve_review_item(
                    conn,
                    int(review_id),
                    "link_alias",
                    edited_payload={"target_entity_id": second},
                )

            self.assertEqual(
                [first, second],
                [
                    row[0]
                    for row in conn.execute(
                        "SELECT entity_id FROM entity_aliases WHERE entity_type='person' AND normalized_alias='david' ORDER BY entity_id"
                    )
                ],
            )
            self.assertEqual(
                "pending",
                conn.execute("SELECT status FROM review_queue").fetchone()[0],
            )

    def test_identity_review_separate_and_unresolved_preserve_contacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            conn = connect(make_settings(Path(directory)))
            resolver = EntityResolver(conn)
            first = resolver.person("David One", telegram_user_id=11)
            second = resolver.person("David Two", telegram_user_id=22)
            assert first is not None and second is not None
            resolver._alias("person", first, "David", "test", 1.0)
            resolver._alias("person", second, "David", "test", 1.0)
            for action in ("reject", "ignore"):
                review_id = conn.execute(
                    """INSERT INTO review_queue(review_type,subject_type,payload_json,created_at)
                       VALUES ('entity_merge','person',?,'now')""",
                    (json.dumps({"alias": "david", "entity_ids": [first, second]}),),
                ).lastrowid
                assert review_id is not None

                resolve_review_item(conn, int(review_id), action)

            self.assertEqual(
                [first, second],
                [
                    row[0]
                    for row in conn.execute(
                        "SELECT entity_id FROM entity_aliases WHERE entity_type='person' AND normalized_alias='david' ORDER BY entity_id"
                    )
                ],
            )
            self.assertEqual(
                ["active", "active"],
                [
                    row[0]
                    for row in conn.execute(
                        "SELECT status FROM people WHERE person_id IN (?, ?) ORDER BY person_id",
                        (first, second),
                    )
                ],
            )
            self.assertEqual(
                2,
                conn.execute(
                    "SELECT COUNT(*) FROM user_feedback WHERE feedback_type='review:entity_merge'"
                ).fetchone()[0],
            )

    def test_project_merge_review_preserves_source_observation_reference(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            conn = connect(make_settings(Path(directory)))
            resolver = EntityResolver(conn)
            keep = resolver.entity("project", "Georgia LP", source="manual")
            discard = resolver.entity("project", "Georgia L.P.", source="manual")
            assert keep is not None and discard is not None
            item_id = conn.execute(
                """INSERT INTO ai_items(batch_id,kind,title,details,status,owner,confidence,
                       source_chat_id,source_message_id,project_id,created_at,dedupe_key)
                   VALUES (1,'project','Georgia L.P.','','informational','unknown',0.96,
                           1,1,?,'now','project-merge-source')""",
                (discard,),
            ).lastrowid
            assert item_id is not None
            review_id = conn.execute(
                """INSERT INTO review_queue(review_type,subject_type,payload_json,created_at)
                   VALUES ('entity_merge','project',?,'now')""",
                (json.dumps({"alias": "georgia l.p.", "entity_ids": [keep, discard]}),),
            ).lastrowid
            conn.execute(
                """INSERT INTO entity_merge_candidates(entity_type,normalized_alias,entity_ids_json,
                       reason,created_at) VALUES ('project','georgia l.p.',?,'test','now')""",
                (json.dumps([keep, discard]),),
            )
            assert review_id is not None

            resolve_review_item(
                conn,
                int(review_id),
                "accept",
                edited_payload={"keep_entity_id": keep},
            )

            self.assertEqual(
                keep,
                conn.execute(
                    "SELECT project_id FROM ai_items WHERE item_id=?", (item_id,)
                ).fetchone()[0],
            )
            self.assertEqual(
                "merged",
                conn.execute(
                    "SELECT status FROM projects WHERE project_id=?", (discard,)
                ).fetchone()[0],
            )
            conn.close()

    def test_accepted_task_review_uses_the_task_reconciler(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            conn = connect(settings)
            conn.execute(
                "INSERT INTO chats(chat_id,title,chat_type) VALUES (1,'Alice','user')"
            )
            item = conn.execute(
                """INSERT INTO ai_items(batch_id,kind,title,details,status,owner,confidence,
                   source_chat_id,source_message_id,created_at,dedupe_key)
                   VALUES (1,'task','Send invoice','Requested invoice','open','me',0.7,1,1,'now','review-task')"""
            )
            review = conn.execute(
                """INSERT INTO review_queue(review_type,subject_type,subject_id,payload_json,created_at)
                   VALUES ('task_change','ai_item',?,?,'now')""",
                (item.lastrowid, json.dumps({"item_id": item.lastrowid})),
            )

            resolve_review_item(
                conn, int(review.lastrowid), "accept", settings=settings
            )

            self.assertEqual(
                1, conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
            )
            self.assertEqual(
                "approved",
                conn.execute("SELECT status FROM review_queue").fetchone()[0],
            )
            conn.close()

    def test_classification_review_edit_updates_the_routing_record(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            conn = connect(make_settings(Path(directory)))
            conn.execute(
                "INSERT INTO chats(chat_id,title,chat_type) VALUES (1,'Alice','user')"
            )
            conn.execute(
                "INSERT INTO messages(chat_id,message_id,text) VALUES (1,1,'Please send it')"
            )
            message = AIMessage(
                1, 1, None, None, "Please send it", False, "Alice", "user"
            )
            save_classification(conn, message, classify_message(conn, message))
            review = conn.execute(
                """INSERT INTO review_queue(review_type,subject_type,subject_id,payload_json,created_at)
                   VALUES ('message_classification','message',1,?,'now')""",
                (json.dumps({"chat_id": 1, "message_id": 1}),),
            )

            resolve_review_item(
                conn,
                int(review.lastrowid),
                "edit",
                edited_payload={
                    "information_scope": "external_news",
                    "content_type": "news",
                },
            )

            self.assertEqual(
                ("external_news", "external_news", "news"),
                conn.execute(
                    """SELECT information_scope,content_scope,content_type
                       FROM message_classifications WHERE chat_id=1 AND message_id=1"""
                ).fetchone(),
            )
            conn.close()
