"""Lifecycle management for the project-owned RamaLama inference server."""

from __future__ import annotations

import json
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
    """Current availability and model identity of the managed server."""

    running: bool
    detail: str | None = None
    models: tuple[str, ...] = ()
    endpoint_available: bool = False


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
            if self._expected_model_is_served(health.models):
                return RamaLamaServerStatus(
                    True, health.detail, health.models, endpoint_available=True
                )
            expected = self._config.server.model
            advertised = ", ".join(health.models) if health.models else "<none>"
            return RamaLamaServerStatus(
                False,
                f"LLM endpoint is available but does not serve requested model "
                f"{expected!r}; advertised models: {advertised}",
                health.models,
                endpoint_available=True,
            )
        if process_running:
            return RamaLamaServerStatus(
                False,
                health.detail or f"RamaLama process {pid} is running but endpoint is unavailable",
            )
        return RamaLamaServerStatus(False, health.detail)

    def start(self) -> None:
        if not self._config.server.enabled:
            return

        status = self.status()
        if status.running:
            return
        if status.endpoint_available:
            raise RamaLamaServerError(status.detail or "LLM endpoint serves an unexpected model")

        server = self._config.server
        self._remove_named_container()
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
            self._wait_for_start(process.pid, timeout=server.startup_timeout_seconds)
            self._record_runtime_ownership()
        except RamaLamaServerError:
            self._cleanup_failed_start(process.pid)
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
        """Stop the project-owned container and clean up its launcher process.

        RamaLama's foreground CLI process is only a launcher/controller when the
        actual inference runtime is containerized.  Container ownership is
        therefore authoritative; the PID is retained only for host-side cleanup.
        """
        if not self._config.server.enabled:
            return

        pid = self._read_pid()
        removed_container = self._remove_owned_runtime_container()
        if not removed_container:
            # Compatibility for containers created before ownership persistence
            # existed.  Only project-owned containers publishing this manager's
            # inference port may be taken over.
            removed_container = self._remove_project_container_on_port()
        if not removed_container:
            # Still clean the configured name in case the container exists but is
            # stopped and therefore absent from ``podman ps`` discovery.
            self._remove_named_container()

        try:
            if pid is not None and self._pid_is_running(pid):
                self._terminate_process(pid)
                try:
                    self._wait_for_process_exit(
                        pid, self._config.server.shutdown_timeout_seconds
                    )
                except RamaLamaServerError:
                    # The container is authoritative.  If it has already been
                    # removed, force-clean the stale host launcher and continue.
                    if not self._wait_until_process_stopped(pid, 5.0):
                        raise
        finally:
            self._config.server.pid_file.unlink(missing_ok=True)

        self._wait_for_endpoint_shutdown(self._config.server.shutdown_timeout_seconds)

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

    def _expected_model_is_served(self, advertised_models: tuple[str, ...]) -> bool:
        expected = _canonical_model_identity(self._config.server.model)
        return any(_canonical_model_identity(model) == expected for model in advertised_models)

    def _record_runtime_ownership(self) -> None:
        """Persist the actual project-owned container behind the shared endpoint."""
        container_id = self._container_id_for_name(self._config.server.name)
        if container_id is None:
            raise RamaLamaServerError(
                "RamaLama endpoint became ready but its managed container could not "
                f"be resolved by name {self._config.server.name!r}"
            )
        ownership_file = self._config.server.ownership_file
        ownership_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "container_id": container_id,
            "container_name": self._config.server.name,
            "model": self._config.server.model,
            "port": self._port(),
        }
        ownership_file.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    def _read_runtime_ownership(self) -> dict[str, object] | None:
        try:
            payload = json.loads(
                self._config.server.ownership_file.read_text(encoding="utf-8")
            )
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return None
        return payload if isinstance(payload, dict) else None

    def _clear_runtime_ownership(self) -> None:
        self._config.server.ownership_file.unlink(missing_ok=True)

    def _remove_owned_runtime_container(self) -> bool:
        ownership = self._read_runtime_ownership()
        if ownership is None:
            return False
        container_id = str(ownership.get("container_id") or "").strip()
        container_name = str(ownership.get("container_name") or "").strip()
        target = container_id or container_name
        if not target:
            self._clear_runtime_ownership()
            return False
        self._remove_container(target)
        self._clear_runtime_ownership()
        return True

    def _remove_project_container_on_port(self) -> bool:
        """Remove a legacy Standards Atlas container publishing our LLM port."""
        containers = self._containers_publishing_port(self._port())
        project_containers = [
            (container_id, name)
            for container_id, name in containers
            if name == self._config.server.name or name.startswith("standards-atlas-")
        ]
        if not project_containers:
            return False
        if len(project_containers) > 1:
            names = ", ".join(name for _, name in project_containers)
            raise RamaLamaServerError(
                "Multiple project-owned containers publish the managed LLM port "
                f"{self._port()}: {names}"
            )
        container_id, _ = project_containers[0]
        self._remove_container(container_id)
        return True

    def _containers_publishing_port(self, port: int) -> tuple[tuple[str, str], ...]:
        engine = self._container_engine()
        try:
            result = subprocess.run(  # noqa: S603
                (
                    engine,
                    "ps",
                    "--filter",
                    f"publish={port}",
                    "--format",
                    "{{.ID}}\t{{.Names}}",
                ),
                check=False,
                capture_output=True,
                text=True,
                timeout=10.0,
            )
        except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
            return ()
        containers: list[tuple[str, str]] = []
        for line in result.stdout.splitlines():
            container_id, separator, name = line.partition("\t")
            if separator and container_id.strip() and name.strip():
                containers.append((container_id.strip(), name.strip()))
        return tuple(containers)

    def _container_id_for_name(self, name: str) -> str | None:
        engine = self._container_engine()
        try:
            result = subprocess.run(  # noqa: S603
                (engine, "inspect", "--format", "{{.Id}}", name),
                check=False,
                capture_output=True,
                text=True,
                timeout=10.0,
            )
        except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
            return None
        container_id = result.stdout.strip()
        return container_id if result.returncode == 0 and container_id else None

    def _remove_container(self, target: str) -> None:
        engine = self._container_engine()
        try:
            result = subprocess.run(  # noqa: S603
                (engine, "rm", "--force", target),
                check=False,
                capture_output=True,
                text=True,
                timeout=10.0,
            )
        except FileNotFoundError as exc:
            raise RamaLamaServerError(f"Container engine not found: {engine}") from exc
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RamaLamaServerError(
                f"Could not remove RamaLama container {target!r}: {exc}"
            ) from exc
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            suffix = f": {detail}" if detail else ""
            raise RamaLamaServerError(
                f"Could not remove RamaLama container {target!r}{suffix}"
            )

    @staticmethod
    def _container_engine() -> str:
        return os.environ.get("RAMALAMA_CONTAINER_ENGINE", "podman").strip() or "podman"

    def _wait_for_endpoint_shutdown(self, timeout: float) -> None:
        """Require the old endpoint to disappear before another model may be started."""
        deadline = time.monotonic() + timeout
        gateway = OpenAICompatibleLlmGateway(self._config)
        while time.monotonic() < deadline:
            if not gateway.health().available:
                return
            time.sleep(0.25)
        health = gateway.health()
        models = ", ".join(health.models) if health.models else "<unknown>"
        raise RamaLamaServerError(
            "RamaLama endpoint remained available after shutdown; refusing model switch "
            f"because it still advertises: {models}"
        )

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

    def _wait_for_start(self, pid: int, *, timeout: float) -> None:
        """Wait for readiness and fail early if the foreground server process exits."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            status = self.status()
            if status.running:
                return
            if status.endpoint_available:
                raise RamaLamaServerError(
                    status.detail or "RamaLama endpoint serves an unexpected model"
                )
            if not self._pid_is_running(pid):
                detail = self._tail_log()
                suffix = f"\nRamaLama log:\n{detail}" if detail else ""
                raise RamaLamaServerError(
                    f"RamaLama server process {pid} exited before becoming ready{suffix}"
                )
            time.sleep(0.25)
        detail = self._tail_log()
        suffix = f"\nRamaLama log:\n{detail}" if detail else ""
        raise RamaLamaServerError(
            f"RamaLama server did not start within {timeout:g} seconds{suffix}"
        )

    def _cleanup_failed_start(self, pid: int) -> None:
        """Best-effort cleanup after a failed start so a retry can reuse the name."""
        self._terminate_process(pid)
        try:
            self._wait_for_process_exit(pid, self._config.server.shutdown_timeout_seconds)
        except RamaLamaServerError:
            self._stop_named_container()
            self._wait_until_process_stopped(pid, 5.0)
        finally:
            self._config.server.pid_file.unlink(missing_ok=True)
            self._remove_named_container()

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

    def _remove_named_container(self) -> None:
        """Best-effort removal of a stale container with the configured name."""
        engine = self._container_engine()
        try:
            subprocess.run(  # noqa: S603
                (engine, "rm", "--force", self._config.server.name),
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10.0,
            )
        except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
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


def _canonical_model_identity(model: str) -> str:
    """Normalize a served model to its stable repository identity.

    RamaLama accepts Hugging Face GGUF references such as
    ``hf.co/owner/model-GGUF:Q4_K_M`` but the OpenAI-compatible
    ``/v1/models`` endpoint advertises only ``owner/model-GGUF``.
    The quantization selector therefore cannot be verified through that
    endpoint and must not make an otherwise identical repository look like
    a different model.
    """
    value = model.strip()
    lowered = value.lower()
    prefixes = (
        "huggingface://",
        "huggingface.co/",
        "hf.co://",
        "hf.co/",
        "hf://",
    )
    for prefix in prefixes:
        if lowered.startswith(prefix):
            value = value[len(prefix):].lstrip("/")
            break

    # GGUF transport references may append the selected quantization after
    # the repository id. llama.cpp/RamaLama does not expose that selector via
    # /v1/models, so compare the stable repository identity instead.
    repository, separator, selector = value.rpartition(":")
    if separator and repository.lower().endswith("-gguf") and selector:
        value = repository

    # RamaLama may advertise Hugging Face repositories without a transport
    # prefix. A slash distinguishes those repository ids from simple local
    # aliases such as ``granite`` or ``qwen``.
    if "/" in value:
        return "hf:" + value
    return value
