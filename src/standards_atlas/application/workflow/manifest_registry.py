"""Typed workflow manifest discovery and validation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import yaml

from standards_atlas.application.schema import require_current_schema


class WorkflowManifestType(StrEnum):
    STANDARDS = "standards"
    QUALIFICATION_MATRIX = "qualification_matrix"


@dataclass(frozen=True)
class WorkflowManifestSet:
    """Resolved workflow manifests keyed by their declared manifest type."""

    paths: tuple[Path, ...]
    by_type: dict[WorkflowManifestType, Path]

    def require(self, manifest_type: WorkflowManifestType) -> Path:
        try:
            return self.by_type[manifest_type]
        except KeyError as exc:
            raise ValueError(
                "workflow requires exactly one manifest of type "
                f"{manifest_type.value!r}; none was provided"
            ) from exc

    def optional(self, manifest_type: WorkflowManifestType) -> Path | None:
        return self.by_type.get(manifest_type)


class WorkflowManifestLoader:
    """Load the common manifest envelope without knowing each payload schema."""

    def load(self, paths: tuple[Path, ...]) -> WorkflowManifestSet:
        if not paths:
            raise ValueError("at least one workflow manifest must be provided")
        by_type: dict[WorkflowManifestType, Path] = {}
        normalized: list[Path] = []
        for path in paths:
            payload = yaml.safe_load(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError(f"manifest {path} must contain a YAML mapping")
            raw_type = payload.get("manifest_type")
            if raw_type is None:
                raise ValueError(f"manifest {path} is missing required 'manifest_type' header")
            if "schema_version" not in payload:
                raise ValueError(f"manifest {path} is missing required 'schema_version' header")
            try:
                manifest_type = WorkflowManifestType(str(raw_type))
            except ValueError as exc:
                known = ", ".join(item.value for item in WorkflowManifestType)
                raise ValueError(
                    f"manifest {path} declares unsupported manifest_type {raw_type!r}; "
                    f"expected one of: {known}"
                ) from exc
            schema_family = {
                WorkflowManifestType.STANDARDS: "standards-manifest",
                WorkflowManifestType.QUALIFICATION_MATRIX: "qualification-matrix-manifest",
            }[manifest_type]
            require_current_schema(schema_family, payload["schema_version"])
            if manifest_type in by_type:
                raise ValueError(
                    f"workflow accepts exactly one manifest of type {manifest_type.value!r}; "
                    f"provided {by_type[manifest_type]} and {path}"
                )
            by_type[manifest_type] = path
            normalized.append(path)
        return WorkflowManifestSet(paths=tuple(normalized), by_type=by_type)


def parse_manifest_options(values: tuple[str, ...]) -> tuple[Path, ...]:
    """Flatten repeated and comma-separated --manifests values."""
    paths: list[Path] = []
    for value in values:
        for item in value.split(","):
            candidate = item.strip()
            if candidate:
                paths.append(Path(candidate))
    if not paths:
        raise ValueError("--manifests requires at least one manifest path")
    return tuple(paths)
