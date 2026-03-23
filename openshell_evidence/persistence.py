"""
Persistence layer for OpenShell evidence graphs.

Graphs are stored as JSON files in a configurable store directory.  The store
maintains a manifest so you can list, load, and delete graphs by task ID or
graph ID.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .knowledge_graph import KnowledgeGraph
from .task_graph import TaskGraph

_DEFAULT_STORE = Path.home() / ".openshell" / "evidence_store"


class EvidenceStore:
    """
    A file-system-backed store for task evidence graphs.

    Directory layout::

        store_dir/
            manifest.json           – index of all stored task graphs
            tasks/<task_id>.json    – one JSON file per TaskGraph
            graphs/<graph_id>.json  – raw KnowledgeGraph files (optional)

    Parameters
    ----------
    store_dir:
        Root directory for the store.  Defaults to
        ``~/.openshell/evidence_store``.
    """

    MANIFEST_FILE = "manifest.json"

    def __init__(self, store_dir: Optional[str] = None) -> None:
        self.store_dir = Path(store_dir) if store_dir else _DEFAULT_STORE
        self._tasks_dir = self.store_dir / "tasks"
        self._graphs_dir = self.store_dir / "graphs"
        self._manifest_path = self.store_dir / self.MANIFEST_FILE
        self._ensure_dirs()

    # ---------------------------------------------------------------- Tasks

    def save_task(self, task: TaskGraph) -> Path:
        """Persist *task* to disk.  Returns the path written."""
        path = self._tasks_dir / f"{task.task_id}.json"
        _write_json(path, task.to_dict())
        self._update_manifest_task(task)
        return path

    def load_task(self, task_id: str) -> Optional[TaskGraph]:
        """Load a :class:`~openshell_evidence.task_graph.TaskGraph` by ID."""
        path = self._tasks_dir / f"{task_id}.json"
        if not path.exists():
            return None
        return TaskGraph.from_dict(_read_json(path))

    def delete_task(self, task_id: str) -> bool:
        """Delete a persisted task.  Returns ``True`` if it existed."""
        path = self._tasks_dir / f"{task_id}.json"
        if path.exists():
            path.unlink()
            self._remove_from_manifest_task(task_id)
            return True
        return False

    def list_tasks(self) -> List[Dict[str, Any]]:
        """Return lightweight metadata for all stored tasks."""
        manifest = self._load_manifest()
        return manifest.get("tasks", [])

    # ---------------------------------------------------------------- Raw graphs

    def save_graph(self, graph: KnowledgeGraph) -> Path:
        """Persist a raw :class:`~openshell_evidence.knowledge_graph.KnowledgeGraph`."""
        path = self._graphs_dir / f"{graph.id}.json"
        _write_json(path, graph.to_dict())
        return path

    def load_graph(self, graph_id: str) -> Optional[KnowledgeGraph]:
        """Load a raw :class:`~openshell_evidence.knowledge_graph.KnowledgeGraph`."""
        path = self._graphs_dir / f"{graph_id}.json"
        if not path.exists():
            return None
        return KnowledgeGraph.from_dict(_read_json(path))

    # ---------------------------------------------------------------- Global graph

    def build_global_graph(self) -> KnowledgeGraph:
        """
        Build a global knowledge graph by merging all persisted task graphs.

        This is the shared memory space that represents the cumulative
        knowledge of all tasks performed by all agents.
        """
        global_graph = KnowledgeGraph(name="global-evidence-graph")
        for entry in self.list_tasks():
            task = self.load_task(entry["task_id"])
            if task is not None:
                global_graph.merge(task.graph)
        return global_graph

    # ---------------------------------------------------------------- Internals

    def _ensure_dirs(self) -> None:
        self._tasks_dir.mkdir(parents=True, exist_ok=True)
        self._graphs_dir.mkdir(parents=True, exist_ok=True)
        if not self._manifest_path.exists():
            _write_json(self._manifest_path, {"tasks": [], "version": 1})

    def _load_manifest(self) -> Dict[str, Any]:
        return _read_json(self._manifest_path)

    def _update_manifest_task(self, task: TaskGraph) -> None:
        manifest = self._load_manifest()
        tasks: List[Dict[str, Any]] = manifest.setdefault("tasks", [])
        entry = self._task_manifest_entry(task)
        for existing in tasks:
            if existing["task_id"] == task.task_id:
                existing.update(entry)
                break
        else:
            tasks.append(entry)
        _write_json(self._manifest_path, manifest)

    def _remove_from_manifest_task(self, task_id: str) -> None:
        manifest = self._load_manifest()
        manifest["tasks"] = [
            t for t in manifest.get("tasks", []) if t["task_id"] != task_id
        ]
        _write_json(self._manifest_path, manifest)

    @staticmethod
    def _task_manifest_entry(task: TaskGraph) -> Dict[str, Any]:
        return {
            "task_id": task.task_id,
            "task_name": task.task_name,
            "status": task.status,
            "created_at": task.created_at,
            "updated_at": task.updated_at,
        }

    def __repr__(self) -> str:
        return f"EvidenceStore(store_dir={str(self.store_dir)!r})"


# -------------------------------------------------------------------- Helpers

def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)


def _read_json(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)
