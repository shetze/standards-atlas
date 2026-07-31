"""Lifecycle management for the project-owned RamaLama inference server."""

from __future__ import annotations

import os
import signal
import subprocess
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from standards_atlas.adapters.llm.config import LlmConfig
from standards_atlas.adapters.llm.openai_compatible import OpenAICompatibleLlmGateway


class RamaLamaServerError(RuntimeError):
    """Raised when the managed RamaLama server cannot be controlled."""


@dataclass(frozen=True)
class RamaLamaServerStatus:
    """Current availability of the managed server."""

    running: bool
    detail: str | None = None


class RamaLamaServerManager:
    """Start, stop, and temporarily pause the project-owned RamaLama server."""

    def __init__(self, config: LlmConfig) -> None:
        self._config = config

    def status(self) -> RamaLamaServerStatus:
        if not self._config.server.enabled:
            return RamaLamaServerStatus(False, "managed server is disabled")

        pid = self._read_pid()
        process_running = pid is not None and self._pid_is_running(pid)
        health = OpenAICompatibleLlmGateway(self._config).health()

        if health.available:
            return RamaLamaServerStatus(True, health.detail)
        if process_running:
            return RamaLamaServerStatus(
                False,
                health.detail or f"RamaLama process {pid} is running but endpoint is unavailable",
            )
        return RamaLamaServerStatus(False, health.detail)

    def start(self) -> None:
        if not self._config.server.enabled or self.status().running:
            return

        server = self._config.server
        state_directory = server.state_directory
        state_directory.mkdir(parents=True, exist_ok=True)
        command = (
            server.executable,
            "serve",
            "--name",
            server.name,
            "--backend",
            server.backend,
            f"--selinux={str(server.selinux).lower()}",
            "--port",
            str(self._port()),
            server.model,
        )

        try:
            log = server.log_file.open("ab")
            process = subprocess.Popen(  # noqa: S603
                command,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        except FileNotFoundError as exc:
            raise RamaLamaServerError(
                f"RamaLama executable not found: {server.executable}"
            ) from exc
        except OSError as exc:
            raise RamaLamaServerError(f"Could not start RamaLama server: {exc}") from exc
        finally:
            if "log" in locals():
                log.close()

        server.pid_file.write_text(f"{process.pid}\n", encoding="utf-8")
        try:
            self._wait_for(running=True, timeout=server.startup_timeout_seconds)
        except RamaLamaServerError:
            self._terminate_process(process.pid)
            server.pid_file.unlink(missing_ok=True)
            raise

    def pull(self, model: str | None = None) -> None:
        """Download one model into RamaLama local storage without starting it."""
        model_ref = model or self._config.server.model
        if not model_ref.strip():
            raise RamaLamaServerError("RamaLama model reference must not be empty")
        try:
            subprocess.run(  # noqa: S603
                (self._config.server.executable, "pull", model_ref),
                check=True,
            )
        except FileNotFoundError as exc:
            raise RamaLamaServerError(
                f"RamaLama executable not found: {self._config.server.executable}"
            ) from exc
        except subprocess.CalledProcessError as exc:
            raise RamaLamaServerError(
                f"Could not preload RamaLama model {model_ref!r}: exit code {exc.returncode}"
            ) from exc
        except OSError as exc:
            raise RamaLamaServerError(
                f"Could not preload RamaLama model {model_ref!r}: {exc}"
            ) from exc

    def stop(self) -> None:
        if not self._config.server.enabled:
            return

        pid = self._read_pid()
        if pid is None or not self._pid_is_running(pid):
            self._config.server.pid_file.unlink(missing_ok=True)
            return

        try:
            self._terminate_process(pid)
            try:
                self._wait_for_process_exit(pid, self._config.server.shutdown_timeout_seconds)
            except RamaLamaServerError:
                self._stop_named_container()
                if self._wait_until_process_stopped(pid, 5.0):
                    return
                raise
        finally:
            self._config.server.pid_file.unlink(missing_ok=True)

    @contextmanager
    def paused_for_exclusive_accelerator(self) -> Iterator[None]:
        """Pause a running server and restore it after an exclusive GPU workload."""
        was_running = self.status().running
        if was_running:
            self.stop()
        try:
            yield
        finally:
            if was_running:
                self.start()

    @contextmanager
    def stopped_for_exclusive_accelerator(self) -> Iterator[None]:
        """Stop a running server and leave it stopped after an exclusive GPU workload."""
        if self.status().running:
            self.stop()
        yield

    def _port(self) -> int:
        parsed = urlparse(self._config.base_url)
        if parsed.scheme not in {"http", "https"} or parsed.hostname not in {
            "127.0.0.1",
            "localhost",
            "::1",
        }:
            raise RamaLamaServerError("managed RamaLama requires a loopback llm.base_url")
        if parsed.port is not None:
            return parsed.port
        return 443 if parsed.scheme == "https" else 80

    def _wait_for(self, *, running: bool, timeout: float) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.status().running is running:
                return
            time.sleep(0.25)
        state = "start" if running else "stop"
        detail = self._tail_log() if running else None
        suffix = f"\nRamaLama log:\n{detail}" if detail else ""
        raise RamaLamaServerError(
            f"RamaLama server did not {state} within {timeout:g} seconds{suffix}"
        )

    def _read_pid(self) -> int | None:
        try:
            return int(self._config.server.pid_file.read_text(encoding="utf-8").strip())
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

    def _stop_named_container(self) -> None:
        try:
            subprocess.run(  # noqa: S603
                (
                    self._config.server.executable,
                    "stop",
                    self._config.server.name,
                ),
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10.0,
            )
        except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
            return

    def _wait_for_process_exit(self, pid: int, timeout: float) -> None:
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
        raise RamaLamaServerError(f"RamaLama process {pid} did not stop within {timeout:g} seconds")

    def _wait_until_process_stopped(self, pid: int, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not self._pid_is_running(pid):
                return True
            time.sleep(0.25)
        return not self._pid_is_running(pid)

    def _tail_log(self, line_count: int = 20) -> str | None:
        try:
            lines = self._config.server.log_file.read_text(
                encoding="utf-8", errors="replace"
            ).splitlines()
        except FileNotFoundError:
            return None
        return "\n".join(lines[-line_count:]) or None
