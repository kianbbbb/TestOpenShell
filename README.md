# TestOpenShell – Evidence Capture System

A Python package that captures evidence of AI agent task execution using
**OpenShell** as the constrained shell executor. All execution evidence is
stored in a **knowledge graph**, providing a shared memory space that persists
across sessions and enables agents to understand the state of previous tasks.

---

## Architecture

```
openshell_evidence/
├── knowledge_graph.py   # Core directed knowledge graph (Node, Edge, KnowledgeGraph)
├── telemetry.py         # Span-based telemetry (TelemetrySpan, TelemetryCollector)
├── shell.py             # Constrained shell executor (OpenShell, CommandResult)
├── task_graph.py        # Per-task evidence sub-graph (TaskGraph)
├── persistence.py       # File-backed evidence store (EvidenceStore)
└── agent.py             # High-level agent interface (Agent)
```

### Key components

| Component | Role |
|---|---|
| `KnowledgeGraph` | Shared memory space; directed graph of nodes and edges |
| `TaskGraph` | Per-task sub-graph anchored to a root Task node |
| `OpenShell` | Constrained shell executor with optional command allow-list |
| `TelemetryCollector` | Span-based telemetry that records execution timing and attributes |
| `EvidenceStore` | JSON file-backed persistence; builds a global graph by merging all tasks |
| `Agent` | High-level interface tying shell, evidence graph, and store together |

---

## Quick start

```python
from openshell_evidence import Agent

# Create an agent with a custom store directory
agent = Agent(
    name="my-agent",
    store_dir="/tmp/evidence",
    # Optionally restrict allowed commands:
    # allowed_commands=["echo", "ls", "cat", "python3"],
)

# Start a task – creates a fresh TaskGraph and OpenShell instance
task = agent.begin_task(
    task_name="Check server health",
    description="Verify that the API server is running and responding",
)

# Run commands – output is captured automatically in the task graph
result = agent.run("echo 'Starting health check'")
result = agent.run("curl -s http://localhost:8080/health || echo 'unreachable'")

# Add arbitrary evidence (decisions, observations, etc.)
agent.add_evidence(
    evidence_type="observation",
    content="API server returned HTTP 200",
    properties={"endpoint": "/health"},
)

# Record file artefacts produced by the task
agent.add_artifact("health_report.txt", "/tmp/health_report.txt", "report")

# Finish the task
agent.end_task(success=True)

# --- Spawn a sub-task ---
task = agent.begin_task("Deploy update")
child_agent = agent.spawn_subtask(
    "Run migrations",
    description="Apply pending database migrations",
)
child_agent.run("echo 'Applying migrations...'")
child_agent.end_task()
agent.end_task()

# --- Resume a paused task ---
resumed_task = agent.resume_task(task.task_id)

# --- Query the global knowledge graph ---
# Merges all persisted task graphs into one shared memory space
global_graph = agent.global_graph()
print(f"Global graph: {len(global_graph)} nodes, {len(global_graph.all_edges())} edges")
```

---

## Evidence model

Every task execution populates a `TaskGraph` with nodes of the following types:

| Node type | Description |
|---|---|
| `task` | Root node for each task (and references to sub-tasks) |
| `agent` | The agent performing the task |
| `command` | A shell command that was executed |
| `output` | stdout or stderr captured from a command |
| `evidence` | Arbitrary evidence added by the agent |
| `artifact` | File artefact produced or consumed |

Edges connect these nodes using named relations:
`HAS_COMMAND`, `PRODUCED`, `FOLLOWS`, `DELEGATED_TO`, `HAS_EVIDENCE`,
`DEPENDS_ON`, `SPAWNED`.

---

## Persistence

Task graphs are stored as JSON files under the evidence store directory
(default `~/.openshell/evidence_store`):

```
evidence_store/
├── manifest.json          # Index of all stored tasks
├── tasks/<task_id>.json   # One file per TaskGraph
└── graphs/<graph_id>.json # Raw KnowledgeGraph files
```

Use `EvidenceStore.build_global_graph()` to merge all stored task graphs into
a single knowledge graph representing the cumulative memory of all agents.

---

## Running the tests

```bash
pip install pytest pytest-cov
pytest tests/ -v
```
