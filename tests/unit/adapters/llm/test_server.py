from __future__ import annotations

from unittest.mock import Mock

from standards_atlas.adapters.llm.server import (
    LlmRuntime,
    ManagedLlmServerConfig,
    RamaLamaServerController,
)


def test_start_uses_configured_runtime_and_service_name() -> None:
    executor = Mock()
    controller = RamaLamaServerController(
        base_url="http://127.0.0.1:8080/v1",
        config=ManagedLlmServerConfig(
            name="standards-atlas-llm",
            model="granite",
            runtime=LlmRuntime.LLAMA_CPP,
        ),
        executor=executor,
    )
    controller.is_running = Mock(side_effect=[False, True])  # type: ignore[method-assign]

    controller.start()

    executor.run.assert_called_once_with(
        (
            "ramalama",
            "serve",
            "--detach",
            "--name",
            "standards-atlas-llm",
            "--port",
            "8080",
            "--runtime=llama.cpp",
            "granite",
        )
    )


def test_suspended_restores_a_previously_running_server() -> None:
    controller = RamaLamaServerController(
        base_url="http://127.0.0.1:8080/v1",
        config=ManagedLlmServerConfig(),
        executor=Mock(),
    )
    controller.is_running = Mock(return_value=True)  # type: ignore[method-assign]
    controller.stop = Mock()  # type: ignore[method-assign]
    controller.start = Mock()  # type: ignore[method-assign]

    with controller.suspended():
        controller.stop.assert_called_once_with()
        controller.start.assert_not_called()

    controller.start.assert_called_once_with()


def test_suspended_does_not_start_a_server_that_was_stopped() -> None:
    controller = RamaLamaServerController(
        base_url="http://127.0.0.1:8080/v1",
        config=ManagedLlmServerConfig(),
        executor=Mock(),
    )
    controller.is_running = Mock(return_value=False)  # type: ignore[method-assign]
    controller.stop = Mock()  # type: ignore[method-assign]
    controller.start = Mock()  # type: ignore[method-assign]

    with controller.suspended():
        pass

    controller.stop.assert_not_called()
    controller.start.assert_not_called()


def test_vllm_is_available_as_a_configuration_choice() -> None:
    config = ManagedLlmServerConfig(runtime=LlmRuntime.VLLM)

    assert config.runtime.value == "vllm"
