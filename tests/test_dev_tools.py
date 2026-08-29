from __future__ import annotations

import tempfile
import unittest
import importlib.util
from pathlib import Path

from test_ai_pipeline import make_settings
from alex_memory.database import connect


_SPEC = importlib.util.spec_from_file_location(
    "dev_tools", Path(__file__).parents[1] / "scripts" / "dev_tools.py"
)
assert _SPEC is not None and _SPEC.loader is not None
dev_tools = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(dev_tools)


class LogicalReferenceDiagnosticsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.conn = connect(make_settings(Path(self.directory.name)))

    def tearDown(self) -> None:
        self.conn.close()
        self.directory.cleanup()

    def test_reports_actionable_orphan_without_writing(self) -> None:
        self.conn.execute(
            """INSERT INTO source_evidence_versions(
                   evidence_id,content,captured_at,reason
               ) VALUES (999,'redacted','now','initial')"""
        )
        changes_before = self.conn.total_changes

        self.assertEqual(
            [("source_evidence_versions", "evidence_id", 1)],
            dev_tools.logical_reference_violations(self.conn),
        )
        self.assertEqual(changes_before, self.conn.total_changes)

    def test_reports_unknown_or_missing_relationship_endpoints(self) -> None:
        self.conn.execute(
            """INSERT INTO relationships(
                   from_type,from_id,to_type,to_id,relationship_type,valid_from,
                   confidence,created_at,updated_at
               ) VALUES ('person',999,'unknown',888,'works_with','now',1.0,'now','now')"""
        )

        self.assertEqual(
            [
                ("relationships", "from_endpoint", 1),
                ("relationships", "to_endpoint", 1),
            ],
            dev_tools.logical_reference_violations(self.conn),
        )
