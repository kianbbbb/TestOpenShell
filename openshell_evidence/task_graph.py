"""
Task knowledge graph – per-task evidence sub-graph.

Each task that an agent undertakes creates its own :class:`TaskGraph` which
captures all evidence (commands run, outputs produced, decisions made) as a
sub-graph anchored to a root Task node.  Task graphs can be merged into a
global :class:`~openshell_evidence.knowledge_graph.KnowledgeGraph`, and they
persist state so that agents can resume work after interruption.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .knowledge_graph import Edge, KnowledgeGraph, Node
from .shell import CommandResult
from .telemetry import TelemetryCollector, TelemetrySpan

# ------------------------------------------------------------------ Node types

NODE_TASK = "task"
NODE_COMMAND = "command"
NODE_OUTPUT = "output"
NODE_AGENT = "agent"
NODE_ARTIFACT = "artifact"
NODE_EVIDENCE = "evidence"

# ---------------------------------------------------------------- Relation types

REL_HAS_COMMAND = "HAS_COMMAND"
REL_PRODUCED = "PRODUCED"
REL_FOLLOWS = "FOLLOWS"
REL_DELEGATED_TO = "DELEGATED_TO"
REL_HAS_EVIDENCE = "HAS_EVIDENCE"
REL_DEPENDS_ON = "DEPENDS_ON"
REL_SPAWNED = "SPAWNED"


class TaskStatus:
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"


class TaskGraph:
    """
    A knowledge sub-graph capturing all evidence for a single task.

    The graph is rooted at a Task node and grows as commands are executed,
    outputs are captured, and artefacts are produced.  It can be serialised
    and deserialised independently, and merged into a global knowledge graph
    to maintain full context across sessions.

    Parameters
    ----------
    task_name:
        Human-readable name for the task.
    task_id:
        Unique identifier.  A UUID is generated when not provided.
    description:
        Optional longer description of the task.
    agent_name:
        Name of the agent performing the task.
    parent_task_id:
        If this task was spawned by another task, its parent ID.
    """

    def __init__(
        self,
        task_name: str,
        task_id: Optional[str] = None,
        description: str = "",
        agent_name: Optional[str] = None,
        parent_task_id: Optional[str] = None,
    ) -> None:
        self.task_id = task_id or str(uuid.uuid4())
        self.task_name = task_name
        self.description = description
        self.agent_name = agent_name
        self.parent_task_id = parent_task_id
        self.status = TaskStatus.PENDING
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.updated_at = self.created_at

        self.graph = KnowledgeGraph(
            graph_id=f"task-{self.task_id}",
            name=f"Evidence graph for task: {task_name}",
        )
        self.telemetry = TelemetryCollector()

        # Root task node (uses task_id as node id for easy lookup)
        self._task_node = Node(
            node_type=NODE_TASK,
            properties={
                "task_id": self.task_id,
                "name": task_name,
                "description": description,
                "status": self.status,
                "parent_task_id": parent_task_id,
            },
            node_id=self.task_id,
        )
        self.graph.add_node(self._task_node)

        # Optional agent node
        self._agent_node_id: Optional[str] = None
        if agent_name:
            agent_node = Node(
                node_type=NODE_AGENT,
                properties={"name": agent_name},
            )
            self.graph.add_node(agent_node)
            self.graph.add_edge(
                Edge(
                    source_id=self._task_node.id,
                    target_id=agent_node.id,
                    relation=REL_DELEGATED_TO,
                )
            )
            self._agent_node_id = agent_node.id

        self._previous_command_node_id: Optional[str] = None

    # ---------------------------------------------------------------- Lifecycle

    def start(self) -> None:
        """Mark the task as in-progress and open a root telemetry span."""
        self.status = TaskStatus.IN_PROGRESS
        self._update_task_status()
        self.telemetry.start_span(f"task:{self.task_name}")

    def complete(self) -> None:
        """Mark the task completed and close all open telemetry spans."""
        self.status = TaskStatus.COMPLETED
        self._update_task_status()
        self._close_root_spans(TelemetrySpan.STATUS_OK)

    def fail(self, reason: str = "") -> None:
        """Mark the task failed, recording an optional reason."""
        self.status = TaskStatus.FAILED
        self._update_task_status(extra={"failure_reason": reason})
        self._close_root_spans(TelemetrySpan.STATUS_ERROR)

    def pause(self) -> None:
        """Pause the task so it can be resumed later."""
        self.status = TaskStatus.PAUSED
        self._update_task_status()

    def _close_root_spans(self, status: str) -> None:
        for span in self.telemetry.root_spans():
            if not span.is_finished:
                self.telemetry.end_span(span.id, status=status)

    def _update_task_status(self, extra: Optional[Dict[str, Any]] = None) -> None:
        props: Dict[str, Any] = {"status": self.status}
        if extra:
            props.update(extra)
        self.graph.update_node(self._task_node.id, props)
        self.updated_at = datetime.now(timezone.utc).isoformat()

    # ---------------------------------------------------------------- Evidence

    def record_command(self, result: CommandResult) -> Node:
        """
        Record a :class:`~openshell_evidence.shell.CommandResult` from OpenShell
        as a Command node.  Stdout/stderr are stored as child Output nodes.

        Returns the newly created Command node.
        """
        cmd_node = Node(
            node_type=NODE_COMMAND,
            properties={
                "command": result.command,
                "exit_code": result.exit_code,
                "success": result.success,
                "duration_ms": result.duration_ms,
                "timestamp": result.timestamp,
                "span_id": result.span_id,
            },
        )
        self.graph.add_node(cmd_node)
        self.graph.add_edge(
            Edge(
                source_id=self._task_node.id,
                target_id=cmd_node.id,
                relation=REL_HAS_COMMAND,
            )
        )

        # Chain commands in execution order
        if self._previous_command_node_id:
            self.graph.add_edge(
                Edge(
                    source_id=self._previous_command_node_id,
                    target_id=cmd_node.id,
                    relation=REL_FOLLOWS,
                )
            )
        self._previous_command_node_id = cmd_node.id

        # Capture stdout as an output node
        if result.stdout.strip():
            out_node = Node(
                node_type=NODE_OUTPUT,
                properties={
                    "kind": "stdout",
                    "content": result.stdout,
                    "command_id": cmd_node.id,
                },
            )
            self.graph.add_node(out_node)
            self.graph.add_edge(
                Edge(
                    source_id=cmd_node.id,
                    target_id=out_node.id,
                    relation=REL_PRODUCED,
                )
            )

        # Capture stderr as an output node
        if result.stderr.strip():
            err_node = Node(
                node_type=NODE_OUTPUT,
                properties={
                    "kind": "stderr",
                    "content": result.stderr,
                    "command_id": cmd_node.id,
                },
            )
            self.graph.add_node(err_node)
            self.graph.add_edge(
                Edge(
                    source_id=cmd_node.id,
                    target_id=err_node.id,
                    relation=REL_PRODUCED,
                )
            )

        return cmd_node

    def add_evidence(
        self,
        evidence_type: str,
        content: Any,
        properties: Optional[Dict[str, Any]] = None,
    ) -> Node:
        """Add arbitrary evidence (decisions, observations, etc.) to the graph."""
        evidence_node = Node(
            node_type=NODE_EVIDENCE,
            properties={
                "evidence_type": evidence_type,
                "content": content,
                **(properties or {}),
            },
        )
        self.graph.add_node(evidence_node)
        self.graph.add_edge(
            Edge(
                source_id=self._task_node.id,
                target_id=evidence_node.id,
                relation=REL_HAS_EVIDENCE,
            )
        )
        return evidence_node

    def add_artifact(
        self, name: str, path: str, artifact_type: str = ""
    ) -> Node:
        """Record a file artefact produced or consumed by the task."""
        artifact_node = Node(
            node_type=NODE_ARTIFACT,
            properties={"name": name, "path": path, "artifact_type": artifact_type},
        )
        self.graph.add_node(artifact_node)
        self.graph.add_edge(
            Edge(
                source_id=self._task_node.id,
                target_id=artifact_node.id,
                relation=REL_PRODUCED,
            )
        )
        return artifact_node

    def spawn_subtask(
        self,
        task_name: str,
        description: str = "",
        agent_name: Optional[str] = None,
    ) -> "TaskGraph":
        """
        Create a child :class:`TaskGraph` for a sub-task and link it to this
        graph via a ``SPAWNED`` edge.

        The child task has its own evidence graph and telemetry trace while
        remaining discoverable from the parent via the knowledge graph.
        """
        child = TaskGraph(
            task_name=task_name,
            description=description,
            agent_name=agent_name or self.agent_name,
            parent_task_id=self.task_id,
        )
        # Add a reference node in the parent graph so the relation is visible
        child_ref_node = Node(
            node_type=NODE_TASK,
            properties={
                "task_id": child.task_id,
                "name": task_name,
                "description": description,
                "status": child.status,
                "parent_task_id": self.task_id,
                "is_ref": True,
            },
            node_id=child.task_id,
        )
        self.graph.add_node(child_ref_node)
        self.graph.add_edge(
            Edge(
                source_id=self._task_node.id,
                target_id=child_ref_node.id,
                relation=REL_SPAWNED,
            )
        )
        return child

    # ---------------------------------------------------------------- Summary

    def summary(self) -> Dict[str, Any]:
        """Return a lightweight summary dict of task progress."""
        commands = self.graph.nodes_by_type(NODE_COMMAND)
        evidence = self.graph.nodes_by_type(NODE_EVIDENCE)
        artifacts = self.graph.nodes_by_type(NODE_ARTIFACT)
        failed = [c for c in commands if not c.properties.get("success", True)]
        return {
            "task_id": self.task_id,
            "task_name": self.task_name,
            "status": self.status,
            "commands_run": len(commands),
            "commands_failed": len(failed),
            "evidence_items": len(evidence),
            "artifacts": len(artifacts),
            "graph_nodes": len(self.graph),
            "graph_edges": len(self.graph.all_edges()),
        }

    # ---------------------------------------------------------------- Serialisation

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_name": self.task_name,
            "description": self.description,
            "agent_name": self.agent_name,
            "parent_task_id": self.parent_task_id,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "graph": self.graph.to_dict(),
            "telemetry": self.telemetry.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskGraph":
        task: "TaskGraph" = cls.__new__(cls)
        task.task_id = data["task_id"]
        task.task_name = data["task_name"]
        task.description = data.get("description", "")
        task.agent_name = data.get("agent_name")
        task.parent_task_id = data.get("parent_task_id")
        task.status = data.get("status", TaskStatus.PENDING)
        task.created_at = data.get(
            "created_at", datetime.now(timezone.utc).isoformat()
        )
        task.updated_at = data.get("updated_at", task.created_at)
        task.graph = KnowledgeGraph.from_dict(data["graph"])
        task.telemetry = TelemetryCollector.from_dict(data.get("telemetry", {}))
        task._task_node = task.graph.get_node(task.task_id) or Node(
            node_type=NODE_TASK,
            properties={"task_id": task.task_id, "name": task.task_name},
            node_id=task.task_id,
        )
        task._agent_node_id = None
        agents = task.graph.nodes_by_type(NODE_AGENT)
        if agents:
            task._agent_node_id = agents[0].id
        # Restore chaining pointer to last command node
        commands = task.graph.nodes_by_type(NODE_COMMAND)
        task._previous_command_node_id = commands[-1].id if commands else None
        return task

    def __repr__(self) -> str:
        return (
            f"TaskGraph(task_id={self.task_id!r}, "
            f"name={self.task_name!r}, status={self.status!r})"
        )
