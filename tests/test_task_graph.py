"""Tests for openshell_evidence.task_graph."""

import pytest

from openshell_evidence.shell import CommandResult
from openshell_evidence.task_graph import (
    NODE_ARTIFACT,
    NODE_COMMAND,
    NODE_EVIDENCE,
    NODE_OUTPUT,
    NODE_TASK,
    REL_FOLLOWS,
    REL_HAS_COMMAND,
    REL_HAS_EVIDENCE,
    REL_PRODUCED,
    REL_SPAWNED,
    TaskGraph,
    TaskStatus,
)


def _make_result(
    command="echo hi",
    stdout="hi\n",
    stderr="",
    exit_code=0,
):
    return CommandResult(
        command=command,
        stdout=stdout,
        stderr=stderr,
        exit_code=exit_code,
        duration_ms=10.0,
        timestamp="2024-01-01T00:00:00+00:00",
        span_id="span-1",
    )


class TestTaskGraphLifecycle:
    def test_initial_status_pending(self):
        tg = TaskGraph(task_name="test")
        assert tg.status == TaskStatus.PENDING

    def test_start_sets_in_progress(self):
        tg = TaskGraph(task_name="test")
        tg.start()
        assert tg.status == TaskStatus.IN_PROGRESS

    def test_complete_sets_completed(self):
        tg = TaskGraph(task_name="test")
        tg.start()
        tg.complete()
        assert tg.status == TaskStatus.COMPLETED

    def test_fail_sets_failed(self):
        tg = TaskGraph(task_name="test")
        tg.start()
        tg.fail("something broke")
        assert tg.status == TaskStatus.FAILED

    def test_pause_sets_paused(self):
        tg = TaskGraph(task_name="test")
        tg.start()
        tg.pause()
        assert tg.status == TaskStatus.PAUSED

    def test_root_task_node_created(self):
        tg = TaskGraph(task_name="test", task_id="t1")
        assert tg.graph.get_node("t1") is not None

    def test_agent_node_created_when_name_given(self):
        tg = TaskGraph(task_name="test", agent_name="bot")
        agents = tg.graph.nodes_by_type("agent")
        assert len(agents) == 1
        assert agents[0].properties["name"] == "bot"

    def test_no_agent_node_without_name(self):
        tg = TaskGraph(task_name="test")
        assert tg.graph.nodes_by_type("agent") == []


class TestTaskGraphRecordCommand:
    def test_record_command_creates_command_node(self):
        tg = TaskGraph(task_name="test")
        tg.start()
        tg.record_command(_make_result())
        cmds = tg.graph.nodes_by_type(NODE_COMMAND)
        assert len(cmds) == 1

    def test_record_command_links_to_task(self):
        tg = TaskGraph(task_name="test", task_id="t1")
        tg.start()
        tg.record_command(_make_result())
        edges = tg.graph.edges_by_relation(REL_HAS_COMMAND)
        assert len(edges) == 1
        assert edges[0].source_id == "t1"

    def test_record_stdout_creates_output_node(self):
        tg = TaskGraph(task_name="test")
        tg.start()
        tg.record_command(_make_result(stdout="output line\n"))
        outputs = tg.graph.nodes_by_type(NODE_OUTPUT)
        assert any(o.properties["kind"] == "stdout" for o in outputs)

    def test_record_stderr_creates_error_node(self):
        tg = TaskGraph(task_name="test")
        tg.start()
        tg.record_command(_make_result(stderr="err\n", stdout=""))
        outputs = tg.graph.nodes_by_type(NODE_OUTPUT)
        assert any(o.properties["kind"] == "stderr" for o in outputs)

    def test_no_output_node_when_blank_stdout(self):
        tg = TaskGraph(task_name="test")
        tg.start()
        tg.record_command(_make_result(stdout="", stderr=""))
        assert tg.graph.nodes_by_type(NODE_OUTPUT) == []

    def test_commands_chained_with_follows_edge(self):
        tg = TaskGraph(task_name="test")
        tg.start()
        tg.record_command(_make_result(command="echo 1"))
        tg.record_command(_make_result(command="echo 2"))
        follows = tg.graph.edges_by_relation(REL_FOLLOWS)
        assert len(follows) == 1


