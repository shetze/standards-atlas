import signal
from pathlib import Path
from unittest.mock import Mock

import pytest

from standards_atlas.adapters.mcp import (
    McpServerConfig,
    McpServerProcessError,
    McpServerProcessManager,
    McpServerProcessStatus,
)


def test_background_manager_requires_http_transport(tmp_path: Path) -> None:
    config = McpServerConfig(
        transport="stdio",
        process={"state_directory": tmp_path / "runtime"},
    )
    manager = McpServerProcessManager(config, tmp_path / "mcp.yaml")

    with pytest.raises(McpServerProcessError, match="streamable-http"):
        manager.status()


def test_status_removes_stale_pid_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = McpServerConfig(
        transport="streamable-http",
        process={"state_directory": tmp_path / "runtime"},
    )
    config.process.state_directory.mkdir(parents=True)
    config.process.pid_file.write_text("123\n", encoding="utf-8")
    manager = McpServerProcessManager(config, tmp_path / "mcp.yaml")
    monkeypatch.setattr(manager, "_pid_is_running", Mock(return_value=False))

    status = manager.status()

    assert not status.running
    assert "stale PID" in (status.detail or "")
    assert not config.process.pid_file.exists()


def test_status_reports_running_process_and_endpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = McpServerConfig(
        transport="streamable-http",
        process={"state_directory": tmp_path / "runtime"},
    )
    config.process.state_directory.mkdir(parents=True)
    config.process.pid_file.write_text("456\n", encoding="utf-8")
    manager = McpServerProcessManager(config, tmp_path / "mcp.yaml")
    monkeypatch.setattr(manager, "_pid_is_running", Mock(return_value=True))
    monkeypatch.setattr(manager, "_endpoint_available", Mock(return_value=True))

    status = manager.status()

    assert status.running
    assert status.pid == 456


def test_ensure_running_preserves_existing_server(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = McpServerConfig(
        transport="streamable-http",
        process={"state_directory": tmp_path / "runtime"},
    )
    manager = McpServerProcessManager(config, tmp_path / "mcp.yaml")
    running = McpServerProcessStatus(True, 123, "available")
    stop = Mock()
    monkeypatch.setattr(manager, "status", Mock(return_value=running))
    monkeypatch.setattr(manager, "stop", stop)

    with manager.ensure_running() as observed:
        assert observed.running
        assert observed.pid == 123

    stop.assert_not_called()


def test_ensure_running_stops_only_server_started_here(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = McpServerConfig(
        transport="streamable-http",
        process={"state_directory": tmp_path / "runtime"},
    )
    manager = McpServerProcessManager(config, tmp_path / "mcp.yaml")
    stopped = McpServerProcessStatus(False, None, "stopped")
    running = McpServerProcessStatus(True, 456, "available")
    start = Mock()
    stop = Mock()
    monkeypatch.setattr(manager, "status", Mock(side_effect=(stopped, running)))
    monkeypatch.setattr(manager, "start", start)
    monkeypatch.setattr(manager, "stop", stop)

    with manager.ensure_running() as observed:
        assert observed.pid == 456

    start.assert_called_once_with()
    stop.assert_called_once_with()


def test_ensure_running_fails_when_autostart_is_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = McpServerConfig(
        transport="streamable-http",
        process={"state_directory": tmp_path / "runtime"},
    )
    manager = McpServerProcessManager(config, tmp_path / "mcp.yaml")
    stopped = McpServerProcessStatus(False, None, "stopped")
    monkeypatch.setattr(manager, "status", Mock(return_value=stopped))

    with pytest.raises(McpServerProcessError, match="automatic start is disabled"):
        with manager.ensure_running(autostart=False):
            pass


def test_wait_for_process_exit_accepts_exit_after_sigkill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = McpServerConfig(
        transport="streamable-http",
        process={
            "state_directory": tmp_path / "runtime",
            "shutdown_timeout_seconds": 0.01,
        },
    )
    manager = McpServerProcessManager(config, tmp_path / "mcp.yaml")
    waits = Mock(side_effect=(False, True))
    killpg = Mock()
    monkeypatch.setattr(manager, "_wait_until_process_stopped", waits)
    monkeypatch.setattr("os.killpg", killpg)

    manager._wait_for_process_exit(789)

    killpg.assert_called_once_with(789, signal.SIGKILL)
    assert waits.call_count == 2


def test_pid_is_running_treats_zombie_as_stopped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("os.kill", Mock())
    monkeypatch.setattr(
        Path,
        "read_text",
        Mock(return_value="123 (python) Z 1 2 3"),
    )

    assert not McpServerProcessManager._pid_is_running(123)


def test_restart_stops_before_starting_current_code(tmp_path, monkeypatch) -> None:
    config = McpServerConfig(
        transport="streamable-http", process={"state_directory": tmp_path / "runtime"}
    )
    manager = McpServerProcessManager(config, tmp_path / "mcp.yaml")
    calls = []
    monkeypatch.setattr(manager, "stop", lambda: calls.append("stop"))
    monkeypatch.setattr(manager, "start", lambda: calls.append("start"))

    manager.restart()

    assert calls == ["stop", "start"]


def test_restart_does_not_start_after_failed_stop(tmp_path, monkeypatch) -> None:
    config = McpServerConfig(
        transport="streamable-http", process={"state_directory": tmp_path / "runtime"}
    )
    manager = McpServerProcessManager(config, tmp_path / "mcp.yaml")
    start = Mock()
    monkeypatch.setattr(manager, "stop", Mock(side_effect=McpServerProcessError("cannot stop")))
    monkeypatch.setattr(manager, "start", start)

    with pytest.raises(McpServerProcessError, match="cannot stop"):
        manager.restart()

    start.assert_not_called()


def test_start_remains_idempotent_and_does_not_replace_running_server(
    tmp_path,
    monkeypatch,
) -> None:
    config = McpServerConfig(
        transport="streamable-http", process={"state_directory": tmp_path / "runtime"}
    )
    manager = McpServerProcessManager(config, tmp_path / "mcp.yaml")
    spawn = Mock()
    monkeypatch.setattr(manager, "status", Mock(return_value=McpServerProcessStatus(True, 123)))
    monkeypatch.setattr("subprocess.Popen", spawn)

    manager.start()

    spawn.assert_not_called()


def test_start_refuses_unmanaged_listener_without_spawning_or_killing(
    tmp_path,
    monkeypatch,
) -> None:
    config = McpServerConfig(
        transport="streamable-http", process={"state_directory": tmp_path / "runtime"}
    )
    manager = McpServerProcessManager(config, tmp_path / "mcp.yaml")
    spawn, terminate = Mock(), Mock()
    monkeypatch.setattr(manager, "_endpoint_available", Mock(return_value=True))
    monkeypatch.setattr(manager, "_terminate_process", terminate)
    monkeypatch.setattr("subprocess.Popen", spawn)

    with pytest.raises(McpServerProcessError, match="occupied without a managed PID"):
        manager.restart()

    spawn.assert_not_called()
    terminate.assert_not_called()
    assert not config.process.pid_file.exists()
