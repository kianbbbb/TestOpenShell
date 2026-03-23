"""
High-level Agent interface for the OpenShell evidence capture system.

An :class:`Agent` wraps an :class:`~openshell_evidence.shell.OpenShell`
instance and an :class:`~openshell_evidence.persistence.EvidenceStore`, and
automatically records evidence in a :class:`~openshell_evidence.task_graph.TaskGraph`
for every task it performs.
"""

from typing import Any, Dict, List, Optional

from .persistence import EvidenceStore
from .shell import CommandResult, OpenShell
from .task_graph import TaskGraph, TaskStatus


class Agent:
    """
    An agent that uses OpenShell to complete tasks while automatically
    capturing evidence in per-task knowledge graphs.

    Parameters
    ----------
    name:
        Human-readable name for this agent.
    store:
        :class:`~openshell_evidence.persistence.EvidenceStore` where task
        graphs are persisted.  Created automatically when not provided.
    allowed_commands:
        Optional allow-list of shell command base names.  ``None`` permits all.
    working_dir:
        Default working directory for shell commands.
    store_dir:
        Path to the evidence store directory.  Used only when *store* is not
        provided.
    """

    def __init__(
        self,
        name: str,
        store: Optional[EvidenceStore] = None,
        allowed_commands: Optional[List[str]] = None,
        working_dir: Optional[str] = None,
        store_dir: Optional[str] = None,
    ) -> None:
        self.name = name
        self.store = store or EvidenceStore(store_dir=store_dir)
        self._allowed_commands = allowed_commands
        self._working_dir = working_dir
        self._current_task: Optional[TaskGraph] = None
        self._shell: Optional[OpenShell] = None

    # ---------------------------------------------------------------- Task lifecycle

    def begin_task(
        self,
        task_name: str,
        description: str = "",
        task_id: Optional[str] = None,
        parent_task_id: Optional[str] = None,
    ) -> TaskGraph:
        """
        Start a new task.

        Creates a fresh :class:`~openshell_evidence.task_graph.TaskGraph` and
        binds a new :class:`~openshell_evidence.shell.OpenShell` instance to
        the task's telemetry collector.
        """
        task = TaskGraph(
            task_name=task_name,
            task_id=task_id,
            description=description,
            agent_name=self.name,
            parent_task_id=parent_task_id,
        )
        task.start()
        self._current_task = task
        self._shell = OpenShell(
            allowed_commands=self._allowed_commands,
            working_dir=self._working_dir,
            telemetry=task.telemetry,
        )
        self.store.save_task(task)
        return task

    def resume_task(self, task_id: str) -> Optional[TaskGraph]:
        """
        Resume a previously persisted task.

        Returns the :class:`~openshell_evidence.task_graph.TaskGraph` or
        ``None`` when the task cannot be found.
        """
        task = self.store.load_task(task_id)
        if task is None:
            return None
        task.status = TaskStatus.IN_PROGRESS
        task._update_task_status()
        self._current_task = task
        self._shell = OpenShell(
            allowed_commands=self._allowed_commands,
            working_dir=self._working_dir,
            telemetry=task.telemetry,
        )
        return task

    def end_task(
        self, success: bool = True, reason: str = ""
    ) -> Optional[TaskGraph]:
        """
        Complete or fail the current task and persist the evidence.

        Returns the finished :class:`~openshell_evidence.task_graph.TaskGraph`.
        """
        if self._current_task is None:
            return None
        if success:
            self._current_task.complete()
        else:
            self._current_task.fail(reason)
        self.store.save_task(self._current_task)
        finished = self._current_task
        self._current_task = None
        self._shell = None
        return finished

    # ---------------------------------------------------------------- Shell operations

    def run(self, command: str) -> CommandResult:
        """
        Execute a shell command in the current task context, recording
        the result as evidence automatically.

        Raises
        ------
        RuntimeError
            When no task is active.
        PermissionError
            When the command is not on the allow-list.
        """
        if self._shell is None or self._current_task is None:
            raise RuntimeError(
                "No active task.  Call begin_task() or resume_task() first."
            )
        result = self._shell.run(command)
        self._current_task.record_command(result)
        self.store.save_task(self._current_task)
        return result

    # ---------------------------------------------------------------- Evidence helpers

    def add_evidence(
        self,
        evidence_type: str,
        content: Any,
        properties: Optional[Dict[str, Any]] = None,
    ):
        """Add arbitrary evidence to the current task's graph."""
        if self._current_task is None:
            raise RuntimeError("No active task.")
        return self._current_task.add_evidence(evidence_type, content, properties)

    def add_artifact(self, name: str, path: str, artifact_type: str = ""):
        """Record a file artefact in the current task's graph."""
        if self._current_task is None:
            raise RuntimeError("No active task.")
        return self._current_task.add_artifact(name, path, artifact_type)

    def spawn_subtask(
        self, task_name: str, description: str = ""
    ) -> "Agent":
        """
        Create a child agent/task pair for a sub-task.

        The child agent shares the same evidence store and allowed commands.
        Its evidence graph is linked to the parent via a ``SPAWNED`` edge.

        Returns the child :class:`Agent` with its task already started.
        """
        if self._current_task is None:
            raise RuntimeError("No active task.")
        child_task = self._current_task.spawn_subtask(
            task_name=task_name,
            description=description,
            agent_name=self.name,
        )
        self.store.save_task(self._current_task)

        child_agent = Agent(
            name=self.name,
            store=self.store,
            allowed_commands=self._allowed_commands,
            working_dir=self._working_dir,
        )
        child_agent._current_task = child_task
        child_task.start()
        child_agent._shell = OpenShell(
            allowed_commands=self._allowed_commands,
            working_dir=self._working_dir,
            telemetry=child_task.telemetry,
        )
        self.store.save_task(child_task)
        return child_agent

    # ---------------------------------------------------------------- Queries

    @property
    def current_task(self) -> Optional[TaskGraph]:
        """The currently active :class:`~openshell_evidence.task_graph.TaskGraph`."""
        return self._current_task

    def global_graph(self):
        """
        Return the global knowledge graph built by merging all persisted tasks.

        This is the shared memory space that allows an agent to understand
        what all previous tasks accomplished.
        """
        return self.store.build_global_graph()

    def __repr__(self) -> str:
        task = self._current_task
        task_name = repr(task.task_name) if task else "None"
        return f"Agent(name={self.name!r}, current_task={task_name})"
