"""Manifest-only physical AtlasData ownership; never guess parts from filenames."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from standards_atlas.application.catalog.models import StandardCatalog


@dataclass(frozen=True)
class AtlasDataBinding:
    document_key: str
    family_key: str
    source: Path
    selection_part: str | None
    publication_year: int | None
    title: str | None = None

    @property
    def enrichments_path(self) -> Path:
        return self.source.parent / "enrichments" / f"{self.document_key}.yaml"


def atlasdata_bindings(catalog: StandardCatalog, *, root: Path) -> dict[str, AtlasDataBinding]:
    bindings: dict[str, AtlasDataBinding] = {}

    def add(
        key: str,
        family: str,
        source: Path,
        part: str | None,
        year: int | None,
        title: str | None = None,
    ) -> None:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", key) or ".." in key:
            raise ValueError(f"unsafe physical document key: {key!r}")
        if key in bindings:
            raise ValueError(f"duplicate AtlasData binding: {key}")
        bindings[key] = AtlasDataBinding(
            key,
            family,
            (root / source).resolve(),
            part,
            year,
            title,
        )

    for family in catalog.families:
        if family.atlasdata is None:
            continue
        if family.source is not None:
            add(family.key, family.key, family.atlasdata.path, None, family.publication_year)
            continue
        for part in family.parts:
            add(
                part.key,
                family.key,
                family.atlasdata.path,
                part.part,
                part.publication_year or family.publication_year,
                part.title,
            )
            for supplement in part.supplements:
                source = (
                    supplement.atlasdata.path if supplement.atlasdata else family.atlasdata.path
                )
                selection = None if supplement.atlasdata else f"{part.part}-{supplement.supplement}"
                # Supplements are separate publications. An omitted year remains unspecified,
                # not silently inherited from their parent publication.
                add(
                    supplement.key,
                    family.key,
                    source,
                    selection,
                    supplement.publication_year,
                    supplement.title,
                )
    return bindings
