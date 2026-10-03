from standards_atlas.adapters.llm.codex_cli import CodexCliConfig, CodexCliLlmGateway


def test_codex_health_reports_missing_executable():
    health = CodexCliLlmGateway(CodexCliConfig(executable="definitely-not-codex")).health()
    assert not health.available


def _request(**changes):
    from standards_atlas.application.ports.llm_gateway import StructuredGenerationRequest

    values = {
        "task": "synthetic",
        "system_prompt": "system",
        "user_prompt": "user",
        "output_schema": {"type": "object"},
        "prompt_version": "test-v1",
        "model": "explicit-model",
    }
    values.update(changes)
    return StructuredGenerationRequest(**values)


def test_direct_codex_inference_arm_is_disabled_by_default(monkeypatch):
    import subprocess

    called = False

    def fail_if_called(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("subprocess must not be called")

    monkeypatch.setattr(subprocess, "run", fail_if_called)
    gateway = CodexCliLlmGateway(CodexCliConfig(executable="codex"))

    import pytest

    with pytest.raises(RuntimeError, match="disabled"):
        gateway.generate_structured(_request())
    assert not called


def test_uncontrolled_codex_parameters_are_rejected_before_subprocess(monkeypatch):
    import subprocess

    import pytest

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("subprocess must not run")),
    )
    gateway = CodexCliLlmGateway(
        CodexCliConfig(executable="codex", allow_uncontrolled_inference=True)
    )

    with pytest.raises(RuntimeError, match="seed"):
        gateway.generate_structured(_request(seed=7))
    with pytest.raises(RuntimeError, match="max_tokens"):
        gateway.generate_structured(_request(max_tokens=256))
    with pytest.raises(RuntimeError, match="explicit model"):
        gateway.generate_structured(_request(model=None))
