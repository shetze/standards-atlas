"""Lifecycle management for the project-owned MCP HTTP server."""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from standards_atlas.adapters.mcp.configuration import McpServerConfig


class McpServerProcessError(RuntimeError):
    """Raised when the managed MCP server cannot be controlled."""


@dataclass(frozen=True)
class McpServerProcessStatus:
    """Current state of the managed MCP server process."""

    running: bool
    pid: int | None = None
    detail: str | None = None


class McpServerProcessManager:
    """Start, monitor, and stop the MCP HTTP server as a background process."""

    def __init__(self, config: McpServerConfig, config_path: Path) -> None:
        self._config = config
        self._config_path = config_path.resolve()

    def status(self) -> McpServerProcessStatus:
        self._require_http_transport()
        pid = self._read_pid()
        if pid is None:
            return McpServerProcessStatus(False, detail="no managed MCP process")
        if not self._pid_is_running(pid):
            self._config.process.pid_file.unlink(missing_ok=True)
            return McpServerProcessStatus(False, detail=f"stale PID file for process {pid}")
        if self._endpoint_available():
            return McpServerProcessStatus(True, pid, "MCP endpoint is available")
        return McpServerProcessStatus(
            False,
            pid,
            "MCP process is running but the configured endpoint is unavailable",
        )

    def start(self) -> None:
        self._require_http_transport()
        status = self.status()
        if status.running:
            return
        if status.pid is not None:
            raise McpServerProcessError(status.detail or "MCP process is not healthy")

        process_config = self._config.process
        process_config.state_directory.mkdir(parents=True, exist_ok=True)
        process_config.log_file.parent.mkdir(parents=True, exist_ok=True)
        command = (
            sys.executable,
            "-m",
            "standards_atlas",
            "mcp",
            "serve",
            "--config",
            str(self._config_path),
        )
        try:
            with process_config.log_file.open("ab") as log:
                process = subprocess.Popen(  # noqa: S603
                    command,
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
        except OSError as exc:
            raise McpServerProcessError(f"Could not start MCP server: {exc}") from exc

        process_config.pid_file.write_text(f"{process.pid}\n", encoding="utf-8")
        try:
            self._wait_until_available(process.pid)
        except McpServerProcessError:
            self._terminate_process(process.pid)
            process_config.pid_file.unlink(missing_ok=True)
            raise

    def stop(self) -> None:
        self._require_http_transport()
        pid = self._read_pid()
        if pid is None or not self._pid_is_running(pid):
            self._config.process.pid_file.unlink(missing_ok=True)
            return
        self._terminate_process(pid)
        self._wait_for_process_exit(pid)
        self._config.process.pid_file.unlink(missing_ok=True)

    @contextmanager
    def ensure_running(
        self,
        *,
        autostart: bool = True,
        autostop: bool = True,
    ) -> Iterator[McpServerProcessStatus]:
        """Keep the MCP server available and preserve process ownership."""
        status = self.status()
        started_here = False
        if not status.running:
            if not autostart:
                raise McpServerProcessError(
                    "Codex requires a running MCP server; automatic start is disabled"
                )
            self.start()
            started_here = True
            status = self.status()
            if not status.running:
                raise McpServerProcessError(
                    status.detail or "MCP server is unavailable after startup"
                )
        try:
            yield status
        finally:
            if started_here and autostop:
                self.stop()

    def _wait_until_available(self, pid: int) -> None:
        timeout = self._config.process.startup_timeout_seconds
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not self._pid_is_running(pid):
                detail = self._tail_log()
                suffix = f"\nMCP log:\n{detail}" if detail else ""
                raise McpServerProcessError(f"MCP process {pid} exited during startup{suffix}")
            if self._endpoint_available():
                return
            time.sleep(0.25)
        detail = self._tail_log()
        suffix = f"\nMCP log:\n{detail}" if detail else ""
        raise McpServerProcessError(f"MCP server did not start within {timeout:g} seconds{suffix}")

    def _wait_for_process_exit(self, pid: int) -> None:
        timeout = self._config.process.shutdown_timeout_seconds
        if self._wait_until_process_stopped(pid, timeout):
            return
        try:
            os.killpg(pid, signal.SIGKILL)
        except ProcessLookupError:
            return
        except OSError:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                return

        kill_timeout = min(max(timeout / 2, 1.0), 5.0)
        if self._wait_until_process_stopped(pid, kill_timeout):
            return
        raise McpServerProcessError(f"MCP process {pid} did not stop within {timeout:g} seconds")

    def _wait_until_process_stopped(self, pid: int, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not self._pid_is_running(pid):
                return True
            time.sleep(0.25)
        return not self._pid_is_running(pid)

    def _endpoint_available(self) -> bool:
        host = self._config.http.host
        if host in {"0.0.0.0", "::"}:
            host = "127.0.0.1"
        try:
            with socket.create_connection(
                (host, self._config.http.port),
                timeout=self._config.process.health_timeout_seconds,
            ):
                return True
        except OSError:
            return False

    def _read_pid(self) -> int | None:
        try:
            return int(self._config.process.pid_file.read_text(encoding="utf-8").strip())
        except (FileNotFoundError, ValueError):
            return None

    @staticmethod
    def _pid_is_running(pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True

        stat_path = Path(f"/proc/{pid}/stat")
        try:
            fields = stat_path.read_text(encoding="utf-8").split()
        except (FileNotFoundError, PermissionError, OSError):
            return True
        return len(fields) < 3 or fields[2] != "Z"

    @staticmethod
    def _terminate_process(pid: int) -> None:
        try:
            os.killpg(pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        except OSError:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                return

    def _tail_log(self, line_count: int = 20) -> str | None:
        try:
            lines = self._config.process.log_file.read_text(
                encoding="utf-8", errors="replace"
            ).splitlines()
        except FileNotFoundError:
            return None
        return "\n".join(lines[-line_count:]) or None

    def _require_http_transport(self) -> None:
        if self._config.transport != "streamable-http":
            raise McpServerProcessError(
                "managed background operation requires MCP transport 'streamable-http'"
            )
