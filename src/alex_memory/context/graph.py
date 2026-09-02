"""Deterministic projection of validated claims into the temporal graph."""

from __future__ import annotations

import json
import sqlite3
from typing import cast

from ..utils import utc_now
from .ranking import highest, rank_item


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
            self._supersede_other_task_context(
                task_id,
                None if manual_task_project else project_node,
                observed_at,
            )
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
                for (
                    entity_type,
                    _entity_id,
                    relationship_types,
                ) in self._accepted_task_entity_project_context(
                    task_id=task_id,
                    item_id=item_id,
                    claim_id=claim_id,
                    person_id=person_id,
                    company_id=company_id,
                    project_id=project_id,
                ):
                    entity_node = entity_nodes[entity_type]
                    for relationship_type in relationship_types:
                        self._edge(
                            from_node_id=entity_node,
                            to_node_id=project_node,
                            relationship_type=relationship_type,
                            valid_from=observed_at,
                            confidence=float(confidence),
                            authority_status="accepted",
                            claim_id=claim_id,
                            properties={
                                "source_item_id": item_id,
                                "task_id": task_id,
                                "reducer": "accepted_task_context",
                            },
                        )

        self.conn.execute(
            """UPDATE semantic_claims
               SET projection_status=?,projected_at=?
               WHERE claim_id=? AND projection_status IN ('pending','projected')""",
            ("review" if manual_task_project else "projected", utc_now(), claim_id),
        )

    def project_manual_relationship(
        self,
        *,
        from_type: str,
        from_id: int,
        to_type: str,
        to_id: int,
        relationship_type: str,
        valid_from: str,
        confidence: float = 1.0,
    ) -> None:
        """Record an explicitly accepted manual relationship without AI lineage."""
        self._edge(
            from_node_id=self._canonical_node(from_type, from_id),
            to_node_id=self._canonical_node(to_type, to_id),
            relationship_type=relationship_type,
            valid_from=valid_from,
            confidence=confidence,
            authority_status="manual",
            claim_id=None,
            properties={"manual": True},
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

    def _supersede_other_task_context(
        self, task_id: int, project_node_id: int | None, valid_to: str
    ) -> None:
        """Close prior deterministic task context when its project is replaced.

        These edges inherit their validity from one canonical task/project
        decision. They must not remain current after that decision is replaced
        or a manual task-project edge takes precedence.
        """
        predicates = [
            "authority_status='accepted'",
            "valid_to IS NULL",
            "json_extract(properties_json, '$.reducer')='accepted_task_context'",
            "json_extract(properties_json, '$.task_id')=?",
        ]
        parameters: list[object] = [task_id]
        if project_node_id is not None:
            predicates.append("to_node_id<>?")
            parameters.append(project_node_id)
        self.conn.execute(
            f"""UPDATE graph_edges SET valid_to=?,authority_status='superseded',
                   updated_at=? WHERE {" AND ".join(predicates)}""",
            (valid_to, utc_now(), *parameters),
        )

    def _accepted_task_entity_project_context(
        self,
        *,
        task_id: int,
        item_id: int,
        claim_id: int,
        person_id: int | None,
        company_id: int | None,
        project_id: int,
    ) -> tuple[tuple[str, int, tuple[str, ...]], ...]:
        """Return only canonical task context backed by this exact claim.

        This reducer makes no relationship decision from a confidence-only
        compatibility observation. Its inputs are the task reconciler's current
        canonical endpoints and the immutable claim already required by the
        accepted task-to-project edge.
        """
        task = self.conn.execute(
            """SELECT related_person_id,related_company_id,related_project_id
               FROM tasks WHERE task_id=? AND source_item_id=? AND source_claim_id=?""",
            (task_id, item_id, claim_id),
        ).fetchone()
        if task is None or task[2] != project_id:
            return ()
        contexts: list[tuple[str, int, tuple[str, ...]]] = []
        if person_id is not None and task[0] == person_id:
            contexts.append(("person", person_id, ("involved_in",)))
        if company_id is not None and task[1] == company_id:
            contexts.append(("company", company_id, ("involved_in", "associated_with")))
        return tuple(contexts)

    def _edge(
        self,
        *,
        from_node_id: int,
        to_node_id: int,
        relationship_type: str,
        valid_from: str,
        confidence: float,
        authority_status: str,
        claim_id: int | None,
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
        if claim_id is not None:
            self.conn.execute(
                """INSERT OR IGNORE INTO graph_edge_claims(edge_id,claim_id,created_at)
                   VALUES (?,?,?)""",
                (edge_id, claim_id, now),
            )


def current_authoritative_edges(
    conn: sqlite3.Connection,
    seeds: list[tuple[str, int]],
    as_of: str,
    *,
    limit: int = 80,
) -> list[dict[str, object]]:
    """Read bounded current graph edges safe for a future runtime consumer.

    Observed claim material is intentionally excluded. Accepted automatic edges
    are limited to the projector's task-to-project allowlist and must retain
    claim evidence; manual edges remain usable without a fabricated AI source.

    An exact-claim-backed task context is also represented at read time when a
    historical graph materialization is absent. This is the same allowlisted
    reducer as ``accepted_task_context``--not a compatibility-row promotion--
    and lets a bounded reader see the canonical task decision without a replay.
    """
    if not seeds or limit <= 0:
        return []
    bounded_limit = min(limit, 160)
    endpoint_predicates = " OR ".join(
        "(from_node.canonical_entity_type=? AND from_node.canonical_entity_id=?) "
        "OR (to_node.canonical_entity_type=? AND to_node.canonical_entity_id=?)"
        for _ in seeds
    )
    parameters: list[object] = []
    for entity_type, entity_id in seeds:
        parameters.extend((entity_type, entity_id, entity_type, entity_id))
    rows = conn.execute(
        f"""SELECT edge.edge_id,
                   from_node.canonical_entity_type,from_node.canonical_entity_id,
                   to_node.canonical_entity_type,to_node.canonical_entity_id,
                   edge.relationship_type,edge.valid_from,edge.valid_to,
                   edge.confidence,edge.authority_status,
                   GROUP_CONCAT(edge_claim.claim_id)
            FROM graph_edges AS edge
            JOIN graph_nodes AS from_node ON from_node.node_id=edge.from_node_id
            JOIN graph_nodes AS to_node ON to_node.node_id=edge.to_node_id
            LEFT JOIN (
                SELECT provenance.edge_id,provenance.claim_id
                FROM graph_edge_claims AS provenance
                JOIN semantic_claims AS claim ON claim.claim_id=provenance.claim_id
                JOIN semantic_claim_evidence AS evidence ON evidence.claim_id=claim.claim_id
                GROUP BY provenance.edge_id,provenance.claim_id
            ) AS edge_claim ON edge_claim.edge_id=edge.edge_id
            WHERE ({endpoint_predicates})
              AND from_node.canonical_entity_type IS NOT NULL
              AND from_node.canonical_entity_id IS NOT NULL
              AND to_node.canonical_entity_type IS NOT NULL
              AND to_node.canonical_entity_id IS NOT NULL
              AND from_node.authority_status IN ('accepted','manual')
              AND to_node.authority_status IN ('accepted','manual')
              AND edge.authority_status IN ('accepted','manual')
              AND edge.valid_from<=?
              AND (edge.valid_to IS NULL OR edge.valid_to>?)
              AND (
                  edge.authority_status='manual'
                  OR (
                      edge_claim.claim_id IS NOT NULL AND (
                          (
                              edge.relationship_type='belongs_to'
                              AND from_node.canonical_entity_type='task'
                              AND to_node.canonical_entity_type='project'
                          )
                          OR (
                              json_extract(edge.properties_json, '$.reducer')
                                ='accepted_task_context'
                              AND to_node.canonical_entity_type='project'
                              AND (
                                  (
                                      from_node.canonical_entity_type='person'
                                      AND edge.relationship_type='involved_in'
                                  )
                                  OR (
                                      from_node.canonical_entity_type='company'
                                      AND edge.relationship_type IN (
                                          'involved_in','associated_with'
                                      )
                                  )
                              )
                          )
                      )
                  )
              )
            GROUP BY edge.edge_id
            ORDER BY edge.valid_from DESC,edge.edge_id DESC
            LIMIT ?""",
        [*parameters, as_of, as_of, bounded_limit],
    ).fetchall()
    stored_edges = [
        {
            "edge_id": int(row[0]),
            "from_type": str(row[1]),
            "from_id": int(row[2]),
            "to_type": str(row[3]),
            "to_id": int(row[4]),
            "relationship_type": str(row[5]),
            "valid_from": str(row[6]),
            "valid_to": row[7],
            "confidence": float(row[8]),
            "authority_status": str(row[9]),
            "claim_ids": tuple(
                sorted(int(value) for value in str(row[10]).split(","))
                if row[10] is not None
                else ()
            ),
        }
        for row in rows
    ]
    derived_edges = _current_task_context_edges(conn, seeds, as_of, bounded_limit)
    edges = {
        (
            str(edge["from_type"]),
            cast(int, edge["from_id"]),
            str(edge["to_type"]),
            cast(int, edge["to_id"]),
            str(edge["relationship_type"]),
        ): edge
        for edge in derived_edges
    }
    # Stored graph rows remain the representation when both paths describe the
    # same accepted reducer result.
    edges.update(
        {
            (
                str(edge["from_type"]),
                cast(int, edge["from_id"]),
                str(edge["to_type"]),
                cast(int, edge["to_id"]),
                str(edge["relationship_type"]),
            ): edge
            for edge in stored_edges
        }
    )
    return sorted(
        edges.values(),
        key=lambda edge: (
            str(edge["valid_from"]),
            1 if edge.get("materialization") != "derived_task_context" else 0,
            int(cast(int, edge["edge_id"])) if edge["edge_id"] is not None else 0,
        ),
        reverse=True,
    )[:bounded_limit]


def _current_task_context_edges(
    conn: sqlite3.Connection,
    seeds: list[tuple[str, int]],
    as_of: str,
    limit: int,
) -> list[dict[str, object]]:
    """Return the exact-claim task-context reducer without materializing it.

    This narrow fallback exists for accepted tasks projected before their
    context graph edges were persisted. It reads canonical task endpoints and
    their immutable claim only; it never reads ``relationships`` and never
    turns an unreviewed compatibility inference into accepted graph authority.
    """
    task_columns = {
        "person": "related_person_id",
        "company": "related_company_id",
        "project": "related_project_id",
        "task": "task_id",
    }
    predicates: list[str] = []
    parameters: list[object] = []
    for entity_type, entity_id in seeds:
        column = task_columns.get(entity_type)
        if column is None:
            continue
        predicates.append(f"task.{column}=?")
        parameters.append(entity_id)
    if not predicates:
        return []
    endpoint_predicates = " OR ".join(predicates)
    rows = conn.execute(
        f"""SELECT task.task_id,task.related_person_id,task.related_company_id,
                   task.related_project_id,item.person_id,item.company_id,item.project_id,
                   task.source_claim_id,COALESCE(item.source_date,task.created_at),
                   item.confidence
              FROM tasks AS task
              JOIN ai_items AS item ON item.item_id=task.source_item_id
                                  AND item.source_claim_id=task.source_claim_id
             WHERE ({endpoint_predicates})
               AND task.source_claim_id IS NOT NULL
               AND task.related_project_id IS NOT NULL
               AND item.project_id=task.related_project_id
               AND COALESCE(item.source_date,task.created_at)<=?
               AND EXISTS (
                   SELECT 1 FROM semantic_claim_evidence AS evidence
                    WHERE evidence.claim_id=task.source_claim_id
               )
               AND NOT EXISTS (
                   SELECT 1 FROM graph_edges AS manual_edge
                   JOIN graph_nodes AS manual_task
                     ON manual_task.node_id=manual_edge.from_node_id
                    WHERE manual_task.canonical_entity_type='task'
                      AND manual_task.canonical_entity_id=task.task_id
                      AND manual_edge.relationship_type='belongs_to'
                      AND manual_edge.authority_status='manual'
                      AND manual_edge.valid_to IS NULL
               )
             ORDER BY COALESCE(item.source_date,task.created_at) DESC,task.task_id DESC
             LIMIT ?""",
        [*parameters, as_of, limit],
    ).fetchall()
    edges: list[dict[str, object]] = []
    for (
        task_id,
        task_person_id,
        task_company_id,
        project_id,
        item_person_id,
        item_company_id,
        _item_project_id,
        claim_id,
        valid_from,
        confidence,
    ) in rows:
        contexts: tuple[tuple[str, int, tuple[str, ...]], ...] = ()
        if task_person_id is not None and task_person_id == item_person_id:
            contexts += (("person", int(task_person_id), ("involved_in",)),)
        if task_company_id is not None and task_company_id == item_company_id:
            contexts += (
                ("company", int(task_company_id), ("involved_in", "associated_with")),
            )
        for from_type, from_id, relationship_types in contexts:
            for relationship_type in relationship_types:
                edges.append(
                    {
                        "edge_id": None,
                        "from_type": from_type,
                        "from_id": from_id,
                        "to_type": "project",
                        "to_id": int(project_id),
                        "relationship_type": relationship_type,
                        "valid_from": str(valid_from),
                        "valid_to": None,
                        "confidence": float(confidence),
                        "authority_status": "accepted",
                        "materialization": "derived_task_context",
                        "claim_ids": (int(cast(int, claim_id)),),
                        "task_id": int(task_id),
                    }
                )
    return edges


def context_builder_relationship_parity_gaps(
    conn: sqlite3.Connection,
    seeds: list[tuple[str, int]],
    as_of: str,
    *,
    max_depth: int = 2,
    limit: int = 80,
) -> dict[str, object]:
    """Report bounded legacy ContextBuilder relationship inputs missing from graph.

    This is a read-only cutover diagnostic. It intentionally reports grouped
    gaps rather than returning relationship content or changing either layer.
    """
    bounded_limit = min(max(limit, 0), 80)
    requested_depth = max(max_depth, 0)
    bounded_depth = min(requested_depth, 4)
    unique_seeds = list(dict.fromkeys(seeds))
    frontier = unique_seeds[:20]
    seen_entities = set(frontier)
    collected: list[dict[str, object]] = []
    collected_ids: set[int] = set()
    truncated = len(unique_seeds) > len(frontier) or requested_depth > bounded_depth
    for depth in range(bounded_depth + 1):
        if not frontier:
            break
        predicates = " OR ".join(
            "(from_type=? AND from_id=?) OR (to_type=? AND to_id=?)" for _ in frontier
        )
        parameters: list[object] = []
        for entity_type, entity_id in frontier:
            parameters.extend((entity_type, entity_id, entity_type, entity_id))
        rows = conn.execute(
            f"""SELECT relationship_id,from_type,from_id,to_type,to_id,relationship_type,
                       valid_from,is_current,confidence,updated_at
                FROM relationships WHERE ({predicates}) AND valid_from<=?
                  AND (valid_to IS NULL OR valid_to>?)
                LIMIT 160""",
            [*parameters, as_of, as_of],
        ).fetchall()
        next_frontier: list[tuple[str, int]] = []
        for row in rows:
            relationship_id = int(row[0])
            from_type, from_id, to_type, to_id, relationship_type = row[1:6]
            relationship = rank_item(
                {
                    "relationship_id": relationship_id,
                    "from_type": str(from_type),
                    "from_id": int(from_id),
                    "to_type": str(to_type),
                    "to_id": int(to_id),
                    "relationship_type": str(relationship_type),
                    "valid_from": str(row[6]),
                    "is_current": bool(row[7]),
                    "confidence": float(row[8]),
                    "updated_at": str(row[9]),
                },
                "relationship",
                graph_distance=depth,
                now=as_of,
            )
            if relationship_id not in collected_ids:
                collected_ids.add(relationship_id)
                collected.append(relationship)
            if depth >= bounded_depth:
                continue
            for entity in (
                (str(from_type), int(from_id)),
                (str(to_type), int(to_id)),
            ):
                if entity[0] not in {"person", "company", "project"}:
                    continue
                if entity in seen_entities:
                    continue
                if len(seen_entities) >= 40:
                    truncated = True
                    continue
                seen_entities.add(entity)
                next_frontier.append(entity)
        frontier = next_frontier

    legacy_edges = {
        (
            cast(str, edge["from_type"]),
            cast(int, edge["from_id"]),
            cast(str, edge["to_type"]),
            cast(int, edge["to_id"]),
            cast(str, edge["relationship_type"]),
        )
        for edge in highest(collected, bounded_limit)
    }
    graph_seeds = sorted(
        {
            endpoint
            for from_type, from_id, to_type, to_id, _relationship_type in legacy_edges
            for endpoint in ((from_type, from_id), (to_type, to_id))
        }
    )
    graph_edges = current_authoritative_edges(conn, graph_seeds, as_of, limit=160)
    accepted = {
        (
            str(edge["from_type"]),
            cast(int, edge["from_id"]),
            str(edge["to_type"]),
            cast(int, edge["to_id"]),
            str(edge["relationship_type"]),
        )
        for edge in graph_edges
    }
    missing_edges = legacy_edges - accepted
    groups: dict[tuple[str, str, str], int] = {}
    authority_diagnostics: dict[tuple[str, str, str, str], int] = {}
    for from_type, from_id, to_type, to_id, relationship_type in missing_edges:
        key = (from_type, relationship_type, to_type)
        groups[key] = groups.get(key, 0) + 1
        reason_key = (
            *key,
            _task_context_gap_reason(
                conn,
                from_type=from_type,
                from_id=from_id,
                to_type=to_type,
                to_id=to_id,
                relationship_type=relationship_type,
                as_of=as_of,
            ),
        )
        authority_diagnostics[reason_key] = authority_diagnostics.get(reason_key, 0) + 1
    return {
        "reader": "ContextBuilder",
        "as_of": as_of,
        "truncated": truncated,
        "gaps": [
            {
                "from_type": from_type,
                "relationship_type": relationship_type,
                "to_type": to_type,
                "legacy_authority": "compatibility",
                "accepted_graph_authority": "missing",
                "count": count,
            }
            for (from_type, relationship_type, to_type), count in sorted(groups.items())
        ],
        "gap_authority_diagnostics": [
            {
                "from_type": from_type,
                "relationship_type": relationship_type,
                "to_type": to_type,
                "reason": reason,
                "count": count,
            }
            for (from_type, relationship_type, to_type, reason), count in sorted(
                authority_diagnostics.items()
            )
        ],
    }


def _task_context_gap_reason(
    conn: sqlite3.Connection,
    *,
    from_type: str,
    from_id: int,
    to_type: str,
    to_id: int,
    relationship_type: str,
    as_of: str,
) -> str:
    """Classify a missing edge without returning its private provenance.

    The result is deliberately aggregate-safe: it states only which authority
    boundary prevented the existing task reducer from representing a legacy
    relationship. It does not inspect message content or expose task/item IDs.
    """
    allowed_relationships = {
        ("person", "involved_in"),
        ("company", "involved_in"),
        ("company", "associated_with"),
    }
    if (
        to_type != "project"
        or (from_type, relationship_type) not in allowed_relationships
    ):
        return "not_allowlisted_task_context"
    task_column = "related_person_id" if from_type == "person" else "related_company_id"
    rows = conn.execute(
        f"""SELECT task.task_id,task.source_item_id,task.source_claim_id,
                   item.item_id,item.source_claim_id,item.person_id,item.company_id,
                   item.project_id,COALESCE(item.source_date,task.created_at),
                   EXISTS (
                       SELECT 1 FROM semantic_claim_evidence AS evidence
                        WHERE evidence.claim_id=task.source_claim_id
                   ),
                   EXISTS (
                       SELECT 1 FROM graph_edges AS manual_edge
                       JOIN graph_nodes AS manual_task
                         ON manual_task.node_id=manual_edge.from_node_id
                        WHERE manual_task.canonical_entity_type='task'
                          AND manual_task.canonical_entity_id=task.task_id
                          AND manual_edge.relationship_type='belongs_to'
                          AND manual_edge.authority_status='manual'
                          AND manual_edge.valid_to IS NULL
                   )
              FROM tasks AS task
              LEFT JOIN ai_items AS item ON item.item_id=task.source_item_id
             WHERE task.{task_column}=? AND task.related_project_id=?""",
        (from_id, to_id),
    ).fetchall()
    if not rows:
        return "no_matching_current_task"
    for row in rows:
        (
            _task_id,
            source_item_id,
            source_claim_id,
            item_id,
            item_claim_id,
            item_person_id,
            item_company_id,
            item_project_id,
            valid_from,
            has_claim_evidence,
            has_manual_override,
        ) = row
        if has_manual_override:
            return "manual_task_project_override"
        if source_item_id is None or source_claim_id is None:
            continue
        if item_id is None or item_claim_id != source_claim_id:
            continue
        if item_project_id != to_id:
            continue
        if from_type == "person" and item_person_id != from_id:
            continue
        if from_type == "company" and item_company_id != from_id:
            continue
        if str(valid_from) > as_of:
            continue
        if not has_claim_evidence:
            continue
        return "eligible_task_context_not_returned"
    return "missing_exact_task_claim_lineage"
