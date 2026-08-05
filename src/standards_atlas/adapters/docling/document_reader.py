"""Read native Docling JSON into adapter-neutral extraction models."""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from standards_atlas.adapters.docling.errors import DoclingDocumentValidationError
from standards_atlas.adapters.docling.evidence import single_reference as _single_reference
from standards_atlas.adapters.docling.item_mapper import (
    map_items,
    referenced_caption_ids,
)
from standards_atlas.adapters.docling.repairs import merge_orphaned_items, repair_reading_order
from standards_atlas.application.model import ExtractedDocument, ExtractionMetadata
from standards_atlas.domain.model import ArtifactLineage, artifact_reference


class DoclingJsonReader:
    """Interpret persisted native Docling JSON without importing Docling itself."""

    def read(self, source: Path) -> ExtractedDocument:
        """Read a native Docling document in its declared reading order."""
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            message = f"Cannot read Docling JSON {source}: {exc}"
            raise DoclingDocumentValidationError(message) from exc
        if not isinstance(payload, dict):
            raise DoclingDocumentValidationError("Docling JSON must contain an object")

        source_id = _source_id(payload, source)
        indexed = _index_items(payload)
        caption_references = referenced_caption_ids(indexed)
        ordered = [
            item
            for item in _ordered_items(payload, indexed)
            if item.get("self_ref") not in caption_references
        ]
        items = map_items(
            ordered,
            source_id=source_id,
            indexed=indexed,
            pages=payload.get("pages"),
        )
        origin = payload.get("origin") if isinstance(payload.get("origin"), dict) else {}

        metadata = ExtractionMetadata(
            converter="docling",
            source_path=_string_or_none(origin.get("filename")),
        )
        draft = ExtractedDocument(
            source_id=source_id,
            items=tuple(items),
            metadata=metadata,
        )
        source_artifact = artifact_reference(
            "source_document",
            {"source_id": source_id, "source_path": metadata.source_path},
            location=metadata.source_path,
        )
        extraction_artifact = artifact_reference(
            "docling_extraction",
            draft,
            location=str(source),
            media_type="application/json",
        )
        return draft.model_copy(
            update={
                "lineage": ArtifactLineage(
                    artifact=extraction_artifact,
                    derived_from=(source_artifact,),
                )
            }
        )


def _source_id(payload: dict[str, Any], source: Path) -> str:
    name = payload.get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    origin = payload.get("origin")
    if isinstance(origin, dict):
        filename = origin.get("filename")
        if isinstance(filename, str) and filename.strip():
            return Path(filename).stem
    return source.stem


def _index_items(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for collection_name in (
        "texts",
        "tables",
        "pictures",
        "key_value_items",
        "form_items",
        "groups",
    ):
        collection = payload.get(collection_name, [])
        if not isinstance(collection, list):
            continue
        for item in collection:
            if not isinstance(item, dict):
                continue
            reference = item.get("self_ref")
            if isinstance(reference, str):
                result[reference] = item
    return result


def _ordered_items(
    payload: dict[str, Any],
    indexed: dict[str, dict[str, Any]],
) -> Iterable[dict[str, Any]]:
    body = payload.get("body")
    yielded_items: set[str] = set()
    visited_groups: set[str] = set()

    def visit(node: Any, group_path: tuple[str, ...] = ()) -> Iterable[dict[str, Any]]:
        if not isinstance(node, dict):
            return

        reference = node.get("$ref")
        if isinstance(reference, str) and reference in indexed:
            resolved = indexed[reference]
            if _is_group(reference, resolved):
                if reference in visited_groups:
                    return
                visited_groups.add(reference)
                yield from visit(resolved, (*group_path, reference))
                return
            if reference in yielded_items:
                return
            yielded_items.add(reference)
            enriched = dict(resolved)
            enriched["_atlas_group_path"] = group_path
            yield enriched
            return

        children = node.get("children", []) if isinstance(node.get("children"), list) else []
        for child in children:
            yield from visit(child, group_path)

    body_items = list(visit(body)) if isinstance(body, dict) else []
    body_items = repair_reading_order(body_items)

    # Some Docling documents contain content items which are not reachable from
    # the body tree. They still belong to the document, but appending them at the
    # end corrupts reading order when Docling omitted a heading from the body
    # tree. Reinsert only these orphaned items from their page geometry while
    # preserving the declared order of all body-reachable items.
    orphaned_items = [
        _with_group_path(item, indexed)
        for reference, item in indexed.items()
        if not _is_group(reference, item) and reference not in yielded_items
    ]
    yield from merge_orphaned_items(body_items, orphaned_items)


def _is_group(reference: str, item: dict[str, Any]) -> bool:
    if reference.startswith("#/groups/"):
        return True
    label = str(item.get("label", "")).lower()
    return label in {"group", "list", "ordered_list", "unordered_list", "chapter"}


def _with_group_path(raw: dict[str, Any], indexed: dict[str, dict[str, Any]]) -> dict[str, Any]:
    enriched = dict(raw)
    path: list[str] = []
    seen: set[str] = set()
    parent_reference = _single_reference(raw.get("parent"))
    while parent_reference and parent_reference not in seen:
        seen.add(parent_reference)
        parent = indexed.get(parent_reference)
        if parent is None or not _is_group(parent_reference, parent):
            break
        path.append(parent_reference)
        parent_reference = _single_reference(parent.get("parent"))
    enriched["_atlas_group_path"] = tuple(reversed(path))
    return enriched


def _string_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None
