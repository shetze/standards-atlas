"""Export deterministic Gemara governance sources for ComplyTime authoring."""

from __future__ import annotations

import shutil
from hashlib import sha256
from pathlib import Path

import yaml

from standards_atlas.adapters.artifact_lineage import write_directory_lineage_manifest
from standards_atlas.adapters.complytime.models import (
    GovernanceBundleArtifact,
    GovernanceBundleManifest,
    GovernanceBundleSource,
    GovernanceBundleTraceability,
)
from standards_atlas.adapters.gemara.contract import (
    GEMARA_SPEC_VERSION,
    artifact_version,
    control_catalog_id,
    gemara_id,
    guidance_catalog_id,
)
from standards_atlas.adapters.gemara.control_mapper import GemaraControlMapper
from standards_atlas.adapters.gemara.control_traceability import build_control_traceability
from standards_atlas.adapters.gemara.mapper import GemaraGuidanceMapper
from standards_atlas.adapters.gemara.traceability import build_traceability
from standards_atlas.application.model import PublicationDocument
from standards_atlas.shared.artifacts import write_json, write_yaml

_GUIDANCE_FILE = "guidance.yaml"
_CONTROLS_FILE = "controls.yaml"
_TRACEABILITY_FILE = "traceability.json"
_MANIFEST_FILE = "manifest.yaml"


class ComplyTimeGovernanceBundleExporter:
    """Create an evaluator-independent governance source bundle."""

    def __init__(
        self,
        *,
        guidance_mapper: GemaraGuidanceMapper | None = None,
        control_mapper: GemaraControlMapper | None = None,
    ) -> None:
        self._guidance_mapper = guidance_mapper or GemaraGuidanceMapper()
        self._control_mapper = control_mapper or GemaraControlMapper()

    def export(
        self,
        document: PublicationDocument,
        target: Path,
        *,
        replace_existing: bool = True,
    ) -> Path:
        """Export guidance, controls, traceability, and bundle manifest."""
        if target.exists():
            if not replace_existing:
                raise FileExistsError(f"ComplyTime governance bundle already exists: {target}")
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
        target.mkdir(parents=True, exist_ok=False)

        guidance = self._guidance_mapper.map(document)
        controls = self._control_mapper.map(document)

        guidance_bytes = _yaml_bytes(
            guidance.model_dump(mode="json", by_alias=True, exclude_none=True)
        )
        control_bytes = _yaml_bytes(
            controls.model_dump(mode="json", by_alias=True, exclude_none=True)
        )

        guidance_path = target / _GUIDANCE_FILE
        controls_path = target / _CONTROLS_FILE
        guidance_path.write_bytes(guidance_bytes)
        controls_path.write_bytes(control_bytes)

        guidance_hash = sha256(guidance_bytes).hexdigest()
        controls_hash = sha256(control_bytes).hexdigest()
        traceability = GovernanceBundleTraceability(
            document_key=document.key.value,
            guidance=build_traceability(
                document,
                guidance,
                exported_artifact_sha256=guidance_hash,
            ).model_dump(mode="json", exclude_none=True),
            controls=build_control_traceability(
                document,
                controls,
                exported_artifact_sha256=controls_hash,
            ).model_dump(mode="json", exclude_none=True),
        )
        traceability_path = target / _TRACEABILITY_FILE
        write_json(
            traceability_path,
            traceability.model_dump(mode="json"),
            sort_keys=True,
        )

        manifest = GovernanceBundleManifest(
            bundle_id=gemara_id(f"{document.key.value}-governance"),
            source=GovernanceBundleSource(
                document_key=document.key.value,
                title=document.title,
                version=artifact_version(document),
            ),
            gemara_version=GEMARA_SPEC_VERSION,
            guidance=GovernanceBundleArtifact(
                path=_GUIDANCE_FILE,
                media_type="application/yaml",
                sha256=guidance_hash,
                catalog_id=guidance_catalog_id(document.key.value),
            ),
            controls=GovernanceBundleArtifact(
                path=_CONTROLS_FILE,
                media_type="application/yaml",
                sha256=controls_hash,
                catalog_id=control_catalog_id(document.key.value),
            ),
            traceability=GovernanceBundleArtifact(
                path=_TRACEABILITY_FILE,
                media_type="application/json",
                sha256=_sha256_file(traceability_path),
            ),
        )
        write_yaml(
            target / _MANIFEST_FILE,
            manifest.model_dump(mode="json", by_alias=True, exclude_none=True),
        )
        write_directory_lineage_manifest(
            target,
            document,
            kind="complytime_governance_bundle",
        )
        return target


def _yaml_bytes(payload: object) -> bytes:
    rendered = yaml.safe_dump(
        payload,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    )
    return rendered.encode("utf-8")


def _sha256_file(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()
