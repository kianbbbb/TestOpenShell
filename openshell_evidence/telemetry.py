"""
Telemetry module for capturing OpenShell agent execution events.

Telemetry spans trace the execution of tasks and commands, recording
timing, attributes, and outcomes.  Spans can be nested to represent
hierarchical operations, and are linked to knowledge graph nodes so
evidence can be queried through the graph.
"""

import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class TelemetrySpan:
    """A single telemetry span representing a bounded unit of work."""

    STATUS_OK = "OK"
    STATUS_ERROR = "ERROR"
    STATUS_IN_PROGRESS = "IN_PROGRESS"

    def __init__(
        self,
        name: str,
        span_id: Optional[str] = None,
        parent_id: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> None:
        self.id = span_id or str(uuid.uuid4())
        self.trace_id = trace_id or str(uuid.uuid4())
        self.parent_id = parent_id
        self.name = name
        self.status = self.STATUS_IN_PROGRESS
        self.attributes: Dict[str, Any] = {}
        self.events: List[Dict[str, Any]] = []
        self._start_time = time.monotonic()
        self.start_timestamp = datetime.now(timezone.utc).isoformat()
        self.end_timestamp: Optional[str] = None
        self.duration_ms: Optional[float] = None

    def set_attribute(self, key: str, value: Any) -> None:
        """Attach an attribute key/value pair to this span."""
        self.attributes[key] = value

    def add_event(
        self, name: str, attributes: Optional[Dict[str, Any]] = None
    ) -> None:
        """Record a named event within this span."""
        self.events.append(
            {
                "name": name,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "attributes": attributes or {},
            }
        )

    def end(self, status: str = STATUS_OK) -> None:
        """Close the span and compute its duration."""
        self.duration_ms = (time.monotonic() - self._start_time) * 1000
        self.end_timestamp = datetime.now(timezone.utc).isoformat()
        self.status = status

    @property
    def is_finished(self) -> bool:
        return self.end_timestamp is not None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "trace_id": self.trace_id,
            "parent_id": self.parent_id,
            "name": self.name,
            "status": self.status,
            "attributes": self.attributes,
            "events": self.events,
            "start_timestamp": self.start_timestamp,
            "end_timestamp": self.end_timestamp,
            "duration_ms": self.duration_ms,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TelemetrySpan":
        span = cls(
            name=data["name"],
            span_id=data["id"],
            parent_id=data.get("parent_id"),
            trace_id=data.get("trace_id"),
        )
        span.status = data.get("status", cls.STATUS_IN_PROGRESS)
        span.attributes = data.get("attributes", {})
        span.events = data.get("events", [])
        span.start_timestamp = data.get("start_timestamp", span.start_timestamp)
        span.end_timestamp = data.get("end_timestamp")
        span.duration_ms = data.get("duration_ms")
        return span

    def __repr__(self) -> str:
        return f"TelemetrySpan(id={self.id!r}, name={self.name!r}, status={self.status!r})"


class TelemetryCollector:
    """
    Collects and stores telemetry spans for agent task execution.

    Spans can be nested (parent/child) to represent hierarchical operations.
    All spans are retained in memory and can be exported to a list of dicts
    for integration with the knowledge graph or external systems.
    """

    def __init__(self, trace_id: Optional[str] = None) -> None:
        self.trace_id = trace_id or str(uuid.uuid4())
        self._spans: Dict[str, TelemetrySpan] = {}
        self._root_span_ids: List[str] = []

    def start_span(
        self, name: str, parent_id: Optional[str] = None
    ) -> TelemetrySpan:
        """Start a new span, optionally as a child of an existing span."""
        span = TelemetrySpan(
            name=name,
            parent_id=parent_id,
            trace_id=self.trace_id,
        )
        self._spans[span.id] = span
        if parent_id is None:
            self._root_span_ids.append(span.id)
        return span

    def end_span(
        self, span_id: str, status: str = TelemetrySpan.STATUS_OK
    ) -> Optional[TelemetrySpan]:
        """End a span by ID."""
        span = self._spans.get(span_id)
        if span and not span.is_finished:
            span.end(status)
        return span

    def get_span(self, span_id: str) -> Optional[TelemetrySpan]:
        return self._spans.get(span_id)

    def all_spans(self) -> List[TelemetrySpan]:
        return list(self._spans.values())

    def root_spans(self) -> List[TelemetrySpan]:
        """Return spans with no parent."""
        return [
            self._spans[sid]
            for sid in self._root_span_ids
            if sid in self._spans
        ]

    def children_of(self, span_id: str) -> List[TelemetrySpan]:
        """Return all direct child spans of the given span."""
        return [s for s in self._spans.values() if s.parent_id == span_id]

    def export(self) -> List[Dict[str, Any]]:
        """Export all spans as a list of dicts."""
        return [s.to_dict() for s in self._spans.values()]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "spans": self.export(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TelemetryCollector":
        collector = cls(trace_id=data.get("trace_id"))
        for span_data in data.get("spans", []):
            span = TelemetrySpan.from_dict(span_data)
            collector._spans[span.id] = span
            if span.parent_id is None:
                collector._root_span_ids.append(span.id)
        return collector

    def __repr__(self) -> str:
        return (
            f"TelemetryCollector(trace_id={self.trace_id!r}, "
            f"spans={len(self._spans)})"
        )
