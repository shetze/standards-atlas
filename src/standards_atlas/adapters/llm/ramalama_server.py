"""Lifecycle management for the project-owned RamaLama inference server."""

from __future__ import annotations

import subprocess
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator
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
        health = OpenAICompatibleLlmGateway(self._config).health()
        return RamaLamaServerStatus(health.available, health.detail)

    def start(self) -> None:
        if not self._config.server.enabled or self.status().running:
            return
        server = self._config.server
        command = (
            server.executable,
            "serve",
            "--detach",
            "--name",
            server.name,
            "--port",
            str(self._port()),
            "--runtime",
            server.runtime.value,
            "--webui",
            "off",
            server.model,
        )
        self._run(command, "start")
        self._wait_for(running=True, timeout=server.startup_timeout_seconds)

    def stop(self) -> None:
        if not self._config.server.enabled or not self.status().running:
            return
        server = self._config.server
        self._run((server.executable, "stop", server.name), "stop")
        self._wait_for(running=False, timeout=server.shutdown_timeout_seconds)

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

    def _port(self) -> int:
        parsed = urlparse(self._config.base_url)
        if parsed.scheme not in {"http", "https"} or parsed.hostname not in {
            "127.0.0.1",
            "localhost",
            "::1",
        }:
            raise RamaLamaServerError(
                "managed RamaLama requires a loopback llm.base_url"
            )
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
        raise RamaLamaServerError(
            f"RamaLama server did not {state} within {timeout:g} seconds"
        )

    @staticmethod
    def _run(command: tuple[str, ...], action: str) -> None:
        try:
            subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError as exc:
            raise RamaLamaServerError(
                f"RamaLama executable not found: {command[0]}"
            ) from exc
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or exc.stdout or "").strip()
            suffix = f": {detail}" if detail else ""
            raise RamaLamaServerError(f"Could not {action} RamaLama server{suffix}") from exc
