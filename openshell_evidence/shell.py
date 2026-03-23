"""
OpenShell – constrained shell executor for AI agents.

The shell wrapper executes commands in a controlled environment, captures
all output (stdout, stderr, exit code, timing), and emits telemetry spans
for each command.  Allowed commands can be restricted via an optional
allow-list.
"""

import shlex
import subprocess
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .telemetry import TelemetryCollector, TelemetrySpan


class CommandResult:
    """The result of a single shell command execution."""

    def __init__(
        self,
        command: str,
        stdout: str,
        stderr: str,
        exit_code: int,
        duration_ms: float,
        timestamp: str,
        span_id: Optional[str] = None,
    ) -> None:
        self.command = command
        self.stdout = stdout
        self.stderr = stderr
        self.exit_code = exit_code
        self.duration_ms = duration_ms
        self.timestamp = timestamp
        self.span_id = span_id

    @property
    def success(self) -> bool:
        return self.exit_code == 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "command": self.command,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "duration_ms": self.duration_ms,
            "timestamp": self.timestamp,
            "span_id": self.span_id,
            "success": self.success,
        }

    def __repr__(self) -> str:
        return (
            f"CommandResult(command={self.command!r}, "
            f"exit_code={self.exit_code}, success={self.success})"
        )


class OpenShell:
    """
    A constrained shell executor that wraps subprocess execution with
    telemetry capture and optional command allow-listing.

    Parameters
    ----------
    allowed_commands:
        If provided, only commands whose base name appears in this list will
        be executed.  Pass ``None`` (default) to allow all commands.
    working_dir:
        Working directory for command execution.  Defaults to the current
        directory when ``None``.
    timeout:
        Maximum time in seconds for a single command.  Defaults to 30.
    telemetry:
        An existing :class:`TelemetryCollector` to append spans to.  A fresh
        collector is created when not provided.
    """

    def __init__(
        self,
        allowed_commands: Optional[List[str]] = None,
        working_dir: Optional[str] = None,
        timeout: int = 30,
        telemetry: Optional[TelemetryCollector] = None,
    ) -> None:
        self.allowed_commands = allowed_commands
        self.working_dir = working_dir
        self.timeout = timeout
        self.telemetry = telemetry or TelemetryCollector()
        self._history: List[CommandResult] = []

    # ------------------------------------------------------------------

    def run(
        self,
        command: str,
        parent_span_id: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> CommandResult:
        """
        Execute *command* in the constrained shell and return a
        :class:`CommandResult`.

        Raises
        ------
        PermissionError
            If *command*'s base name is not in the allow-list.
        """
        args = shlex.split(command) if command.strip() else []
        base = args[0] if args else ""

        if self.allowed_commands is not None and base not in self.allowed_commands:
            raise PermissionError(
                f"Command {base!r} is not in the allowed commands list: "
                f"{self.allowed_commands}"
            )

        span = self.telemetry.start_span(
            f"shell.run:{base}", parent_id=parent_span_id
        )
        span.set_attribute("command", command)
        span.set_attribute("working_dir", self.working_dir or "")

        start = time.monotonic()
        timestamp = datetime.now(timezone.utc).isoformat()
        stdout = ""
        stderr = ""
        exit_code = -1
        try:
            proc = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=self.working_dir,
                env=env,
            )
            stdout = proc.stdout
            stderr = proc.stderr
            exit_code = proc.returncode
        except subprocess.TimeoutExpired:
            stderr = f"Command timed out after {self.timeout}s"
            exit_code = -1
        except Exception as exc:  # pragma: no cover – OS-level errors
            stderr = str(exc)
            exit_code = -1
        finally:
            duration_ms = (time.monotonic() - start) * 1000

        status = (
            TelemetrySpan.STATUS_OK
            if exit_code == 0
            else TelemetrySpan.STATUS_ERROR
        )
        span.set_attribute("exit_code", exit_code)
        span.set_attribute("stdout", stdout)
        span.set_attribute("stderr", stderr)
        span.set_attribute("duration_ms", duration_ms)
        self.telemetry.end_span(span.id, status=status)

        result = CommandResult(
            command=command,
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            duration_ms=duration_ms,
            timestamp=timestamp,
            span_id=span.id,
        )
        self._history.append(result)
        return result

    def history(self) -> List[CommandResult]:
        """Return the ordered list of all executed commands."""
        return list(self._history)

    def last_result(self) -> Optional[CommandResult]:
        """Return the most recent command result, or ``None``."""
        return self._history[-1] if self._history else None

    def __repr__(self) -> str:
        return (
            f"OpenShell(allowed_commands={self.allowed_commands!r}, "
            f"working_dir={self.working_dir!r}, timeout={self.timeout})"
        )
