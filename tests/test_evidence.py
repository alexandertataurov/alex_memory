from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from alex_memory.database import connect
from alex_memory.evidence import EvidenceRecord, EvidenceRepository
from alex_memory.telegram.evidence import TelegramEvidenceSource
from test_ai_pipeline import make_settings


class EvidenceContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.settings = make_settings(Path(self.directory.name))
        self.conn = connect(self.settings)

    def tearDown(self) -> None:
        self.conn.close()
        self.directory.cleanup()

    def test_repository_retains_source_identity_and_edit_delete_history(self) -> None:
        repository = EvidenceRepository(self.conn)
        original = EvidenceRecord(
            source_name="gmail",
            source_account_id="alex@example.test",
            conversation_id="thread-9",
            source_item_id="message-14",
            observed_at="2026-08-22T10:00:00+00:00",
            occurred_at="2026-08-22T09:00:00+00:00",
            author_id="person-4",
            content="Initial email body",
            raw_locator={"thread_id": "thread-9", "message_id": "message-14"},
            metadata={"subject": "Invoice"},
        )
        evidence_id = repository.save(original)
        repository.save(
            replace(
                original,
                content="Corrected email body",
                edited_at="2026-08-22T10:05:00+00:00",
                observed_at="2026-08-22T10:05:00+00:00",
            )
        )
        repository.save(
            replace(
                original,
                content="Corrected email body",
                is_deleted=True,
                deleted_at="2026-08-22T10:10:00+00:00",
                observed_at="2026-08-22T10:10:00+00:00",
            )
        )
        stored = repository.get(original.identity)
        assert stored is not None
        self.assertTrue(stored.is_deleted)
        self.assertEqual("Invoice", stored.metadata["subject"])
        self.assertEqual(
            ["initial", "edited", "deleted"],
            [reason for _, _, reason in repository.versions(evidence_id)],
        )

    def test_telegram_adapter_preserves_native_locator_and_lifecycle_state(
        self,
    ) -> None:
        self.conn.execute(
            "INSERT INTO chats(chat_id,title,chat_type,updated_at) VALUES (10,'[Test] chat','user','2026-08-22')"
        )
        self.conn.execute(
            """INSERT INTO messages(chat_id,message_id,sender_id,date,text,is_outgoing,has_media,
               edited_at,is_deleted,deleted_at) VALUES (10,2,3,?,?,?,?,?,?,?)""",
            (
                "2026-08-22T09:00:00+00:00",
                "Original Telegram message",
                0,
                0,
                "2026-08-22T09:03:00+00:00",
                1,
                "2026-08-22T09:04:00+00:00",
            ),
        )
        self.conn.commit()
        record = TelegramEvidenceSource(self.conn).get("10", "2")
        assert record is not None
        self.assertTrue(record.is_deleted)
        self.assertEqual({"chat_id": 10, "message_id": 2}, record.raw_locator)
        self.assertEqual("[Test] chat", record.metadata["chat_title"])

    def test_repository_save_participates_in_outer_transaction(self) -> None:
        record = EvidenceRecord(
            source_name="gmail",
            source_account_id="alex@example.test",
            conversation_id="thread-rollback",
            source_item_id="message-1",
            observed_at="2026-08-22T10:00:00+00:00",
            content="Uncommitted evidence",
        )
        repository = EvidenceRepository(self.conn)
        repository.save(record)
        self.conn.rollback()

        self.assertIsNone(repository.get(record.identity))
        self.assertEqual(
            0,
            self.conn.execute(
                "SELECT COUNT(*) FROM source_evidence_versions"
            ).fetchone()[0],
        )
