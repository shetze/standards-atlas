from __future__ import annotations

from pathlib import Path

from standards_atlas.adapters.llm import ContextEnrichmentConfig, LlmConfig


def test_loads_yaml_configuration(tmp_path: Path) -> None:
    path = tmp_path / "llm.yaml"
    path.write_text(
        """
llm:
  base_url: http://localhost:9000/v1
  model: test-model
  timeout_seconds: 42
  cache_directory: cache/llm
""".strip(),
        encoding="utf-8",
    )

    config = LlmConfig.load(path)

    assert config.base_url == "http://localhost:9000/v1"
    assert config.model == "test-model"
    assert config.timeout_seconds == 42
    assert config.cache_directory == Path("cache/llm")


def test_environment_overrides_yaml(monkeypatch, tmp_path: Path) -> None:
    path = tmp_path / "llm.yaml"
    path.write_text("llm:\n  model: yaml-model\n", encoding="utf-8")
    monkeypatch.setenv("STANDARDS_ATLAS_LLM_MODEL", "environment-model")
    monkeypatch.setenv("STANDARDS_ATLAS_LLM_CACHE_DIRECTORY", "")

    config = LlmConfig.load(path)

    assert config.model == "environment-model"
    assert config.cache_directory is None


def test_loads_managed_server_configuration(tmp_path: Path) -> None:
    from standards_atlas.adapters.llm import LlmRuntime

    path = tmp_path / "llm.yaml"
    path.write_text(
        """
llm:
  model: endpoint-model
  server:
    enabled: true
    name: project-llm
    model: server-model
    runtime: vllm
    startup_timeout_seconds: 45
    shutdown_timeout_seconds: 15
""".strip(),
        encoding="utf-8",
    )

    config = LlmConfig.load(path)

    assert config.server.name == "project-llm"
    assert config.server.model == "server-model"
    assert config.server.runtime is LlmRuntime.VLLM
    assert config.server.startup_timeout_seconds == 45
    assert config.server.shutdown_timeout_seconds == 15


def test_loads_dedicated_context_enrichment_configuration(tmp_path: Path) -> None:
    path = tmp_path / "context-enrichment.yaml"
    path.write_text(
        """
context_enrichment:
  prompt:
    task: custom-context-task
    version: context-v2
  generation:
    max_tokens: 700
    retry_max_tokens: 1400
llm:
  model: challenger-model
  timeout_seconds: 180
  cache_directory: cache/context
  server:
    name: context-server
    model: challenger-model-ref
    state_directory: work/context/runtime
""".strip(),
        encoding="utf-8",
    )

    config = ContextEnrichmentConfig.load(path)

    assert config.prompt_task == "custom-context-task"
    assert config.prompt_version == "context-v2"
    assert config.max_tokens == 700
    assert config.retry_max_tokens == 1400
    assert config.llm.model == "challenger-model"
    assert config.llm.timeout_seconds == 180
    assert config.llm.cache_directory == Path("cache/context")
    assert config.llm.server.name == "context-server"
    assert config.llm.server.model == "challenger-model-ref"
    assert config.llm.server.state_directory == Path("work/context/runtime")


def test_context_enrichment_rejects_retry_budget_below_initial_budget() -> None:
    import pytest

    with pytest.raises(ValueError, match="retry_max_tokens"):
        ContextEnrichmentConfig(max_tokens=1024, retry_max_tokens=512)


def test_project_context_enrichment_profile_uses_independent_challenger() -> None:
    config = ContextEnrichmentConfig.load(Path("cfg/context-enrichment.yaml"))

    assert config.prompt_task == "context-routing-enrichment"
    assert config.prompt_version == "context-routing-v1"
    assert config.llm.model == "hf.co/bartowski/phi-4-GGUF:Q4_K_M"
    assert config.llm.server.model == config.llm.model
    assert config.llm.server.name == "standards-atlas-context-enrichment"
    assert config.llm.cache_directory == Path(".atlas/cache/llm/context-enrichment")
