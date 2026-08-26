"""Deterministic projection of validated claims into the temporal graph."""

from __future__ import annotations

import json
import sqlite3

from ..utils import utc_now


_CLAIM_NODE_TYPES = {
    "action_candidate": "commitment",
    "commitment": "commitment",
    "event": "event",
    "temporal_fact": "event",
    "topic": "topic",
}


class SemanticGraphProjector:
    """The single writer for claim-derived graph rows.

    This projector never changes raw evidence or upgrades an AI claim's
    authority. It records observed claim-to-entity links and the deliberately
    small allowlist of accepted operational edges that canonical reducers have
    already resolved without ambiguity.
    """

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def project_item(
        self,
        *,
        claim_id: int | None,
        item_id: int,
        source_at: str | None,
        person_id: int | None,
        company_id: int | None,
        project_id: int | None,
        task_id: int | None,
    ) -> None:
        """Project one validated compatibility observation idempotently."""
        if claim_id is None:
            return
        claim = self.conn.execute(
            """SELECT claim_type,confidence,created_at FROM semantic_claims
               WHERE claim_id=?""",
            (claim_id,),
        ).fetchone()
        if claim is None:
            raise RuntimeError(f"AI item {item_id} references a missing semantic claim")
        claim_type, confidence, created_at = claim
        observed_at = source_at or str(created_at)
        resolved = {
            "person": person_id,
            "company": company_id,
            "project": project_id,
            "task": task_id,
        }
        self._resolve_claim_references(claim_id, resolved)

        entity_nodes: dict[str, int] = {}
        for entity_type, entity_id in resolved.items():
            if entity_id is not None:
                entity_nodes[entity_type] = self._canonical_node(entity_type, entity_id)

        claim_node_type = _CLAIM_NODE_TYPES.get(str(claim_type))
        if claim_node_type is not None:
            claim_node = self._claim_node(claim_id, claim_node_type)
            for entity_type, node_id in entity_nodes.items():
                self._edge(
                    from_node_id=claim_node,
                    to_node_id=node_id,
                    relationship_type="claims_about",
                    valid_from=observed_at,
                    confidence=float(confidence),
                    authority_status="observed",
                    claim_id=claim_id,
                    properties={"entity_type": entity_type},
                )

        # This is the sole automatic relationship allowlist. The reconciler
        # already applied confidence, identity, and ambiguity policy; every
        # other claimed relationship remains observed or is handled by Review.
        manual_task_project = False
        if task_id is not None and project_id is not None:
            task_node = entity_nodes["task"]
            project_node = entity_nodes["project"]
            manual_task_project = self._has_manual_task_project(task_node)
            if not manual_task_project:
                self._supersede_other_task_projects(
                    task_node, project_node, observed_at
                )
                self._edge(
                    from_node_id=task_node,
                    to_node_id=project_node,
                    relationship_type="belongs_to",
                    valid_from=observed_at,
                    confidence=float(confidence),
                    authority_status="accepted",
                    claim_id=claim_id,
                    properties={"source_item_id": item_id},
                )

        self.conn.execute(
            """UPDATE semantic_claims
               SET projection_status=?,projected_at=?
               WHERE claim_id=? AND projection_status IN ('pending','projected')""",
            ("review" if manual_task_project else "projected", utc_now(), claim_id),
        )

    def _resolve_claim_references(
        self, claim_id: int, resolved: dict[str, int | None]
    ) -> None:
        refs = self.conn.execute(
            """SELECT ordinal,role,entity_type FROM semantic_claim_entity_refs
               WHERE claim_id=?""",
            (claim_id,),
        ).fetchall()
        for ordinal, role, entity_type in refs:
            entity_id = resolved.get(str(entity_type))
            if entity_id is None and role == "subject":
                entity_id = resolved.get(str(entity_type))
            status = "resolved" if entity_id is not None else "review"
            self.conn.execute(
                """UPDATE semantic_claim_entity_refs
                   SET canonical_entity_id=?,resolution_status=?
                   WHERE claim_id=? AND ordinal=?""",
                (entity_id, status, claim_id, ordinal),
            )

    def _canonical_node(self, entity_type: str, entity_id: int) -> int:
        now = utc_now()
        key = f"canonical:{entity_type}:{entity_id}"
        self.conn.execute(
            """INSERT INTO graph_nodes(
                   node_key,node_type,canonical_entity_type,canonical_entity_id,
                   properties_json,authority_status,created_at,updated_at
               ) VALUES (?,?,?,?,?,'accepted',?,?)
               ON CONFLICT(node_key) DO UPDATE SET updated_at=excluded.updated_at""",
            (
                key,
                entity_type,
                entity_type,
                entity_id,
                json.dumps({"canonical_entity_id": entity_id}, sort_keys=True),
                now,
                now,
            ),
        )
        row = self.conn.execute(
            "SELECT node_id FROM graph_nodes WHERE node_key=?", (key,)
        ).fetchone()
        if row is None:
            raise RuntimeError("SQLite did not return the canonical graph node")
        return int(row[0])

    def _claim_node(self, claim_id: int, node_type: str) -> int:
        now = utc_now()
        key = f"claim:{claim_id}"
        self.conn.execute(
            """INSERT INTO graph_nodes(
                   node_key,node_type,canonical_entity_type,canonical_entity_id,
                   properties_json,authority_status,created_at,updated_at
               ) VALUES (?,?,?,?,?,'observed',?,?)
               ON CONFLICT(node_key) DO UPDATE SET updated_at=excluded.updated_at""",
            (
                key,
                node_type,
                None,
                None,
                json.dumps({"claim_id": claim_id}, sort_keys=True),
                now,
                now,
            ),
        )
        row = self.conn.execute(
            "SELECT node_id FROM graph_nodes WHERE node_key=?", (key,)
        ).fetchone()
        if row is None:
            raise RuntimeError("SQLite did not return the semantic graph node")
        return int(row[0])

    def _supersede_other_task_projects(
        self, task_node_id: int, project_node_id: int, valid_to: str
    ) -> None:
        self.conn.execute(
            """UPDATE graph_edges
               SET valid_to=?,authority_status='superseded',updated_at=?
               WHERE from_node_id=? AND relationship_type='belongs_to'
                 AND authority_status='accepted' AND valid_to IS NULL
                 AND to_node_id<>?""",
            (valid_to, utc_now(), task_node_id, project_node_id),
        )

    def _has_manual_task_project(self, task_node_id: int) -> bool:
        return bool(
            self.conn.execute(
                """SELECT 1 FROM graph_edges
                   WHERE from_node_id=? AND relationship_type='belongs_to'
                     AND authority_status='manual' AND valid_to IS NULL
                   LIMIT 1""",
                (task_node_id,),
            ).fetchone()
        )

    def _edge(
        self,
        *,
        from_node_id: int,
        to_node_id: int,
        relationship_type: str,
        valid_from: str,
        confidence: float,
        authority_status: str,
        claim_id: int,
        properties: dict[str, object],
    ) -> None:
        row = self.conn.execute(
            """SELECT edge_id FROM graph_edges
               WHERE from_node_id=? AND to_node_id=? AND relationship_type=?
                 AND authority_status=? AND valid_to IS NULL
               ORDER BY edge_id LIMIT 1""",
            (from_node_id, to_node_id, relationship_type, authority_status),
        ).fetchone()
        now = utc_now()
        if row is None:
            cursor = self.conn.execute(
                """INSERT INTO graph_edges(
                       from_node_id,to_node_id,relationship_type,valid_from,valid_to,
                       first_seen_at,last_seen_at,confidence,authority_status,
                       properties_json,created_at,updated_at
                   ) VALUES (?,?,?,?,NULL,?,?,?,?,?,?,?)""",
                (
                    from_node_id,
                    to_node_id,
                    relationship_type,
                    valid_from,
                    valid_from,
                    valid_from,
                    confidence,
                    authority_status,
                    json.dumps(properties, sort_keys=True),
                    now,
                    now,
                ),
            )
            if cursor.lastrowid is None:
                raise RuntimeError("SQLite did not return an ID for the graph edge")
            edge_id = int(cursor.lastrowid)
        else:
            edge_id = int(row[0])
            self.conn.execute(
                """UPDATE graph_edges
                   SET last_seen_at=CASE WHEN last_seen_at < ? THEN ? ELSE last_seen_at END,
                       updated_at=?
                   WHERE edge_id=?""",
                (valid_from, valid_from, now, edge_id),
            )
        self.conn.execute(
            """INSERT OR IGNORE INTO graph_edge_claims(edge_id,claim_id,created_at)
               VALUES (?,?,?)""",
            (edge_id, claim_id, now),
        )
