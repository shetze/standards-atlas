"""RamaLama model catalog assembled from qualification manifests."""

from __future__ import annotations

from pathlib import Path

import yaml

from standards_atlas.application.prompt_workbench.models import (
    ModelCatalogEntry,
    ModelGenerationDefaults,
)
from standards_atlas.application.semantic_qualification.qualification_matrix import (
    ModelCandidate,
    QualificationMatrixManifest,
)


class ManifestRamaLamaModelCatalog:
    """Load and deduplicate selectable RamaLama models from matrix manifests."""

    def __init__(self, manifest_paths: tuple[Path, ...]) -> None:
        self._models = self._load(manifest_paths)

    @classmethod
    def from_directory(cls, root: Path) -> ManifestRamaLamaModelCatalog:
        return cls(tuple(sorted(root.glob("*.yaml"))))

    def list_models(self) -> tuple[ModelCatalogEntry, ...]:
        return self._models

    def get_model(self, model_id: str) -> ModelCatalogEntry:
        try:
            return next(item for item in self._models if item.id == model_id)
        except StopIteration as exc:
            available = ", ".join(item.id for item in self._models)
            raise KeyError(f"unknown RamaLama model {model_id!r}; available: {available}") from exc

    @staticmethod
    def _load(paths: tuple[Path, ...]) -> tuple[ModelCatalogEntry, ...]:
        by_id: dict[str, ModelCatalogEntry] = {}
        for path in paths:
            payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if (
                not isinstance(payload, dict)
                or payload.get("manifest_type") != "qualification_matrix"
            ):
                continue
            manifest = QualificationMatrixManifest.load(path)
            candidates = list(manifest.models)
            if manifest.challenger_qualification.enabled:
                candidates.extend(manifest.challenger_qualification.models)
            for candidate in candidates:
                if candidate.provider != "ramalama" or not candidate.model_ref:
                    continue
                entry = _entry(candidate, path)
                existing = by_id.get(entry.id)
                if existing is None:
                    by_id[entry.id] = entry
                    continue
                if existing.model_ref != entry.model_ref:
                    raise ValueError(
                        f"conflicting model_ref declarations for {entry.id!r}: "
                        f"{existing.model_ref!r} in {existing.sources[0]} and "
                        f"{entry.model_ref!r} in {path}"
                    )
                by_id[entry.id] = existing.model_copy(
                    update={"sources": (*existing.sources, str(path))}
                )
        return tuple(by_id[key] for key in sorted(by_id))


def _entry(candidate: ModelCandidate, path: Path) -> ModelCatalogEntry:
    return ModelCatalogEntry(
        id=candidate.id,
        model_ref=candidate.model_ref or "",
        description=candidate.description,
        quantization=candidate.quantization,
        supported_reasoning_modes=candidate.supported_reasoning_modes,
        generation=ModelGenerationDefaults(
            max_output_tokens=candidate.generation.max_output_tokens,
            truncation_retry_max_tokens=candidate.generation.truncation_retry_max_tokens,
            reasoning_enabled=candidate.generation.reasoning_mode == "enabled",
        ),
        sources=(str(path),),
    )
