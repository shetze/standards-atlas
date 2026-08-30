from __future__ import annotations

import signal
from dataclasses import replace
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
from standards_atlas.application.ports.llm_gateway import LlmHealth


def _config(tmp_path: Path = Path(".atlas/work/llm/runtime")) -> LlmConfig:
    return LlmConfig(
        base_url="http://127.0.0.1:8080/v1",
        server=RamaLamaServerConfig(
            startup_timeout_seconds=1,
            shutdown_timeout_seconds=1,
            state_directory=tmp_path,
            ownership_file=tmp_path / "active-runtime.json",
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
        patch.object(manager, "_remove_named_container") as remove_container,
        patch.object(manager, "_wait_for_start") as wait_for_start,
        patch.object(manager, "_record_runtime_ownership") as record_ownership,
        patch("subprocess.Popen", return_value=process) as popen,
    ):
        manager.start()

    remove_container.assert_called_once_with()
    wait_for_start.assert_called_once_with(1234, timeout=1)
    record_ownership.assert_called_once_with()
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
    monkeypatch.setattr(manager, "_remove_owned_runtime_container", Mock(return_value=True))
    monkeypatch.setattr(manager, "_wait_until_process_stopped", Mock(return_value=True))
    monkeypatch.setattr(manager, "_wait_for_endpoint_shutdown", Mock())

    manager.stop()

    manager._remove_owned_runtime_container.assert_called_once_with()
    manager._wait_for_endpoint_shutdown.assert_called_once_with(1)
    assert not manager._config.server.pid_file.exists()


def test_start_removes_stale_named_container_before_launch(tmp_path: Path) -> None:
    manager = RamaLamaServerManager(_config(tmp_path))
    process = Mock(pid=1234)

    with (
        patch.object(manager, "status", return_value=RamaLamaServerStatus(False)),
        patch.object(manager, "_remove_named_container") as remove_container,
        patch.object(manager, "_wait_for_start"),
        patch.object(manager, "_record_runtime_ownership"),
        patch("subprocess.Popen", return_value=process),
    ):
        manager.start()

    remove_container.assert_called_once_with()


def test_start_failure_waits_for_process_and_removes_container(tmp_path: Path) -> None:
    manager = RamaLamaServerManager(_config(tmp_path))
    process = Mock(pid=1234)
    failure = RamaLamaServerError("startup timed out")

    with (
        patch.object(manager, "status", return_value=RamaLamaServerStatus(False)),
        patch.object(manager, "_remove_named_container") as remove_container,
        patch.object(manager, "_wait_for_start", side_effect=failure),
        patch.object(manager, "_terminate_process") as terminate,
        patch.object(manager, "_wait_for_process_exit") as wait_for_exit,
        patch("subprocess.Popen", return_value=process),
    ):
        with pytest.raises(RamaLamaServerError, match="startup timed out"):
            manager.start()

    terminate.assert_called_once_with(1234)
    wait_for_exit.assert_called_once_with(1234, 1)
    assert remove_container.call_count == 2
    assert not manager._config.server.pid_file.exists()


def test_start_failure_falls_back_to_container_stop_when_process_will_not_exit(
    tmp_path: Path,
) -> None:
    manager = RamaLamaServerManager(_config(tmp_path))
    process = Mock(pid=1234)

    with (
        patch.object(manager, "status", return_value=RamaLamaServerStatus(False)),
        patch.object(manager, "_remove_named_container"),
        patch.object(
            manager,
            "_wait_for_start",
            side_effect=RamaLamaServerError("startup timed out"),
        ),
        patch.object(manager, "_terminate_process"),
        patch.object(
            manager,
            "_wait_for_process_exit",
            side_effect=RamaLamaServerError("shutdown failed"),
        ),
        patch.object(manager, "_stop_named_container") as stop_container,
        patch.object(manager, "_wait_until_process_stopped", return_value=True),
        patch("subprocess.Popen", return_value=process),
    ):
        with pytest.raises(RamaLamaServerError, match="startup timed out"):
            manager.start()

    stop_container.assert_called_once_with()


def test_wait_for_start_fails_early_when_foreground_process_exits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = RamaLamaServerManager(_config(tmp_path))
    monkeypatch.setattr(manager, "status", Mock(return_value=RamaLamaServerStatus(False)))
    monkeypatch.setattr(manager, "_pid_is_running", Mock(return_value=False))
    monkeypatch.setattr(manager, "_tail_log", Mock(return_value="container name is in use"))

    with pytest.raises(RamaLamaServerError, match="exited before becoming ready") as exc_info:
        manager._wait_for_start(1234, timeout=1)

    assert "container name is in use" in str(exc_info.value)


def test_stop_cleans_stale_container_without_live_pid(tmp_path: Path) -> None:
    manager = RamaLamaServerManager(_config(tmp_path))
    manager._config.server.state_directory.mkdir(parents=True, exist_ok=True)
    manager._config.server.pid_file.write_text("123\n", encoding="utf-8")

    with (
        patch.object(manager, "_pid_is_running", return_value=False),
        patch.object(manager, "_remove_owned_runtime_container", return_value=False),
        patch.object(
            manager, "_remove_project_container_on_port", return_value=True
        ) as remove_legacy,
        patch.object(manager, "_wait_for_endpoint_shutdown") as wait_for_shutdown,
    ):
        manager.stop()

    remove_legacy.assert_called_once_with()
    wait_for_shutdown.assert_called_once_with(1)
    assert not manager._config.server.pid_file.exists()


def test_remove_named_container_uses_configured_engine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = RamaLamaServerManager(_config(tmp_path))
    monkeypatch.setenv("RAMALAMA_CONTAINER_ENGINE", "docker")

    with patch("subprocess.run") as run:
        manager._remove_named_container()

    run.assert_called_once_with(
        ("docker", "rm", "--force", "standards-atlas-llm"),
        check=False,
        stdout=-3,
        stderr=-3,
        timeout=10.0,
    )


def test_status_requires_requested_model_identity(tmp_path: Path) -> None:
    config = _config(tmp_path)
    config = replace(
        config,
        model="hf.co://example/Model-GGUF:Q4_K_M",
        server=replace(config.server, model="hf.co://example/Model-GGUF:Q4_K_M"),
    )
    manager = RamaLamaServerManager(config)

    with patch(
        "standards_atlas.adapters.llm.ramalama_server.OpenAICompatibleLlmGateway.health",
        return_value=LlmHealth(available=True, models=("hf://example/Model-GGUF:Q4_K_M",)),
    ):
        status = manager.status()

    assert status.running
    assert status.endpoint_available
    assert status.models == ("hf://example/Model-GGUF:Q4_K_M",)


def test_status_rejects_endpoint_serving_different_model(tmp_path: Path) -> None:
    manager = RamaLamaServerManager(_config(tmp_path))

    with patch(
        "standards_atlas.adapters.llm.ramalama_server.OpenAICompatibleLlmGateway.health",
        return_value=LlmHealth(available=True, models=("qwen",)),
    ):
        status = manager.status()

    assert not status.running
    assert status.endpoint_available
    assert status.models == ("qwen",)
    assert "does not serve requested model 'granite'" in (status.detail or "")


def test_start_refuses_reachable_endpoint_with_wrong_model(tmp_path: Path) -> None:
    manager = RamaLamaServerManager(_config(tmp_path))

    with (
        patch.object(
            manager,
            "status",
            return_value=RamaLamaServerStatus(
                False,
                "wrong model",
                ("qwen",),
                endpoint_available=True,
            ),
        ),
        patch("subprocess.Popen") as popen,
    ):
        with pytest.raises(RamaLamaServerError, match="wrong model"):
            manager.start()

    popen.assert_not_called()


def test_wait_for_start_fails_immediately_on_wrong_served_model(tmp_path: Path) -> None:
    manager = RamaLamaServerManager(_config(tmp_path))
    manager.status = Mock(  # type: ignore[method-assign]
        return_value=RamaLamaServerStatus(
            False,
            "model identity mismatch",
            ("qwen",),
            endpoint_available=True,
        )
    )
    manager._pid_is_running = Mock(return_value=True)  # type: ignore[method-assign]

    with pytest.raises(RamaLamaServerError, match="model identity mismatch"):
        manager._wait_for_start(1234, timeout=1)


def test_stop_requires_endpoint_to_disappear_without_live_pid(tmp_path: Path) -> None:
    manager = RamaLamaServerManager(_config(tmp_path))

    with (
        patch.object(manager, "_read_pid", return_value=None),
        patch.object(manager, "_stop_named_container"),
        patch.object(manager, "_remove_named_container"),
        patch.object(manager, "_wait_for_endpoint_shutdown") as wait_for_shutdown,
    ):
        manager.stop()

    wait_for_shutdown.assert_called_once_with(1)


def test_endpoint_shutdown_fails_closed_when_server_remains_available(
    tmp_path: Path,
) -> None:
    manager = RamaLamaServerManager(_config(tmp_path))
    health = LlmHealth(available=True, models=("granite",))

    with (
        patch(
            "standards_atlas.adapters.llm.ramalama_server.OpenAICompatibleLlmGateway.health",
            return_value=health,
        ),
        patch(
            "standards_atlas.adapters.llm.ramalama_server.time.monotonic",
            side_effect=(0.0, 2.0),
        ),
    ):
        with pytest.raises(RamaLamaServerError, match="remained available after shutdown"):
            manager._wait_for_endpoint_shutdown(1)


def test_status_accepts_ramalama_gguf_repository_identity_without_quantization(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    config = replace(
        config,
        model="hf.co/ibm-granite/granite-3.3-8b-instruct-GGUF:Q4_K_M",
        server=replace(
            config.server,
            model="hf.co/ibm-granite/granite-3.3-8b-instruct-GGUF:Q4_K_M",
        ),
    )
    manager = RamaLamaServerManager(config)

    with patch(
        "standards_atlas.adapters.llm.ramalama_server.OpenAICompatibleLlmGateway.health",
        return_value=LlmHealth(
            available=True,
            models=("ibm-granite/granite-3.3-8b-instruct-GGUF",),
        ),
    ):
        status = manager.status()

    assert status.running
    assert status.endpoint_available


def test_status_still_rejects_different_gguf_repository_with_same_quantization(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    config = replace(
        config,
        model="hf.co/ibm-granite/granite-3.3-8b-instruct-GGUF:Q4_K_M",
        server=replace(
            config.server,
            model="hf.co/ibm-granite/granite-3.3-8b-instruct-GGUF:Q4_K_M",
        ),
    )
    manager = RamaLamaServerManager(config)

    with patch(
        "standards_atlas.adapters.llm.ramalama_server.OpenAICompatibleLlmGateway.health",
        return_value=LlmHealth(
            available=True,
            models=("Qwen/Qwen3-8B-GGUF",),
        ),
    ):
        status = manager.status()

    assert not status.running
    assert status.endpoint_available


def test_record_runtime_ownership_persists_actual_container_identity(tmp_path: Path) -> None:
    manager = RamaLamaServerManager(_config(tmp_path))

    with patch.object(
        manager, "_container_id_for_name", return_value="abc123"
    ) as inspect_container:
        manager._record_runtime_ownership()

    inspect_container.assert_called_once_with("standards-atlas-llm")
    payload = manager._config.server.ownership_file.read_text(encoding="utf-8")
    assert '"container_id": "abc123"' in payload
    assert '"container_name": "standards-atlas-llm"' in payload
    assert '"model": "granite"' in payload
    assert '"port": 8080' in payload


def test_stop_removes_container_from_shared_ownership_across_profiles(tmp_path: Path) -> None:
    ownership_file = tmp_path / "active-runtime.json"
    context_config = replace(
        _config(tmp_path / "context"),
        model="hf.co/bartowski/phi-4-GGUF:Q4_K_M",
        server=replace(
            _config(tmp_path / "context").server,
            name="standards-atlas-context-enrichment",
            model="hf.co/bartowski/phi-4-GGUF:Q4_K_M",
            ownership_file=ownership_file,
        ),
    )
    qualification_config = replace(
        _config(tmp_path / "qualification"),
        server=replace(
            _config(tmp_path / "qualification").server,
            ownership_file=ownership_file,
        ),
    )
    context_manager = RamaLamaServerManager(context_config)
    qualification_manager = RamaLamaServerManager(qualification_config)

    with patch.object(context_manager, "_container_id_for_name", return_value="phi4-id"):
        context_manager._record_runtime_ownership()

    with (
        patch.object(qualification_manager, "_read_pid", return_value=None),
        patch.object(qualification_manager, "_remove_container") as remove_container,
        patch.object(qualification_manager, "_wait_for_endpoint_shutdown"),
    ):
        qualification_manager.stop()

    remove_container.assert_called_once_with("phi4-id")
    assert not ownership_file.exists()


def test_stop_discovers_legacy_context_container_by_managed_port(tmp_path: Path) -> None:
    manager = RamaLamaServerManager(_config(tmp_path))

    with (
        patch.object(manager, "_read_pid", return_value=None),
        patch.object(manager, "_read_runtime_ownership", return_value=None),
        patch.object(
            manager,
            "_containers_publishing_port",
            return_value=(("phi4-id", "standards-atlas-context-enrichment"),),
        ),
        patch.object(manager, "_remove_container") as remove_container,
        patch.object(manager, "_wait_for_endpoint_shutdown"),
    ):
        manager.stop()

    remove_container.assert_called_once_with("phi4-id")


def test_stop_does_not_take_over_foreign_container_on_managed_port(tmp_path: Path) -> None:
    manager = RamaLamaServerManager(_config(tmp_path))

    with (
        patch.object(manager, "_read_pid", return_value=None),
        patch.object(manager, "_read_runtime_ownership", return_value=None),
        patch.object(
            manager,
            "_containers_publishing_port",
            return_value=(("foreign-id", "unrelated-llm"),),
        ),
        patch.object(manager, "_remove_container") as remove_container,
        patch.object(manager, "_remove_named_container"),
        patch.object(
            manager,
            "_wait_for_endpoint_shutdown",
            side_effect=RamaLamaServerError("endpoint remained available"),
        ),
    ):
        with pytest.raises(RamaLamaServerError, match="endpoint remained available"):
            manager.stop()

    remove_container.assert_not_called()
