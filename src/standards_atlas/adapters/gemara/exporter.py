"""YAML exporter for Gemara GuidanceCatalog projections."""

from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
from pathlib import Path

import yaml

from standards_atlas.adapters.artifact_lineage import write_file_lineage_manifest
from standards_atlas.adapters.gemara.mapper import GemaraGuidanceMapper
from standards_atlas.adapters.gemara.models import GemaraGuidanceCatalog
from standards_atlas.adapters.gemara.traceability import build_traceability
from standards_atlas.application.model import PublicationDocument
from standards_atlas.shared.artifacts import write_json


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
        catalog = self._mapper.map(document)
        rendered = self._render_catalog(catalog)
        target.write_text(rendered, encoding="utf-8")
        write_json(
            target.with_suffix(target.suffix + ".traceability.json"),
            build_traceability(
                document,
                catalog,
                exported_artifact_sha256=sha256(rendered.encode("utf-8")).hexdigest(),
            ).model_dump(mode="json", exclude_none=True),
        )
        write_file_lineage_manifest(
            target,
            document,
            kind="gemara_guidance_export",
            media_type="application/yaml",
        )
        return target

    def render(self, document: PublicationDocument) -> str:
        return self._render_catalog(self._mapper.map(document))

    @staticmethod
    def _render_catalog(catalog: GemaraGuidanceCatalog) -> str:
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
