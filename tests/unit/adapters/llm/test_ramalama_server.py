from __future__ import annotations

import signal
from pathlib import Path
from unittest.mock import ANY, Mock, patch

import pytest

from standards_atlas.adapters.llm import (
    LlmConfig,
    RamaLamaServerConfig,
    RamaLamaServerError,
    RamaLamaServerManager,
    RamaLamaServerStatus,
)


def _config(tmp_path: Path = Path(".atlas/llm/runtime")) -> LlmConfig:
    return LlmConfig(
        base_url="http://127.0.0.1:8080/v1",
        server=RamaLamaServerConfig(
            startup_timeout_seconds=1,
            shutdown_timeout_seconds=1,
            state_directory=tmp_path,
        ),
    )


def test_start_invokes_same_foreground_command_as_start_script(tmp_path: Path) -> None:
    manager = RamaLamaServerManager(_config(tmp_path))
    statuses = iter(
        [
            RamaLamaServerStatus(False),
            RamaLamaServerStatus(True),
        ]
    )
    process = Mock(pid=1234)

    with (
        patch.object(manager, "status", side_effect=lambda: next(statuses)),
        patch("subprocess.Popen", return_value=process) as popen,
    ):
        manager.start()

    popen.assert_called_once_with(
        (
            "ramalama",
            "serve",
            "--name",
            "standards-atlas-llm",
            "--backend",
            "auto",
            "--selinux=false",
            "--port",
            "8080",
            "granite",
        ),
        stdin=-3,
        stdout=ANY,
        stderr=-2,
        start_new_session=True,
    )
    assert (tmp_path / "ramalama.pid").read_text(encoding="utf-8") == "1234\n"


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


def test_stop_for_exclusive_accelerator_leaves_running_server_stopped() -> None:
    manager = RamaLamaServerManager(_config())
    manager.status = Mock(return_value=RamaLamaServerStatus(True))  # type: ignore[method-assign]
    manager.stop = Mock()  # type: ignore[method-assign]
    manager.start = Mock()  # type: ignore[method-assign]

    with manager.stopped_for_exclusive_accelerator():
        pass

    assert manager.stop.call_count == 1
    manager.start.assert_not_called()


def test_stop_for_exclusive_accelerator_does_not_restore_after_failure() -> None:
    manager = RamaLamaServerManager(_config())
    manager.status = Mock(return_value=RamaLamaServerStatus(True))  # type: ignore[method-assign]
    manager.stop = Mock()  # type: ignore[method-assign]
    manager.start = Mock()  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="conversion failed"):
        with manager.stopped_for_exclusive_accelerator():
            raise RuntimeError("conversion failed")

    assert manager.stop.call_count == 1
    manager.start.assert_not_called()


def test_rejects_remote_endpoint_for_managed_server() -> None:
    manager = RamaLamaServerManager(LlmConfig(base_url="https://example.com/v1"))
    manager.status = Mock(return_value=RamaLamaServerStatus(False))  # type: ignore[method-assign]

    with pytest.raises(RamaLamaServerError, match="loopback"):
        manager.start()


def test_wait_for_process_exit_accepts_exit_after_sigkill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = RamaLamaServerManager(_config(tmp_path))
    waits = Mock(side_effect=(False, True))
    killpg = Mock()
    monkeypatch.setattr(manager, "_wait_until_process_stopped", waits)
    monkeypatch.setattr("os.killpg", killpg)

    manager._wait_for_process_exit(789, 0.01)

    killpg.assert_called_once_with(789, signal.SIGKILL)
    assert waits.call_count == 2


def test_pid_is_running_treats_zombie_as_stopped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("os.kill", Mock())
    monkeypatch.setattr(
        Path,
        "read_text",
        Mock(return_value="123 (ramalama) Z 1 2 3"),
    )

    assert not RamaLamaServerManager._pid_is_running(123)


def test_stop_removes_pid_file_when_shutdown_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = RamaLamaServerManager(_config(tmp_path))
    manager._config.server.state_directory.mkdir(parents=True, exist_ok=True)
    manager._config.server.pid_file.write_text("123\n", encoding="utf-8")
    monkeypatch.setattr(manager, "_pid_is_running", Mock(return_value=True))
    monkeypatch.setattr(manager, "_terminate_process", Mock())
    monkeypatch.setattr(
        manager,
        "_wait_for_process_exit",
        Mock(side_effect=RamaLamaServerError("shutdown failed")),
    )
    monkeypatch.setattr(manager, "_stop_named_container", Mock())
    monkeypatch.setattr(manager, "_wait_until_process_stopped", Mock(return_value=False))

    with pytest.raises(RamaLamaServerError, match="shutdown failed"):
        manager.stop()

    assert not manager._config.server.pid_file.exists()


def test_pull_downloads_model_with_ramalama(tmp_path: Path) -> None:
    manager = RamaLamaServerManager(_config(tmp_path))

    with patch("subprocess.run") as run:
        manager.pull("hf.co/example/model-GGUF:Q4_K_M")

    run.assert_called_once_with(
        ("ramalama", "pull", "hf.co/example/model-GGUF:Q4_K_M"),
        check=True,
    )


def test_stop_falls_back_to_named_container(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = RamaLamaServerManager(_config(tmp_path))
    manager._config.server.state_directory.mkdir(parents=True, exist_ok=True)
    manager._config.server.pid_file.write_text("123\n", encoding="utf-8")
    monkeypatch.setattr(manager, "_pid_is_running", Mock(return_value=True))
    monkeypatch.setattr(manager, "_terminate_process", Mock())
    monkeypatch.setattr(
        manager,
        "_wait_for_process_exit",
        Mock(side_effect=RamaLamaServerError("shutdown failed")),
    )
    monkeypatch.setattr(manager, "_stop_named_container", Mock())
    monkeypatch.setattr(manager, "_wait_until_process_stopped", Mock(return_value=True))

    manager.stop()

    manager._stop_named_container.assert_called_once_with()
    assert not manager._config.server.pid_file.exists()
