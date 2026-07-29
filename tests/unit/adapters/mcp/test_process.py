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
