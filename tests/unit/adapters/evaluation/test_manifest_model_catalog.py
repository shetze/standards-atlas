from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from standards_atlas.adapters.evaluation.manifest_model_catalog import (
    ManifestRamaLamaModelCatalog,
)


def _manifest(path: Path, *, model_ref: str, include_codex: bool = False) -> None:
    models = [
        {
            "id": "granite",
            "provider": "ramalama",
            "model_ref": model_ref,
            "supported_reasoning_modes": ["disabled", "enabled"],
            "generation": {
                "max_output_tokens": 384,
                "truncation_retry_max_tokens": 512,
            },
        }
    ]
    if include_codex:
        models.append({"id": "codex", "provider": "codex", "model_ref": "gpt"})
    path.write_text(
        yaml.safe_dump(
            {
                "manifest_type": "qualification_matrix",
                "schema_version": "1.5",
                "matrix_id": path.stem,
                "corpus_id": "corpus",
                "prompts": [{"id": "one"}, {"id": "two"}],
                "models": models,
                "reasoning_modes": [
                    {"id": "disabled", "enabled": False},
                    {"id": "enabled", "enabled": True, "optional": True},
                ],
            }
        ),
        encoding="utf-8",
    )


def test_deduplicates_ramalama_models_and_records_manifest_sources(tmp_path: Path) -> None:
    first = tmp_path / "first.yaml"
    second = tmp_path / "second.yaml"
    ignored = tmp_path / "standards.yaml"
    _manifest(first, model_ref="hf.co/example/granite:Q4_K_M", include_codex=True)
    _manifest(second, model_ref="hf.co/example/granite:Q4_K_M")
    ignored.write_text("manifest_type: standards\n", encoding="utf-8")

    models = ManifestRamaLamaModelCatalog((first, ignored, second)).list_models()

    assert [item.id for item in models] == ["granite"]
    assert models[0].generation.max_output_tokens == 384
    assert models[0].supported_reasoning_modes == ("disabled", "enabled")
    assert models[0].sources == (str(first), str(second))


def test_rejects_conflicting_model_references(tmp_path: Path) -> None:
    first = tmp_path / "first.yaml"
    second = tmp_path / "second.yaml"
    _manifest(first, model_ref="hf.co/example/granite:Q4_K_M")
    _manifest(second, model_ref="hf.co/example/granite:Q6_K")

    with pytest.raises(ValueError, match="conflicting model_ref declarations"):
        ManifestRamaLamaModelCatalog((first, second))
