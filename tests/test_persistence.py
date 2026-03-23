"""Tests for openshell_evidence.persistence."""

import pytest

from openshell_evidence.knowledge_graph import KnowledgeGraph, Node
from openshell_evidence.persistence import EvidenceStore
from openshell_evidence.shell import CommandResult
from openshell_evidence.task_graph import TaskGraph, TaskStatus


def _make_result():
    return CommandResult(
        command="echo hi",
        stdout="hi\n",
        stderr="",
        exit_code=0,
        duration_ms=5.0,
        timestamp="2024-01-01T00:00:00+00:00",
        span_id="span-1",
    )


class TestEvidenceStore:
    def test_save_and_load_task(self, tmp_path):
        store = EvidenceStore(store_dir=str(tmp_path))
        tg = TaskGraph(task_name="test", task_id="t1")
        tg.start()
        store.save_task(tg)

        loaded = store.load_task("t1")
        assert loaded is not None
        assert loaded.task_id == "t1"
        assert loaded.task_name == "test"

    def test_load_missing_task_returns_none(self, tmp_path):
        store = EvidenceStore(store_dir=str(tmp_path))
        assert store.load_task("no-such-id") is None

    def test_save_creates_json_file(self, tmp_path):
        store = EvidenceStore(store_dir=str(tmp_path))
        tg = TaskGraph(task_name="test", task_id="t1")
        path = store.save_task(tg)
        assert path.exists()

    def test_list_tasks_empty_initially(self, tmp_path):
        store = EvidenceStore(store_dir=str(tmp_path))
        assert store.list_tasks() == []

    def test_list_tasks_after_save(self, tmp_path):
        store = EvidenceStore(store_dir=str(tmp_path))
        tg = TaskGraph(task_name="test", task_id="t1")
        store.save_task(tg)
        tasks = store.list_tasks()
        assert len(tasks) == 1
        assert tasks[0]["task_id"] == "t1"

    def test_list_tasks_updates_on_re_save(self, tmp_path):
        store = EvidenceStore(store_dir=str(tmp_path))
        tg = TaskGraph(task_name="test", task_id="t1")
        tg.start()
        store.save_task(tg)
        tg.complete()
        store.save_task(tg)
        tasks = store.list_tasks()
        # Should still be one entry with updated status
        assert len(tasks) == 1
        assert tasks[0]["status"] == TaskStatus.COMPLETED

    def test_delete_task(self, tmp_path):
        store = EvidenceStore(store_dir=str(tmp_path))
        tg = TaskGraph(task_name="test", task_id="t1")
        store.save_task(tg)
        assert store.delete_task("t1") is True
        assert store.load_task("t1") is None
        assert store.list_tasks() == []

    def test_delete_missing_task_returns_false(self, tmp_path):
        store = EvidenceStore(store_dir=str(tmp_path))
        assert store.delete_task("no-such-id") is False

    def test_save_and_load_graph(self, tmp_path):
        store = EvidenceStore(store_dir=str(tmp_path))
        kg = KnowledgeGraph(graph_id="g1", name="test")
        kg.add_node(Node(node_type="task", node_id="n1"))
        store.save_graph(kg)

        loaded = store.load_graph("g1")
        assert loaded is not None
        assert loaded.id == "g1"
        assert loaded.get_node("n1") is not None

    def test_load_missing_graph_returns_none(self, tmp_path):
        store = EvidenceStore(store_dir=str(tmp_path))
        assert store.load_graph("no-such-id") is None

    def test_build_global_graph_merges_all_tasks(self, tmp_path):
        store = EvidenceStore(store_dir=str(tmp_path))
        t1 = TaskGraph(task_name="task1", task_id="t1")
        t1.start()
        t1.record_command(_make_result())
        store.save_task(t1)

        t2 = TaskGraph(task_name="task2", task_id="t2")
        t2.start()
        store.save_task(t2)

        global_graph = store.build_global_graph()
        # Should contain nodes from both tasks
        assert global_graph.get_node("t1") is not None
        assert global_graph.get_node("t2") is not None

    def test_build_global_graph_empty_store(self, tmp_path):
        store = EvidenceStore(store_dir=str(tmp_path))
        global_graph = store.build_global_graph()
        assert len(global_graph) == 0

    def test_repr(self, tmp_path):
        store = EvidenceStore(store_dir=str(tmp_path))
        assert "EvidenceStore" in repr(store)
