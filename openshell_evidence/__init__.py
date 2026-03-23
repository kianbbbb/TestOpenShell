"""
OpenShell Evidence Capture – public API.

Core classes
------------
- :class:`Agent` – high-level agent interface
- :class:`OpenShell` – constrained shell executor
- :class:`TaskGraph` – per-task evidence sub-graph
- :class:`KnowledgeGraph` – core directed knowledge graph
- :class:`EvidenceStore` – file-system-backed persistence
- :class:`TelemetryCollector` – span-based telemetry
- :class:`TelemetrySpan` – individual telemetry span
- :class:`CommandResult` – result of a shell command execution
- :class:`Node` / :class:`Edge` – graph primitives
"""

from .agent import Agent
from .knowledge_graph import Edge, KnowledgeGraph, Node
from .persistence import EvidenceStore
from .shell import CommandResult, OpenShell
from .task_graph import (
    NODE_AGENT,
    NODE_ARTIFACT,
    NODE_COMMAND,
    NODE_EVIDENCE,
    NODE_OUTPUT,
    NODE_TASK,
    REL_DELEGATED_TO,
    REL_DEPENDS_ON,
    REL_FOLLOWS,
    REL_HAS_COMMAND,
    REL_HAS_EVIDENCE,
    REL_PRODUCED,
    REL_SPAWNED,
    TaskGraph,
    TaskStatus,
)
from .telemetry import TelemetryCollector, TelemetrySpan

__all__ = [
    "Agent",
    "CommandResult",
    "Edge",
    "EvidenceStore",
    "KnowledgeGraph",
    "Node",
    "OpenShell",
    "TaskGraph",
    "TaskStatus",
    "TelemetryCollector",
    "TelemetrySpan",
    # Node type constants
    "NODE_AGENT",
    "NODE_ARTIFACT",
    "NODE_COMMAND",
    "NODE_EVIDENCE",
    "NODE_OUTPUT",
    "NODE_TASK",
    # Relation type constants
    "REL_DELEGATED_TO",
    "REL_DEPENDS_ON",
    "REL_FOLLOWS",
    "REL_HAS_COMMAND",
    "REL_HAS_EVIDENCE",
    "REL_PRODUCED",
    "REL_SPAWNED",
]
