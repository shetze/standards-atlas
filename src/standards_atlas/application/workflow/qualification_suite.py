"""Versioned orchestration manifest for routed semantic qualification suites."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from standards_atlas.application.schema import require_supported_schema


class QualificationSuiteManifest(BaseModel):
    """Bind one routing manifest to an ordered set of qualification matrices."""

    model_config = ConfigDict(frozen=True)

    manifest_type: Literal["qualification_suite"] = "qualification_suite"
    schema_version: Literal[1] = 1
    suite_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    routing_manifest: str = Field(min_length=1)
    qualification_manifests: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_manifests(self) -> QualificationSuiteManifest:
        if len(set(self.qualification_manifests)) != len(self.qualification_manifests):
            raise ValueError("qualification suite contains duplicate qualification manifests")
        return self

    def resolve(self, suite_path: Path, project_root: Path) -> tuple[Path, tuple[Path, ...]]:
        """Resolve suite-relative references with project-root fallback."""

        base = suite_path.parent

        def _resolve(value: str) -> Path:
            candidate = Path(value)
            if candidate.is_absolute():
                return candidate
            relative = (base / candidate).resolve()
            if relative.exists():
                return relative
            return (project_root / candidate).resolve()

        return _resolve(self.routing_manifest), tuple(
            _resolve(value) for value in self.qualification_manifests
        )


def load_qualification_suite_manifest(path: Path) -> QualificationSuiteManifest:
    """Load and validate one qualification-suite workflow manifest."""

    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    require_supported_schema("qualification-suite-manifest", payload.get("schema_version"))
    return QualificationSuiteManifest.model_validate(payload)
