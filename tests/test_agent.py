"""Tests for openshell_evidence.agent."""

import pytest

from openshell_evidence.agent import Agent
from openshell_evidence.persistence import EvidenceStore
from openshell_evidence.task_graph import TaskStatus


class TestAgentTaskLifecycle:
    def test_begin_task_returns_task_graph(self, tmp_path):
        agent = Agent(name="bot", store_dir=str(tmp_path))
        task = agent.begin_task("test task")
        assert task.task_name == "test task"
        assert task.status == TaskStatus.IN_PROGRESS

    def test_begin_task_creates_current_task(self, tmp_path):
        agent = Agent(name="bot", store_dir=str(tmp_path))
        task = agent.begin_task("test task")
        assert agent.current_task is task

    def test_end_task_completes(self, tmp_path):
        agent = Agent(name="bot", store_dir=str(tmp_path))
        agent.begin_task("test task")
        finished = agent.end_task(success=True)
        assert finished.status == TaskStatus.COMPLETED
        assert agent.current_task is None

    def test_end_task_fails(self, tmp_path):
        agent = Agent(name="bot", store_dir=str(tmp_path))
        agent.begin_task("test task")
        finished = agent.end_task(success=False, reason="oops")
        assert finished.status == TaskStatus.FAILED

    def test_end_task_without_active_task_returns_none(self, tmp_path):
        agent = Agent(name="bot", store_dir=str(tmp_path))
        assert agent.end_task() is None

    def test_task_persisted_on_begin(self, tmp_path):
        agent = Agent(name="bot", store_dir=str(tmp_path))
        task = agent.begin_task("test task")
        loaded = agent.store.load_task(task.task_id)
        assert loaded is not None

    def test_task_persisted_on_end(self, tmp_path):
        agent = Agent(name="bot", store_dir=str(tmp_path))
        task = agent.begin_task("test task")
        agent.end_task()
        loaded = agent.store.load_task(task.task_id)
        assert loaded.status == TaskStatus.COMPLETED


class TestAgentResume:
    def test_resume_task_restores_graph(self, tmp_path):
        agent = Agent(name="bot", store_dir=str(tmp_path))
        task = agent.begin_task("resume test", task_id="t-resume")
        agent.end_task()

        agent2 = Agent(name="bot", store_dir=str(tmp_path))
        resumed = agent2.resume_task("t-resume")
        assert resumed is not None
        assert resumed.task_id == "t-resume"
        assert resumed.status == TaskStatus.IN_PROGRESS

    def test_resume_missing_task_returns_none(self, tmp_path):
        agent = Agent(name="bot", store_dir=str(tmp_path))
        assert agent.resume_task("no-such-id") is None


class TestAgentRun:
    def test_run_executes_command(self, tmp_path):
        agent = Agent(name="bot", store_dir=str(tmp_path))
        agent.begin_task("run test")
        result = agent.run("echo hello")
        assert result.success
        assert "hello" in result.stdout

    def test_run_records_command_in_task(self, tmp_path):
        agent = Agent(name="bot", store_dir=str(tmp_path))
        agent.begin_task("run test")
        agent.run("echo hello")
        from openshell_evidence.task_graph import NODE_COMMAND
        cmds = agent.current_task.graph.nodes_by_type(NODE_COMMAND)
        assert len(cmds) == 1

    def test_run_without_task_raises(self, tmp_path):
        agent = Agent(name="bot", store_dir=str(tmp_path))
        with pytest.raises(RuntimeError, match="No active task"):
            agent.run("echo hi")

    def test_run_blocked_command_raises(self, tmp_path):
        agent = Agent(
            name="bot",
            store_dir=str(tmp_path),
            allowed_commands=["echo"],
        )
        agent.begin_task("restricted task")
        with pytest.raises(PermissionError):
            agent.run("ls")

    def test_run_persists_evidence(self, tmp_path):
        agent = Agent(name="bot", store_dir=str(tmp_path))
        task = agent.begin_task("persist test")
        agent.run("echo hello")

        loaded = agent.store.load_task(task.task_id)
        from openshell_evidence.task_graph import NODE_COMMAND
        assert len(loaded.graph.nodes_by_type(NODE_COMMAND)) == 1


