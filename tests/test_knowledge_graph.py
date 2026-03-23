"""Tests for openshell_evidence.knowledge_graph."""

import pytest

from openshell_evidence.knowledge_graph import Edge, KnowledgeGraph, Node


class TestNode:
    def test_default_id_is_uuid(self):
        node = Node(node_type="task")
        assert len(node.id) == 36  # UUID string length

    def test_explicit_id(self):
        node = Node(node_type="task", node_id="my-id")
        assert node.id == "my-id"

    def test_properties_default_empty(self):
        node = Node(node_type="task")
        assert node.properties == {}

    def test_update_merges_properties(self):
        node = Node(node_type="task", properties={"a": 1})
        node.update({"b": 2})
        assert node.properties == {"a": 1, "b": 2}

    def test_update_refreshes_updated_at(self):
        node = Node(node_type="task")
        old = node.updated_at
        node.update({"x": 1})
        assert node.updated_at >= old

    def test_round_trip(self):
        node = Node(node_type="agent", properties={"name": "bot"}, node_id="n1")
        restored = Node.from_dict(node.to_dict())
        assert restored.id == "n1"
        assert restored.type == "agent"
        assert restored.properties == {"name": "bot"}

    def test_repr(self):
        node = Node(node_type="task", node_id="x")
        assert "x" in repr(node)
        assert "task" in repr(node)


class TestEdge:
    def test_default_id_is_uuid(self):
        edge = Edge(source_id="a", target_id="b", relation="HAS")
        assert len(edge.id) == 36

    def test_round_trip(self):
        edge = Edge(
            source_id="s",
            target_id="t",
            relation="FOLLOWS",
            properties={"order": 1},
            edge_id="e1",
        )
        restored = Edge.from_dict(edge.to_dict())
        assert restored.id == "e1"
        assert restored.source_id == "s"
        assert restored.target_id == "t"
        assert restored.relation == "FOLLOWS"
        assert restored.properties == {"order": 1}

    def test_repr(self):
        edge = Edge(source_id="a", target_id="b", relation="REL")
        assert "REL" in repr(edge)


class TestKnowledgeGraph:
    def _make_graph(self):
        kg = KnowledgeGraph(graph_id="g1", name="test")
        n1 = kg.add_node(Node(node_type="task", node_id="n1"))
        n2 = kg.add_node(Node(node_type="command", node_id="n2"))
        e = kg.add_edge(Edge(source_id="n1", target_id="n2", relation="HAS_COMMAND"))
        return kg, n1, n2, e

    def test_add_node_and_get(self):
        kg = KnowledgeGraph()
        node = Node(node_type="task", node_id="x")
        kg.add_node(node)
        assert kg.get_node("x") is node

    def test_get_missing_node_returns_none(self):
        kg = KnowledgeGraph()
        assert kg.get_node("missing") is None

    def test_update_node(self):
        kg = KnowledgeGraph()
        kg.add_node(Node(node_type="task", node_id="x"))
        kg.update_node("x", {"status": "done"})
        assert kg.get_node("x").properties["status"] == "done"

    def test_update_missing_node_returns_none(self):
        kg = KnowledgeGraph()
        assert kg.update_node("nope", {}) is None

    def test_nodes_by_type(self):
        kg, *_ = self._make_graph()
        tasks = kg.nodes_by_type("task")
        assert len(tasks) == 1
        assert tasks[0].id == "n1"

    def test_add_edge_and_get(self):
        kg, n1, n2, e = self._make_graph()
        assert kg.get_edge(e.id) is e

    def test_add_edge_missing_source_raises(self):
        kg = KnowledgeGraph()
        kg.add_node(Node(node_type="task", node_id="n2"))
        with pytest.raises(ValueError, match="Source node"):
            kg.add_edge(Edge(source_id="missing", target_id="n2", relation="X"))

    def test_add_edge_missing_target_raises(self):
        kg = KnowledgeGraph()
        kg.add_node(Node(node_type="task", node_id="n1"))
        with pytest.raises(ValueError, match="Target node"):
            kg.add_edge(Edge(source_id="n1", target_id="missing", relation="X"))

    def test_edges_from(self):
        kg, *_ = self._make_graph()
        edges = kg.edges_from("n1")
        assert len(edges) == 1
        assert edges[0].relation == "HAS_COMMAND"

    def test_edges_to(self):
        kg, *_ = self._make_graph()
        edges = kg.edges_to("n2")
        assert len(edges) == 1

    def test_edges_by_relation(self):
        kg, *_ = self._make_graph()
        assert len(kg.edges_by_relation("HAS_COMMAND")) == 1
        assert len(kg.edges_by_relation("NOPE")) == 0

    def test_neighbors_no_filter(self):
        kg, *_ = self._make_graph()
        neighbors = kg.neighbors("n1")
        assert len(neighbors) == 1
        assert neighbors[0].id == "n2"

    def test_neighbors_with_relation(self):
        kg, *_ = self._make_graph()
        assert len(kg.neighbors("n1", relation="HAS_COMMAND")) == 1
        assert len(kg.neighbors("n1", relation="OTHER")) == 0

    def test_len(self):
        kg, *_ = self._make_graph()
        assert len(kg) == 2

    def test_merge(self):
        kg1 = KnowledgeGraph()
        n1 = kg1.add_node(Node(node_type="task", node_id="n1"))

        kg2 = KnowledgeGraph()
        n2 = kg2.add_node(Node(node_type="command", node_id="n2"))

        kg1.merge(kg2)
        assert kg1.get_node("n2") is not None

    def test_merge_skips_duplicates(self):
        kg1 = KnowledgeGraph()
        kg1.add_node(Node(node_type="task", node_id="shared"))

        kg2 = KnowledgeGraph()
        kg2.add_node(Node(node_type="task", node_id="shared"))

        kg1.merge(kg2)
        assert len(kg1) == 1

    def test_round_trip(self):
        kg, *_ = self._make_graph()
        restored = KnowledgeGraph.from_dict(kg.to_dict())
        assert restored.id == kg.id
        assert restored.name == kg.name
        assert len(restored) == len(kg)
        assert len(restored.all_edges()) == len(kg.all_edges())

    def test_repr(self):
        kg = KnowledgeGraph(graph_id="g1", name="test")
        r = repr(kg)
        assert "g1" in r
        assert "test" in r
