from __future__ import annotations

from pathlib import Path

from standards_atlas.adapters.llm import LlmConfig


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
