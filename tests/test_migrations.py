from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from alex_memory.database import (
    MIGRATIONS,
    SCHEMA_VERSION,
    _bootstrap_schema,
    _apply_migrations,
    _add_profile_ai_lane,
    _add_ai_job_retry_schedule,
    connect,
    migration_history,
    schema_version,
)
from alex_memory.schema_support import COMPATIBILITY_COLUMNS
from alex_memory.schema_support import FTS_TRIGGERS, fts_index_health
from test_ai_pipeline import make_settings


class MigrationLedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.settings = make_settings(Path(self.directory.name))

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_fresh_database_records_each_ordered_migration(self) -> None:
        conn = connect(self.settings)
        try:
            history = migration_history(conn)
            self.assertEqual(SCHEMA_VERSION, schema_version(conn))
            self.assertEqual(
                [migration.version for migration in MIGRATIONS],
                [version for version, _, _ in history],
            )
            self.assertEqual(
                [migration.name for migration in MIGRATIONS],
                [name for _, name, _ in history],
            )
            self.assertIsNotNone(
                conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='conversation_segments'"
                ).fetchone()
            )
            self.assertIsNotNone(
                conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='ai_model_usage'"
                ).fetchone()
            )
        finally:
            conn.close()

    def test_profile_lane_upgrade_preserves_existing_job_and_membership(self) -> None:
        conn = connect(self.settings)
        try:
            job_id = conn.execute(
                """INSERT INTO ai_jobs(
                       lane,chat_id,first_message_id,last_message_id,message_count,
                       analysis_version,selection_fingerprint,status,created_at,
                       profile_person_id,profile_extractor_version
                   ) VALUES ('history',5,1,1,1,2,'before-profile-lane','failed','now',9,1)"""
            ).lastrowid
            conn.execute(
                "INSERT INTO ai_job_messages(job_id,ordinal,chat_id,message_id) VALUES (?,0,5,1)",
                (job_id,),
            )
            conn.commit()

            with conn:
                _add_profile_ai_lane(conn)

            self.assertEqual(
                ("history", 9, 1, "failed"),
                conn.execute(
                    """SELECT lane,profile_person_id,profile_extractor_version,status
                       FROM ai_jobs WHERE job_id=?""",
                    (job_id,),
                ).fetchone(),
            )
            self.assertEqual(
                [(5, 1)],
                conn.execute(
                    "SELECT chat_id,message_id FROM ai_job_messages WHERE job_id=?",
                    (job_id,),
                ).fetchall(),
            )
            conn.execute(
                """INSERT INTO ai_jobs(
                       lane,chat_id,first_message_id,last_message_id,message_count,
                       analysis_version,selection_fingerprint,status,created_at
                   ) VALUES ('profile',6,1,1,1,2,'profile-lane','pending','now')"""
            )
        finally:
            conn.close()

    def test_retry_schedule_upgrade_preserves_membership_and_requeues_history(
        self,
    ) -> None:
        conn = connect(self.settings)
        try:
            job_id = conn.execute(
                """INSERT INTO ai_jobs(
                       lane,chat_id,first_message_id,last_message_id,message_count,
                       analysis_version,selection_fingerprint,status,created_at
                   ) VALUES ('history',5,1,1,1,2,'retry-schedule','failed','now')"""
            ).lastrowid
            conn.execute(
                "INSERT INTO ai_job_messages(job_id,ordinal,chat_id,message_id) VALUES (?,0,5,1)",
                (job_id,),
            )
            with conn:
                _add_ai_job_retry_schedule(conn)
            self.assertEqual(
                ("pending", None),
                conn.execute(
                    "SELECT status,retry_after_at FROM ai_jobs WHERE job_id=?",
                    (job_id,),
                ).fetchone(),
            )
            self.assertEqual(
                [(5, 1)],
                conn.execute(
                    "SELECT chat_id,message_id FROM ai_job_messages WHERE job_id=?",
                    (job_id,),
                ).fetchall(),
            )
        finally:
            conn.close()

    def test_bootstrap_does_not_execute_later_migration_tables(self) -> None:
        conn = sqlite3.connect(":memory:")
        try:
            _bootstrap_schema(conn)
            for table in (
                "source_evidence",
                "message_classifications",
                "conversation_segments",
                "current_conversation_context",
            ):
                self.assertIsNone(
                    conn.execute(
                        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                        (table,),
                    ).fetchone(),
                    table,
                )
        finally:
            conn.close()

    def test_compatibility_columns_are_not_runtime_mutable(self) -> None:
        with self.assertRaises(TypeError):
            COMPATIBILITY_COLUMNS["chats"] = {}  # type: ignore[index]
        with self.assertRaises(TypeError):
            COMPATIBILITY_COLUMNS["chats"]["other"] = "TEXT"  # type: ignore[index]

    def test_legacy_lane_only_chat_policies_adopt_as_auto(self) -> None:
        conn = connect(self.settings)
        conn.execute("DELETE FROM schema_migrations WHERE version=8")
        conn.execute("ALTER TABLE chat_ai_policy RENAME TO chat_ai_policy_current")
        conn.execute(
            """CREATE TABLE chat_ai_policy (
                   chat_id INTEGER PRIMARY KEY,
                   mode TEXT NOT NULL CHECK(mode IN ('auto','include','exclude','daily_only','history_only')),
                   reason TEXT,updated_at TEXT NOT NULL)"""
        )
        conn.execute(
            "INSERT INTO chat_ai_policy(chat_id,mode,reason,updated_at) VALUES (1,'daily_only','legacy','now')"
        )
        conn.execute("DROP TABLE chat_ai_policy_current")
        conn.commit()
        conn.close()

        conn = connect(self.settings)
        self.assertEqual(
            ("auto", "legacy"),
            conn.execute(
                "SELECT mode,reason FROM chat_ai_policy WHERE chat_id=1"
            ).fetchone(),
        )
        conn.close()

    def test_legacy_database_adopts_ledger_and_compatibility_columns_once(self) -> None:
        self.settings.data_dir.mkdir(parents=True)
        with sqlite3.connect(self.settings.db_path) as legacy:
            legacy.execute(
                """CREATE TABLE ai_batches (
                       batch_id INTEGER PRIMARY KEY AUTOINCREMENT,
                       model TEXT NOT NULL,
                       created_at TEXT NOT NULL,
                       completed_at TEXT,
                       message_count INTEGER NOT NULL,
                       chat_id INTEGER,
                       summary TEXT,
                       error TEXT,
                       prompt_chars INTEGER NOT NULL DEFAULT 0
                   )"""
            )

        conn = connect(self.settings)
        try:
            columns = {row[1] for row in conn.execute("PRAGMA table_info(ai_batches)")}
            self.assertIn("lane", columns)
            self.assertIn("usage_json", columns)
            self.assertEqual(SCHEMA_VERSION, schema_version(conn))
            self.assertEqual(len(MIGRATIONS), len(migration_history(conn)))
        finally:
            conn.close()

        reopened = connect(self.settings)
        try:
            self.assertEqual(len(MIGRATIONS), len(migration_history(reopened)))
        finally:
            reopened.close()

    def test_legacy_tables_receive_every_declared_compatibility_column(self) -> None:
        self.settings.data_dir.mkdir(parents=True)
        with sqlite3.connect(self.settings.db_path) as legacy:
            legacy.executescript(
                """
                CREATE TABLE chats (chat_id INTEGER PRIMARY KEY, title TEXT);
                CREATE TABLE ai_batches (
                    batch_id INTEGER PRIMARY KEY, model TEXT, created_at TEXT,
                    message_count INTEGER, prompt_chars INTEGER
                );
                CREATE TABLE ai_items (
                    item_id INTEGER PRIMARY KEY, batch_id INTEGER, kind TEXT,
                    title TEXT, details TEXT, status TEXT, owner TEXT,
                    due_date TEXT,
                    confidence REAL, source_chat_id INTEGER, source_message_id INTEGER,
                    dedupe_key TEXT
                );
                CREATE TABLE messages (
                    chat_id INTEGER, message_id INTEGER, sender_id INTEGER,
                    date TEXT, text TEXT,
                    PRIMARY KEY (chat_id, message_id)
                );
                CREATE TABLE projects (
                    project_id INTEGER PRIMARY KEY, canonical_name TEXT, created_at TEXT,
                    updated_at TEXT
                );
                """
            )

        conn = connect(self.settings)
        try:
            for table, expected in COMPATIBILITY_COLUMNS.items():
                columns = {
                    row[1] for row in conn.execute(f"PRAGMA table_info({table})")
                }
                self.assertTrue(set(expected).issubset(columns), table)
            self.assertEqual(SCHEMA_VERSION, schema_version(conn))
        finally:
            conn.close()

    def test_fts_lifecycle_rebuild_backfills_legacy_source_rows(self) -> None:
        conn = connect(self.settings)
        if not fts_index_health(conn)["available"]:
            self.skipTest("SQLite was built without optional FTS5")
        conn.execute("DELETE FROM schema_migrations WHERE version=12")
        for trigger in FTS_TRIGGERS:
            conn.execute(f"DROP TRIGGER {trigger}")
        conn.execute(
            """INSERT INTO messages(chat_id,message_id,date,text,is_deleted)
               VALUES (8,1,'2026-08-24T10:00:00+00:00','Legacy FTS backfill evidence',0)"""
        )
        conn.commit()
        conn.close()

        conn = connect(self.settings)
        try:
            self.assertEqual(
                ("Legacy FTS backfill evidence",),
                conn.execute(
                    "SELECT text FROM messages_fts WHERE chat_id=8 AND message_id=1"
                ).fetchone(),
            )
            health = fts_index_health(conn)
            self.assertTrue(health["healthy"])
            self.assertEqual(1, health["indexes"]["messages"]["source_rows"])
        finally:
            conn.close()

    def test_fts_health_detects_source_index_drift(self) -> None:
        conn = connect(self.settings)
        try:
            if not fts_index_health(conn)["available"]:
                self.skipTest("SQLite was built without optional FTS5")
            conn.execute(
                """INSERT INTO messages(chat_id,message_id,date,text,is_deleted)
                   VALUES (8,1,'2026-08-24T10:00:00+00:00','Coverage evidence',0)"""
            )
            conn.execute("DELETE FROM messages_fts WHERE chat_id=8 AND message_id=1")
            health = fts_index_health(conn)
            self.assertFalse(health["healthy"])
            self.assertEqual(1, health["indexes"]["messages"]["missing_rows"])
        finally:
            conn.close()

    def test_fts_rebuild_rolls_back_when_trigger_creation_fails(self) -> None:
        conn = connect(self.settings)
        try:
            if not fts_index_health(conn)["available"]:
                self.skipTest("SQLite was built without optional FTS5")
            initial_tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%_fts'"
                )
            }
            initial_triggers = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='trigger'"
                )
                if row[0] in FTS_TRIGGERS
            }
            conn.execute("DELETE FROM schema_migrations WHERE version=12")
            conn.commit()

            def deny_trigger_creation(action: int, *_: object) -> int:
                return (
                    sqlite3.SQLITE_DENY
                    if action == sqlite3.SQLITE_CREATE_TRIGGER
                    else sqlite3.SQLITE_OK
                )

            conn.set_authorizer(deny_trigger_creation)
            with self.assertRaises(RuntimeError):
                _apply_migrations(conn)
            conn.set_authorizer(None)

            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%_fts'"
                )
            }
            triggers = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='trigger'"
                )
                if row[0] in FTS_TRIGGERS
            }
            self.assertEqual(initial_tables, tables)
            self.assertEqual(initial_triggers, triggers)
            self.assertTrue(fts_index_health(conn)["healthy"])
            self.assertIsNone(
                conn.execute(
                    "SELECT 1 FROM schema_migrations WHERE version=12"
                ).fetchone()
            )
        finally:
            conn.set_authorizer(None)
            conn.close()

    def test_fts_migrations_allow_an_explicitly_unavailable_module(self) -> None:
        with patch("alex_memory.schema_support.fts5_available", return_value=False):
            conn = connect(self.settings)
            try:
                self.assertIsNone(
                    conn.execute(
                        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='messages_fts'"
                    ).fetchone()
                )
                self.assertFalse(fts_index_health(conn)["available"])
            finally:
                conn.close()