class TestTaskGraphEvidence:
    def test_add_evidence_creates_node(self):
        tg = TaskGraph(task_name="test")
        tg.start()
        ev = tg.add_evidence("observation", "server is running")
        nodes = tg.graph.nodes_by_type(NODE_EVIDENCE)
        assert len(nodes) == 1
        assert nodes[0].id == ev.id

    def test_add_evidence_links_to_task(self):
        tg = TaskGraph(task_name="test", task_id="t1")
        tg.start()
        tg.add_evidence("obs", "data")
        edges = tg.graph.edges_by_relation(REL_HAS_EVIDENCE)
        assert edges[0].source_id == "t1"

    def test_add_evidence_stores_content(self):
        tg = TaskGraph(task_name="test")
        tg.start()
        ev = tg.add_evidence("decision", {"chose": "option_a"})
        assert ev.properties["content"] == {"chose": "option_a"}

    def test_add_artifact_creates_node(self):
        tg = TaskGraph(task_name="test")
        tg.start()
        art = tg.add_artifact("report.txt", "/tmp/report.txt", "text")
        nodes = tg.graph.nodes_by_type(NODE_ARTIFACT)
        assert len(nodes) == 1
        assert nodes[0].id == art.id
        assert art.properties["path"] == "/tmp/report.txt"


class TestTaskGraphSpawnSubtask:
    def test_spawn_creates_child_task_graph(self):
        parent = TaskGraph(task_name="parent")
        parent.start()
        child = parent.spawn_subtask("child")
        assert child.task_name == "child"
        assert child.parent_task_id == parent.task_id

    def test_spawn_adds_ref_node_in_parent(self):
        parent = TaskGraph(task_name="parent", task_id="p1")
        parent.start()
        child = parent.spawn_subtask("child")
        ref = parent.graph.get_node(child.task_id)
        assert ref is not None

    def test_spawn_creates_spawned_edge(self):
        parent = TaskGraph(task_name="parent")
        parent.start()
        parent.spawn_subtask("child")
        assert len(parent.graph.edges_by_relation(REL_SPAWNED)) == 1

    def test_spawn_inherits_agent_name(self):
        parent = TaskGraph(task_name="parent", agent_name="bot")
        parent.start()
        child = parent.spawn_subtask("child")
        assert child.agent_name == "bot"


class TestTaskGraphSummary:
    def test_summary_keys(self):
        tg = TaskGraph(task_name="test")
        tg.start()
        s = tg.summary()
        for key in ("task_id", "task_name", "status", "commands_run",
                    "commands_failed", "evidence_items", "artifacts",
                    "graph_nodes", "graph_edges"):
            assert key in s

    def test_summary_counts(self):
        tg = TaskGraph(task_name="test")
        tg.start()
        tg.record_command(_make_result())
        tg.record_command(_make_result(exit_code=1, stdout=""))
        tg.add_evidence("obs", "data")
        s = tg.summary()
        assert s["commands_run"] == 2
        assert s["commands_failed"] == 1
        assert s["evidence_items"] == 1


class TestTaskGraphSerialisation:
    def test_round_trip_preserves_task_id(self):
        tg = TaskGraph(task_name="test", task_id="t1")
        tg.start()
        tg.record_command(_make_result())
        restored = TaskGraph.from_dict(tg.to_dict())
        assert restored.task_id == "t1"

    def test_round_trip_preserves_status(self):
        tg = TaskGraph(task_name="test")
        tg.start()
        tg.complete()
        restored = TaskGraph.from_dict(tg.to_dict())
        assert restored.status == TaskStatus.COMPLETED

    def test_round_trip_preserves_graph_nodes(self):
        tg = TaskGraph(task_name="test", agent_name="bot")
        tg.start()
        tg.record_command(_make_result(stdout="out\n"))
        data = tg.to_dict()
        restored = TaskGraph.from_dict(data)
        assert len(restored.graph) == len(tg.graph)

    def test_round_trip_preserves_telemetry(self):
        tg = TaskGraph(task_name="test")
        tg.start()
        tg.complete()
        restored = TaskGraph.from_dict(tg.to_dict())
        assert len(restored.telemetry.all_spans()) == len(tg.telemetry.all_spans())

    def test_repr(self):
        tg = TaskGraph(task_name="my task", task_id="t1")
        r = repr(tg)
        assert "t1" in r
        assert "my task" in r
