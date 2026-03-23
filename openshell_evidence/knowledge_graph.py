"""
Core knowledge graph implementation for OpenShell evidence capture.

The knowledge graph stores entities (nodes) and their relationships (edges)
as a directed graph.  Nodes represent tasks, commands, outputs, agents, and
other entities.  Edges represent relationships between these entities.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class Node:
    """A node in the knowledge graph representing an entity."""

    def __init__(
        self,
        node_type: str,
        properties: Optional[Dict[str, Any]] = None,
        node_id: Optional[str] = None,
    ) -> None:
        self.id = node_id or str(uuid.uuid4())
        self.type = node_type
        self.properties: Dict[str, Any] = properties or {}
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.updated_at = self.created_at

    def update(self, properties: Dict[str, Any]) -> None:
        """Merge *properties* into this node and refresh the updated timestamp."""
        self.properties.update(properties)
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "properties": self.properties,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Node":
        node = cls(
            node_type=data["type"],
            properties=data.get("properties", {}),
            node_id=data["id"],
        )
        node.created_at = data.get("created_at", node.created_at)
        node.updated_at = data.get("updated_at", node.updated_at)
        return node

    def __repr__(self) -> str:
        return f"Node(id={self.id!r}, type={self.type!r})"


class Edge:
    """A directed edge in the knowledge graph representing a relationship."""

    def __init__(
        self,
        source_id: str,
        target_id: str,
        relation: str,
        properties: Optional[Dict[str, Any]] = None,
        edge_id: Optional[str] = None,
    ) -> None:
        self.id = edge_id or str(uuid.uuid4())
        self.source_id = source_id
        self.target_id = target_id
        self.relation = relation
        self.properties: Dict[str, Any] = properties or {}
        self.created_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relation": self.relation,
            "properties": self.properties,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Edge":
        edge = cls(
            source_id=data["source_id"],
            target_id=data["target_id"],
            relation=data["relation"],
            properties=data.get("properties", {}),
            edge_id=data["id"],
        )
        edge.created_at = data.get("created_at", edge.created_at)
        return edge

    def __repr__(self) -> str:
        return (
            f"Edge(id={self.id!r}, "
            f"{self.source_id!r} -[{self.relation}]-> {self.target_id!r})"
        )


class KnowledgeGraph:
    """
    A directed knowledge graph for storing and querying entity relationships.

    The graph maintains nodes and edges, supports queries by type and
    relationship, and can be serialised to/from a dictionary.
    """

    def __init__(
        self,
        graph_id: Optional[str] = None,
        name: str = "",
    ) -> None:
        self.id = graph_id or str(uuid.uuid4())
        self.name = name
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.updated_at = self.created_at
        self._nodes: Dict[str, Node] = {}
        self._edges: Dict[str, Edge] = {}
        # Adjacency: source_id -> list of edge_ids
        self._out_edges: Dict[str, List[str]] = {}
        # Reverse adjacency: target_id -> list of edge_ids
        self._in_edges: Dict[str, List[str]] = {}

    # ------------------------------------------------------------------ Nodes

    def add_node(self, node: Node) -> Node:
        """Add *node* to the graph."""
        self._nodes[node.id] = node
        self._out_edges.setdefault(node.id, [])
        self._in_edges.setdefault(node.id, [])
        self._touch()
        return node

    def get_node(self, node_id: str) -> Optional[Node]:
        """Return the node with *node_id* or ``None``."""
        return self._nodes.get(node_id)

    def update_node(self, node_id: str, properties: Dict[str, Any]) -> Optional[Node]:
        """Merge *properties* into the node and return it, or ``None`` if absent."""
        node = self._nodes.get(node_id)
        if node:
            node.update(properties)
            self._touch()
        return node

    def nodes_by_type(self, node_type: str) -> List[Node]:
        """Return all nodes of *node_type*."""
        return [n for n in self._nodes.values() if n.type == node_type]

    def all_nodes(self) -> List[Node]:
        return list(self._nodes.values())

    # ------------------------------------------------------------------ Edges

    def add_edge(self, edge: Edge) -> Edge:
        """Add a directed edge between two existing nodes."""
        if edge.source_id not in self._nodes:
            raise ValueError(f"Source node {edge.source_id!r} not found in graph")
        if edge.target_id not in self._nodes:
            raise ValueError(f"Target node {edge.target_id!r} not found in graph")
        self._edges[edge.id] = edge
        self._out_edges.setdefault(edge.source_id, []).append(edge.id)
        self._in_edges.setdefault(edge.target_id, []).append(edge.id)
        self._touch()
        return edge

    def get_edge(self, edge_id: str) -> Optional[Edge]:
        return self._edges.get(edge_id)

    def edges_from(self, node_id: str) -> List[Edge]:
        """Return all edges originating at *node_id*."""
        return [self._edges[eid] for eid in self._out_edges.get(node_id, [])]

    def edges_to(self, node_id: str) -> List[Edge]:
        """Return all edges terminating at *node_id*."""
        return [self._edges[eid] for eid in self._in_edges.get(node_id, [])]

    def edges_by_relation(self, relation: str) -> List[Edge]:
        """Return all edges with the given *relation* type."""
        return [e for e in self._edges.values() if e.relation == relation]

    def all_edges(self) -> List[Edge]:
        return list(self._edges.values())

    # ------------------------------------------------------------------ Query

    def neighbors(
        self, node_id: str, relation: Optional[str] = None
    ) -> List[Node]:
        """Return nodes reachable from *node_id*, filtered by *relation* if given."""
        edges = self.edges_from(node_id)
        if relation is not None:
            edges = [e for e in edges if e.relation == relation]
        return [
            self._nodes[e.target_id]
            for e in edges
            if e.target_id in self._nodes
        ]

    # ------------------------------------------------------------------ Merge

    def merge(self, other: "KnowledgeGraph") -> None:
        """Merge *other* into this graph.  Existing nodes/edges are kept."""
        for node in other.all_nodes():
            if node.id not in self._nodes:
                self.add_node(node)
        for edge in other.all_edges():
            if edge.id not in self._edges:
                # Only add if both endpoints exist after the node merge
                if edge.source_id in self._nodes and edge.target_id in self._nodes:
                    self.add_edge(edge)

    # ------------------------------------------------------------------ Serialisation

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "nodes": [n.to_dict() for n in self._nodes.values()],
            "edges": [e.to_dict() for e in self._edges.values()],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "KnowledgeGraph":
        kg = cls(graph_id=data["id"], name=data.get("name", ""))
        kg.created_at = data.get("created_at", kg.created_at)
        kg.updated_at = data.get("updated_at", kg.updated_at)
        for node_data in data.get("nodes", []):
            node = Node.from_dict(node_data)
            kg._nodes[node.id] = node
            kg._out_edges.setdefault(node.id, [])
            kg._in_edges.setdefault(node.id, [])
        for edge_data in data.get("edges", []):
            edge = Edge.from_dict(edge_data)
            kg._edges[edge.id] = edge
            kg._out_edges.setdefault(edge.source_id, []).append(edge.id)
            kg._in_edges.setdefault(edge.target_id, []).append(edge.id)
        return kg

    def __len__(self) -> int:
        return len(self._nodes)

    def __repr__(self) -> str:
        return (
            f"KnowledgeGraph(id={self.id!r}, name={self.name!r}, "
            f"nodes={len(self._nodes)}, edges={len(self._edges)})"
        )

    def _touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc).isoformat()
