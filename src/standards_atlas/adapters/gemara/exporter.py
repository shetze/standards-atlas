"""YAML exporter for Gemara GuidanceCatalog projections."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import yaml

from standards_atlas.adapters.artifact_lineage import write_file_lineage_manifest
from standards_atlas.adapters.gemara.mapper import GemaraGuidanceMapper
from standards_atlas.application.model import PublicationDocument


class GemaraGuidanceExporter:
    """Export a publication document as deterministic Gemara YAML."""

    def __init__(self, mapper: GemaraGuidanceMapper | None = None) -> None:
        self._mapper = mapper or GemaraGuidanceMapper()

    def export_document(
        self,
        document: PublicationDocument,
        target: Path,
        *,
        link_targets: Mapping[tuple[str, str], str] | None = None,
    ) -> Path:
        del link_targets
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.render(document), encoding="utf-8")
        write_file_lineage_manifest(
            target,
            document,
            kind="gemara_guidance_export",
            media_type="application/yaml",
        )
        return target

    def render(self, document: PublicationDocument) -> str:
        catalog = self._mapper.map(document)
        payload = catalog.model_dump(
            mode="json",
            by_alias=True,
            exclude_none=True,
        )
        return yaml.safe_dump(
            payload,
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False,
        )
