"""Tests for openshell_evidence.shell."""

import pytest

from openshell_evidence.shell import CommandResult, OpenShell
from openshell_evidence.telemetry import TelemetrySpan


class TestCommandResult:
    def _make(self, exit_code=0, stdout="out", stderr=""):
        return CommandResult(
            command="echo hi",
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            duration_ms=5.0,
            timestamp="2024-01-01T00:00:00+00:00",
            span_id="s1",
        )

    def test_success_true_when_exit_0(self):
        assert self._make(exit_code=0).success is True

    def test_success_false_when_nonzero(self):
        assert self._make(exit_code=1).success is False

    def test_to_dict_keys(self):
        d = self._make().to_dict()
        for key in [
            "command", "stdout", "stderr", "exit_code",
            "duration_ms", "timestamp", "span_id", "success",
        ]:
            assert key in d

    def test_repr(self):
        r = repr(self._make())
        assert "echo hi" in r


class TestOpenShell:
    def test_run_echo(self):
        shell = OpenShell()
        result = shell.run("echo hello")
        assert result.success
        assert "hello" in result.stdout

    def test_run_failing_command(self):
        shell = OpenShell()
        result = shell.run("exit 1", )
        # 'exit 1' in a subshell returns exit_code=1
        assert not result.success
        assert result.exit_code == 1

    def test_run_captures_stderr(self):
        shell = OpenShell()
        result = shell.run("echo err >&2")
        assert "err" in result.stderr

    def test_history_grows(self):
        shell = OpenShell()
        shell.run("echo a")
        shell.run("echo b")
        assert len(shell.history()) == 2

    def test_last_result(self):
        shell = OpenShell()
        shell.run("echo a")
        r = shell.run("echo b")
        assert shell.last_result() is r

    def test_last_result_none_when_empty(self):
        shell = OpenShell()
        assert shell.last_result() is None

    def test_allow_list_permits_allowed(self):
        shell = OpenShell(allowed_commands=["echo"])
        result = shell.run("echo ok")
        assert result.success

    def test_allow_list_blocks_disallowed(self):
        shell = OpenShell(allowed_commands=["echo"])
        with pytest.raises(PermissionError):
            shell.run("ls")

    def test_empty_command_allowed_when_no_list(self):
        # Should not raise even for empty string
        shell = OpenShell()
        result = shell.run("")
        # Empty command – exit code may be 0 or nonzero depending on shell
        assert isinstance(result.exit_code, int)

    def test_telemetry_span_recorded(self):
        shell = OpenShell()
        result = shell.run("echo hi")
        span = shell.telemetry.get_span(result.span_id)
        assert span is not None
        assert span.is_finished

    def test_telemetry_span_status_ok_on_success(self):
        shell = OpenShell()
        result = shell.run("echo hi")
        span = shell.telemetry.get_span(result.span_id)
        assert span.status == TelemetrySpan.STATUS_OK

    def test_telemetry_span_status_error_on_failure(self):
        shell = OpenShell()
        result = shell.run("exit 1")
        span = shell.telemetry.get_span(result.span_id)
        assert span.status == TelemetrySpan.STATUS_ERROR

    def test_telemetry_span_has_command_attribute(self):
        shell = OpenShell()
        result = shell.run("echo hi")
        span = shell.telemetry.get_span(result.span_id)
        assert span.attributes["command"] == "echo hi"

    def test_repr(self):
        shell = OpenShell(allowed_commands=["echo"])
        assert "OpenShell" in repr(shell)
