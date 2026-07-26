"""Managed RamaLama server lifecycle for local inference."""

from __future__ import annotations

import json
import subprocess
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
from typing import Iterator, Protocol
from urllib.parse import urlparse


class LlmRuntime(StrEnum):
    """Supported local inference runtimes."""

    LLAMA_CPP = "llama.cpp"
    VLLM = "vllm"


@dataclass(frozen=True)
class ManagedLlmServerConfig:
    """Configuration for a RamaLama-managed local model server."""

    enabled: bool = True
    name: str = "standards-atlas-llm"
    model: str = "granite"
    runtime: LlmRuntime = LlmRuntime.LLAMA_CPP
    startup_timeout_seconds: float = 120.0

    def __post_init__(self) -> None:
        if isinstance(self.runtime, str):
            object.__setattr__(self, "runtime", LlmRuntime(self.runtime))
        if not self.name.strip():
            raise ValueError("llm.server.name must not be empty")
        if not self.model.strip():
            raise ValueError("llm.server.model must not be empty")
        if self.startup_timeout_seconds <= 0:
            raise ValueError("llm.server.startup_timeout_seconds must be positive")


class CommandExecutor(Protocol):
    """Minimal subprocess abstraction used by the server controller."""

    def run(self, command: tuple[str, ...]) -> None: ...


class SubprocessCommandExecutor:
    """Execute RamaLama commands using the local process environment."""

    def run(self, command: tuple[str, ...]) -> None:
        subprocess.run(command, check=True)  # noqa: S603


class RamaLamaServerController:
    """Start, stop, and temporarily suspend the project-owned model server."""

    def __init__(
        self,
        *,
        base_url: str,
        config: ManagedLlmServerConfig,
        executor: CommandExecutor | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._config = config
        self._executor = executor or SubprocessCommandExecutor()

    @property
    def managed(self) -> bool:
        return self._config.enabled

    def is_running(self) -> bool:
        """Return whether the configured OpenAI-compatible endpoint responds."""

        if not self.managed:
            return False
        request = urllib.request.Request(
            f"{self._base_url}/models",
            headers={"Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=1.0) as response:  # noqa: S310
                payload = json.loads(response.read().decode("utf-8"))
            return isinstance(payload, dict)
        except (OSError, ValueError, urllib.error.URLError):
            return False

    def start(self) -> None:
        """Start the configured RamaLama service and wait until it is ready."""

        if not self.managed or self.is_running():
            return
        port = _port_from_base_url(self._base_url)
        self._executor.run(
            (
                "ramalama",
                "serve",
                "--detach",
                "--name",
                self._config.name,
                "--port",
                str(port),
                f"--runtime={self._config.runtime.value}",
                self._config.model,
            )
        )
        deadline = time.monotonic() + self._config.startup_timeout_seconds
        while time.monotonic() < deadline:
            if self.is_running():
                return
            time.sleep(0.5)
        raise TimeoutError(
            f"RamaLama server {self._config.name!r} did not become ready at "
            f"{self._base_url}"
        )

    def stop(self) -> None:
        """Stop the project-owned RamaLama service."""

        if not self.managed:
            return
        self._executor.run(("ramalama", "stop", "--ignore", self._config.name))
        deadline = time.monotonic() + self._config.startup_timeout_seconds
        while time.monotonic() < deadline:
            if not self.is_running():
                return
            time.sleep(0.25)
        raise TimeoutError(
            f"RamaLama server {self._config.name!r} did not stop in time"
        )

    @contextmanager
    def suspended(self) -> Iterator[None]:
        """Temporarily release GPU memory and restore the prior server state."""

        was_running = self.is_running()
        if was_running:
            self.stop()
        try:
            yield
        finally:
            if was_running:
                self.start()


def _port_from_base_url(base_url: str) -> int:
    parsed = urlparse(base_url)
    if parsed.port is not None:
        return parsed.port
    return 443 if parsed.scheme == "https" else 80
