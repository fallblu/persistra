"""
src/persistra/core/validation.py

Graph validation for Persistra projects.

Checks:
1. Disconnected required inputs → ERROR
2. Type mismatches on connected sockets → ERROR
3. Illegal cycles (outside IteratorNode) → ERROR
4. Orphan nodes (zero connections) → WARNING
5. Missing parameters (None or empty string) → WARNING
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Set

from persistra.core.project import Project, Node


@dataclass
class ValidationMessage:
    level: str          # "error", "warning", "info"
    node_id: str
    message: str


class GraphValidator:
    """Validates a Project graph before execution."""

    def validate(self, project: Project) -> list[ValidationMessage]:
        messages: list[ValidationMessage] = []
        messages.extend(self._check_required_inputs(project))
        messages.extend(self._check_type_mismatches(project))
        messages.extend(self._check_illegal_cycles(project))
        messages.extend(self._check_orphan_nodes(project))
        messages.extend(self._check_missing_parameters(project))
        return messages

    # ------------------------------------------------------------------
    # 1. Disconnected required inputs
    # ------------------------------------------------------------------
    def _check_required_inputs(self, project: Project) -> list[ValidationMessage]:
        msgs: list[ValidationMessage] = []
        for node in project.nodes:
            for sock in node.input_sockets:
                if sock.required and not sock.connections:
                    msgs.append(ValidationMessage(
                        level="error",
                        node_id=node.id,
                        message=(
                            f"Required input '{sock.name}' on "
                            f"'{node.operation.name}' is not connected."
                        ),
                    ))
        return msgs

    # ------------------------------------------------------------------
    # 2. Type mismatches
    # ------------------------------------------------------------------
    def _check_type_mismatches(self, project: Project) -> list[ValidationMessage]:
        msgs: list[ValidationMessage] = []
        for node in project.nodes:
            for sock in node.input_sockets:
                if sock.connections:
                    source_sock = sock.connections[0]
                    if not sock.socket_type.accepts(source_sock.socket_type):
                        msgs.append(ValidationMessage(
                            level="error",
                            node_id=node.id,
                            message=(
                                f"Type mismatch: '{source_sock.name}' "
                                f"({source_sock.socket_type}) → '{sock.name}' "
                                f"({sock.socket_type}) on '{node.operation.name}'."
                            ),
                        ))
        return msgs

    # ------------------------------------------------------------------
    # 3. Illegal cycles (DFS back-edge detection)
    # ------------------------------------------------------------------
    def _check_illegal_cycles(self, project: Project) -> list[ValidationMessage]:
        from persistra.core.composite import IteratorNode

        msgs: list[ValidationMessage] = []

        # Collect node IDs that belong to an IteratorNode body
        iterator_body_ids: Set[str] = set()
        for node in project.nodes:
            if isinstance(node, IteratorNode):
                for body_node in node.body.sub_project.nodes:
                    iterator_body_ids.add(body_node.id)

        # Build adjacency (only among top-level project nodes)
        node_ids = {n.id for n in project.nodes}
        adjacency: dict[str, list[str]] = {n.id: [] for n in project.nodes}
        for node in project.nodes:
            for out_sock in node.output_sockets:
                for conn in out_sock.connections:
                    child_id = conn.node.id
                    if child_id in node_ids:
                        adjacency[node.id].append(child_id)

        # DFS coloring: 0 = white, 1 = gray, 2 = black
        color: dict[str, int] = {nid: 0 for nid in node_ids}
        cycle_nodes: Set[str] = set()

        def dfs(nid: str) -> bool:
            color[nid] = 1
            for child in adjacency[nid]:
                if child in iterator_body_ids and nid in iterator_body_ids:
                    continue
                if color[child] == 1:
                    cycle_nodes.add(nid)
                    cycle_nodes.add(child)
                    return True
                if color[child] == 0 and dfs(child):
                    cycle_nodes.add(nid)
                    return True
            color[nid] = 2
            return False

        for nid in node_ids:
            if color[nid] == 0:
                dfs(nid)

        for nid in cycle_nodes:
            node = next((n for n in project.nodes if n.id == nid), None)
            if node:
                msgs.append(ValidationMessage(
                    level="error",
                    node_id=nid,
                    message=f"Node '{node.operation.name}' is part of an illegal cycle.",
                ))
        return msgs

    # ------------------------------------------------------------------
    # 4. Orphan nodes (zero connections)
    # ------------------------------------------------------------------
    def _check_orphan_nodes(self, project: Project) -> list[ValidationMessage]:
        msgs: list[ValidationMessage] = []
        for node in project.nodes:
            has_connection = False
            for sock in node.input_sockets:
                if sock.connections:
                    has_connection = True
                    break
            if not has_connection:
                for sock in node.output_sockets:
                    if sock.connections:
                        has_connection = True
                        break
            if not has_connection:
                msgs.append(ValidationMessage(
                    level="warning",
                    node_id=node.id,
                    message=(
                        f"Node '{node.operation.name}' has no connections (orphan)."
                    ),
                ))
        return msgs

    # ------------------------------------------------------------------
    # 5. Missing parameters
    # ------------------------------------------------------------------
    def _check_missing_parameters(self, project: Project) -> list[ValidationMessage]:
        msgs: list[ValidationMessage] = []
        for node in project.nodes:
            for param in node.parameters:
                if param.value is None or (isinstance(param.value, str) and param.value == ""):
                    msgs.append(ValidationMessage(
                        level="warning",
                        node_id=node.id,
                        message=(
                            f"Parameter '{param.name}' on "
                            f"'{node.operation.name}' is empty or None."
                        ),
                    ))
        return msgs
