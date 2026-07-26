from __future__ import annotations

from unittest.mock import Mock, patch

import pytest

from standards_atlas.adapters.llm import (
    LlmConfig,
    RamaLamaServerConfig,
    RamaLamaServerError,
    RamaLamaServerManager,
    RamaLamaServerStatus,
)


def _config() -> LlmConfig:
    return LlmConfig(
        base_url="http://127.0.0.1:8080/v1",
        server=RamaLamaServerConfig(
            startup_timeout_seconds=1,
            shutdown_timeout_seconds=1,
        ),
    )


def test_start_invokes_ramalama_with_configured_runtime() -> None:
    manager = RamaLamaServerManager(_config())
    statuses = iter(
        [
            RamaLamaServerStatus(False),
            RamaLamaServerStatus(True),
        ]
    )

    with (
        patch.object(manager, "status", side_effect=lambda: next(statuses)),
        patch("subprocess.run") as run,
    ):
        manager.start()

    run.assert_called_once_with(
        (
            "ramalama",
            "serve",
            "--detach",
            "--name",
            "standards-atlas-llm",
            "--port",
            "8080",
            "--runtime",
            "llama.cpp",
            "--webui",
            "off",
            "granite",
        ),
        check=True,
        capture_output=True,
        text=True,
    )


def test_pause_restores_only_previously_running_server() -> None:
    manager = RamaLamaServerManager(_config())
    manager.status = Mock(return_value=RamaLamaServerStatus(True))  # type: ignore[method-assign]
    manager.stop = Mock()  # type: ignore[method-assign]
    manager.start = Mock()  # type: ignore[method-assign]

    with manager.paused_for_exclusive_accelerator():
        pass

    assert manager.stop.call_count == 1
    assert manager.start.call_count == 1


def test_pause_restores_server_after_workload_failure() -> None:
    manager = RamaLamaServerManager(_config())
    manager.status = Mock(return_value=RamaLamaServerStatus(True))  # type: ignore[method-assign]
    manager.stop = Mock()  # type: ignore[method-assign]
    manager.start = Mock()  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="conversion failed"):
        with manager.paused_for_exclusive_accelerator():
            raise RuntimeError("conversion failed")

    assert manager.stop.call_count == 1
    assert manager.start.call_count == 1


def test_rejects_remote_endpoint_for_managed_server() -> None:
    manager = RamaLamaServerManager(
        LlmConfig(base_url="https://example.com/v1")
    )
    manager.status = Mock(return_value=RamaLamaServerStatus(False))  # type: ignore[method-assign]

    with pytest.raises(RamaLamaServerError, match="loopback"):
        manager.start()