class TestAgentEvidence:
    def test_add_evidence(self, tmp_path):
        agent = Agent(name="bot", store_dir=str(tmp_path))
        agent.begin_task("evidence test")
        node = agent.add_evidence("observation", "the server is up")
        from openshell_evidence.task_graph import NODE_EVIDENCE
        ev = agent.current_task.graph.nodes_by_type(NODE_EVIDENCE)
        assert len(ev) == 1

    def test_add_evidence_without_task_raises(self, tmp_path):
        agent = Agent(name="bot", store_dir=str(tmp_path))
        with pytest.raises(RuntimeError, match="No active task"):
            agent.add_evidence("obs", "data")

    def test_add_artifact(self, tmp_path):
        agent = Agent(name="bot", store_dir=str(tmp_path))
        agent.begin_task("artifact test")
        agent.add_artifact("report", "/tmp/report.txt")
        from openshell_evidence.task_graph import NODE_ARTIFACT
        arts = agent.current_task.graph.nodes_by_type(NODE_ARTIFACT)
        assert len(arts) == 1

    def test_add_artifact_without_task_raises(self, tmp_path):
        agent = Agent(name="bot", store_dir=str(tmp_path))
        with pytest.raises(RuntimeError, match="No active task"):
            agent.add_artifact("file", "/path")


class TestAgentSpawnSubtask:
    def test_spawn_creates_child_agent(self, tmp_path):
        store = EvidenceStore(store_dir=str(tmp_path))
        parent = Agent(name="parent-bot", store=store)
        parent.begin_task("parent task")
        child = parent.spawn_subtask("child task")
        assert child.current_task is not None
        assert child.current_task.task_name == "child task"

    def test_spawn_child_shares_store(self, tmp_path):
        store = EvidenceStore(store_dir=str(tmp_path))
        parent = Agent(name="bot", store=store)
        parent.begin_task("parent task")
        child = parent.spawn_subtask("child task")
        assert child.store is store

    def test_spawn_without_task_raises(self, tmp_path):
        agent = Agent(name="bot", store_dir=str(tmp_path))
        with pytest.raises(RuntimeError, match="No active task"):
            agent.spawn_subtask("child")

    def test_spawned_child_can_run_commands(self, tmp_path):
        store = EvidenceStore(store_dir=str(tmp_path))
        parent = Agent(name="bot", store=store)
        parent.begin_task("parent task")
        child = parent.spawn_subtask("child task")
        result = child.run("echo from child")
        assert result.success

    def test_spawned_child_evidence_in_global_graph(self, tmp_path):
        store = EvidenceStore(store_dir=str(tmp_path))
        parent = Agent(name="bot", store=store)
        parent.begin_task("parent task")
        child = parent.spawn_subtask("child task")
        child.run("echo child output")
        child.end_task()
        parent.end_task()

        global_graph = parent.global_graph()
        assert len(global_graph) > 0


class TestAgentGlobalGraph:
    def test_global_graph_includes_all_tasks(self, tmp_path):
        store = EvidenceStore(store_dir=str(tmp_path))

        a1 = Agent(name="bot1", store=store)
        t1 = a1.begin_task("task1", task_id="t1")
        a1.end_task()

        a2 = Agent(name="bot2", store=store)
        t2 = a2.begin_task("task2", task_id="t2")
        a2.end_task()

        a3 = Agent(name="bot3", store=store)
        gg = a3.global_graph()
        assert gg.get_node("t1") is not None
        assert gg.get_node("t2") is not None

    def test_repr(self, tmp_path):
        agent = Agent(name="bot", store_dir=str(tmp_path))
        assert "bot" in repr(agent)
