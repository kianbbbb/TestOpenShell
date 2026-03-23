"""Tests for openshell_evidence.telemetry."""

import time

import pytest

from openshell_evidence.telemetry import TelemetryCollector, TelemetrySpan


class TestTelemetrySpan:
    def test_initial_status_in_progress(self):
        span = TelemetrySpan(name="test")
        assert span.status == TelemetrySpan.STATUS_IN_PROGRESS

    def test_is_finished_false_before_end(self):
        span = TelemetrySpan(name="test")
        assert not span.is_finished

    def test_end_sets_status(self):
        span = TelemetrySpan(name="test")
        span.end(TelemetrySpan.STATUS_OK)
        assert span.status == TelemetrySpan.STATUS_OK
        assert span.is_finished

    def test_end_records_duration(self):
        span = TelemetrySpan(name="test")
        time.sleep(0.01)
        span.end()
        assert span.duration_ms is not None
        assert span.duration_ms >= 0

    def test_set_attribute(self):
        span = TelemetrySpan(name="test")
        span.set_attribute("key", "value")
        assert span.attributes["key"] == "value"

    def test_add_event(self):
        span = TelemetrySpan(name="test")
        span.add_event("my_event", {"x": 1})
        assert len(span.events) == 1
        assert span.events[0]["name"] == "my_event"
        assert span.events[0]["attributes"] == {"x": 1}

    def test_add_event_no_attributes(self):
        span = TelemetrySpan(name="test")
        span.add_event("plain")
        assert span.events[0]["attributes"] == {}

    def test_round_trip(self):
        span = TelemetrySpan(
            name="cmd", span_id="s1", parent_id="p1", trace_id="t1"
        )
        span.set_attribute("cmd", "echo hi")
        span.add_event("started")
        span.end(TelemetrySpan.STATUS_OK)

        restored = TelemetrySpan.from_dict(span.to_dict())
        assert restored.id == "s1"
        assert restored.parent_id == "p1"
        assert restored.trace_id == "t1"
        assert restored.status == TelemetrySpan.STATUS_OK
        assert restored.attributes["cmd"] == "echo hi"
        assert len(restored.events) == 1
        assert restored.duration_ms == span.duration_ms

    def test_repr(self):
        span = TelemetrySpan(name="test")
        assert "test" in repr(span)


class TestTelemetryCollector:
    def test_start_span_adds_to_store(self):
        collector = TelemetryCollector()
        span = collector.start_span("test")
        assert collector.get_span(span.id) is span

    def test_root_span_tracked(self):
        collector = TelemetryCollector()
        span = collector.start_span("root")
        assert span in collector.root_spans()

    def test_child_span_not_root(self):
        collector = TelemetryCollector()
        root = collector.start_span("root")
        child = collector.start_span("child", parent_id=root.id)
        assert child not in collector.root_spans()

    def test_children_of(self):
        collector = TelemetryCollector()
        root = collector.start_span("root")
        c1 = collector.start_span("c1", parent_id=root.id)
        c2 = collector.start_span("c2", parent_id=root.id)
        children = collector.children_of(root.id)
        assert c1 in children
        assert c2 in children

    def test_end_span(self):
        collector = TelemetryCollector()
        span = collector.start_span("test")
        collector.end_span(span.id, status=TelemetrySpan.STATUS_OK)
        assert span.is_finished
        assert span.status == TelemetrySpan.STATUS_OK

    def test_end_already_finished_span_is_noop(self):
        collector = TelemetryCollector()
        span = collector.start_span("test")
        span.end(TelemetrySpan.STATUS_OK)
        # Calling end_span again should not raise
        collector.end_span(span.id, status=TelemetrySpan.STATUS_ERROR)
        # Status should remain OK (first close wins)
        assert span.status == TelemetrySpan.STATUS_OK

    def test_end_missing_span_returns_none(self):
        collector = TelemetryCollector()
        assert collector.end_span("no-such-id") is None

    def test_export_contains_all_spans(self):
        collector = TelemetryCollector()
        collector.start_span("a")
        collector.start_span("b")
        exported = collector.export()
        assert len(exported) == 2

    def test_all_spans(self):
        collector = TelemetryCollector()
        collector.start_span("a")
        collector.start_span("b")
        assert len(collector.all_spans()) == 2

    def test_round_trip(self):
        collector = TelemetryCollector(trace_id="t1")
        s1 = collector.start_span("root")
        s2 = collector.start_span("child", parent_id=s1.id)
        s1.end()
        s2.end()

        restored = TelemetryCollector.from_dict(collector.to_dict())
        assert restored.trace_id == "t1"
        assert len(restored.all_spans()) == 2
        assert restored.get_span(s1.id) is not None
        assert restored.get_span(s2.id) is not None

    def test_repr(self):
        collector = TelemetryCollector()
        assert "TelemetryCollector" in repr(collector)
