from __future__ import annotations

import tempfile
import unittest
import importlib.util
import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from test_ai_pipeline import make_settings
from alex_memory.context.repository import ensure_relationship
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

    def test_graph_parity_is_read_only_and_reports_compatibility_gap(self) -> None:
        person_id = self.conn.execute(
            "INSERT INTO people(canonical_name,created_at,updated_at) VALUES ('Ari','now','now')"
        ).lastrowid
        project_id = self.conn.execute(
            "INSERT INTO projects(canonical_name,created_at,updated_at) VALUES ('Amber','now','now')"
        ).lastrowid
        assert person_id is not None
        assert project_id is not None
        ensure_relationship(
            self.conn,
            "person",
            int(person_id),
            "project",
            int(project_id),
            "involved_in",
            0.9,
            valid_from="2026-08-24T10:00:00+00:00",
        )
        self.conn.commit()
        changes_before = self.conn.total_changes
        output = StringIO()

        with (
            patch.object(dev_tools, "readonly_connection", return_value=self.conn),
            redirect_stdout(output),
        ):
            self.assertEqual(
                0,
                dev_tools.graph_parity(
                    [f"person:{person_id}"], "2026-08-25T00:00:00+00:00", 2
                ),
            )

        report = json.loads(output.getvalue())
        self.assertFalse(report["ready"])
        self.assertFalse(report["truncated"])
        self.assertEqual(1, report["gaps"][0]["count"])
        self.assertEqual(changes_before, self.conn.total_changes)

    def test_graph_parity_rejects_malformed_seed_before_opening_database(self) -> None:
        output = StringIO()

        with redirect_stdout(output):
            self.assertEqual(
                1,
                dev_tools.graph_parity(["task:1"], "2026-08-25T00:00:00+00:00", 2),
            )

        self.assertIn("person|company|project", output.getvalue())

    def test_graph_parity_normalizes_equivalent_offset_as_of_values(self) -> None:
        person_id = self.conn.execute(
            "INSERT INTO people(canonical_name,created_at,updated_at) VALUES ('Ari','now','now')"
        ).lastrowid
        project_id = self.conn.execute(
            "INSERT INTO projects(canonical_name,created_at,updated_at) VALUES ('Amber','now','now')"
        ).lastrowid
        assert person_id is not None
        assert project_id is not None
        ensure_relationship(
            self.conn,
            "person",
            int(person_id),
            "project",
            int(project_id),
            "involved_in",
            0.9,
            valid_from="2026-08-25T00:00:00+00:00",
        )
        self.conn.commit()

        reports = []
        for as_of in ("2026-08-25T00:30:00+00:00", "2026-08-24T20:30:00-04:00"):
            output = StringIO()
            with (
                patch.object(dev_tools, "readonly_connection", return_value=self.conn),
                redirect_stdout(output),
            ):
                self.assertEqual(
                    0, dev_tools.graph_parity([f"person:{person_id}"], as_of, 2)
                )
            reports.append(json.loads(output.getvalue()))

        self.assertEqual(reports[0], reports[1])
        self.assertEqual("2026-08-25T00:30:00+00:00", reports[0]["as_of"])

    def test_graph_parity_rejects_naive_as_of_before_opening_database(self) -> None:
        output = StringIO()

        with redirect_stdout(output):
            self.assertEqual(
                1,
                dev_tools.graph_parity(["person:1"], "2026-08-25T00:00:00", 2),
            )

        self.assertIn("timezone offset", output.getvalue())

    def test_profile_acceptance_is_aggregate_only_and_read_only(self) -> None:
        person_ids = [
            self.conn.execute(
                "INSERT INTO people(canonical_name,created_at,updated_at) VALUES (?,?,?)",
                (f"Person {index}", "now", "now"),
            ).lastrowid
            for index in range(10)
        ]
        self.conn.commit()
        assert all(person_id is not None for person_id in person_ids)
        contacts = [
            f"{shape}:{person_id}"
            for shape, person_id in zip(
                (
                    "recent",
                    "dormant",
                    "group-only",
                    "multi-project",
                    "ambiguous",
                    "sparse-evidence",
                    "recent",
                    "dormant",
                    "group-only",
                    "multi-project",
                ),
                person_ids,
                strict=True,
            )
        ]
        output = StringIO()
        changes_before = self.conn.total_changes

        with (
            patch.object(dev_tools, "readonly_connection", return_value=self.conn),
            redirect_stdout(output),
        ):
            self.assertEqual(0, dev_tools.person_profile_acceptance(contacts))

        report = json.loads(output.getvalue())
        self.assertTrue(report["ready"])
        self.assertTrue(report["read_only"])
        self.assertEqual(10, report["contacts"])
        self.assertEqual(0, sum(report["violations"].values()))
        self.assertNotIn("Person 0", output.getvalue())
        self.assertEqual(changes_before, self.conn.total_changes)

    def test_profile_acceptance_reports_ungrounded_rows_without_content(self) -> None:
        person_ids = [
            self.conn.execute(
                "INSERT INTO people(canonical_name,created_at,updated_at) VALUES (?,?,?)",
                (f"Person {index}", "now", "now"),
            ).lastrowid
            for index in range(10)
        ]
        assert person_ids[0] is not None
        self.conn.execute(
            """INSERT INTO context_facts(
                   subject_type,subject_id,predicate,value_json,valid_from,observed_at,
                   confidence,created_at,updated_at
               ) VALUES ('person',?,'role','{}','now','now',0.9,'now','now')""",
            (person_ids[0],),
        )
        self.conn.commit()
        contacts = [
            f"{shape}:{person_id}"
            for shape, person_id in zip(
                (
                    "recent",
                    "dormant",
                    "group-only",
                    "multi-project",
                    "ambiguous",
                    "sparse-evidence",
                    "recent",
                    "dormant",
                    "group-only",
                    "multi-project",
                ),
                person_ids,
                strict=True,
            )
        ]
        output = StringIO()

        with (
            patch.object(dev_tools, "readonly_connection", return_value=self.conn),
            redirect_stdout(output),
        ):
            self.assertEqual(1, dev_tools.person_profile_acceptance(contacts))

        report = json.loads(output.getvalue())
        self.assertFalse(report["ready"])
        self.assertEqual(1, report["violations"]["records_without_evidence"])
        self.assertNotIn("role", output.getvalue())

    def test_profile_acceptance_rejects_incomplete_shape_sample_before_opening_database(
        self,
    ) -> None:
        output = StringIO()

        with redirect_stdout(output):
            self.assertEqual(
                1,
                dev_tools.person_profile_acceptance(
                    [f"recent:{index}" for index in range(1, 11)]
                ),
            )

        self.assertIn("missing_shapes", output.getvalue())

    def test_task_consistency_reports_exact_queue_and_plan_conflicts(self) -> None:
        text = """# Tasks

## Now

- [x] AM-120 Completed work in the wrong section.

## Now

- [ ] AM-121 Duplicate section.

## Completed

- [ ] AM-122 Open work in the wrong section.
"""

        with patch.object(dev_tools, "ROOT", Path(self.directory.name)):
            active = Path(self.directory.name) / "docs" / "exec-plans" / "active"
            active.mkdir(parents=True)
            (active / "AM-120-example.md").touch()
            violations = dev_tools.task_consistency_violations(text)

        self.assertEqual(
            [
                "TASKS.md:5: completed task remains in 'Now' section",
                "TASKS.md:7: duplicate 'Now' section (first at line 3)",
                "TASKS.md:13: open task is listed in Completed",
                "TASKS.md:5: completed AM-120 still has an active ExecPlan",
            ],
            violations,
        )

    def test_task_consistency_checks_explicit_notion_completion_metadata(self) -> None:
        text = """## Completed

- [x] AM-120 Completed work.
"""

        with patch.object(dev_tools, "ROOT", Path(self.directory.name)):
            violations = dev_tools.task_consistency_violations(
                text,
                [
                    {
                        "properties": {
                            "Task": "Graph readiness",
                            "Repo ID": "AM-120",
                            "Status": "Done",
                            "Repo Section": None,
                            "Evidence Summary": "",
                            "Kind": None,
                            "Gate Type": "",
                            "Gate State": None,
                        }
                    },
                    {
                        "properties": {
                            "Task": "Incorrect queue",
                            "Status": "Next",
                            "Repo Section": "Completed",
                        }
                    },
                ],
            )

        self.assertEqual(
            [
                "Notion AM-120: Status=Done requires Repo Section=Completed",
                "Notion AM-120: completed task is missing Evidence Summary",
                "Notion AM-120: completed task is missing Kind",
                "Notion AM-120: completed task is missing Gate Type",
                "Notion AM-120: completed task is missing Gate State",
                "Notion Incorrect queue: Status=Next conflicts with Repo Section=Completed",
            ],
            violations,
        )
