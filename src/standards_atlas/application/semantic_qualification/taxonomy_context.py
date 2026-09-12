"""Source-only input boundary for the opt-in taxonomy-grounded CBox frame.

This module selects observations, not decision-plan candidates or semantic priors.
Provenance prose, generators and authorities remain in the local canonical audit
context. Only the origin of a selected observation is exposed to the model.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from standards_atlas.application.context.source_structure import read_source_structure
from standards_atlas.application.semantic_qualification.annotations import normalized_content_hash
from standards_atlas.domain.model.structural_profile import SemanticSectionRole

# Versioned by taxonomy-grounded-v1. Distances are real parent links, not positions
# in a possibly sparse list; an omitted immediate parent never promotes a grandparent.
TAXONOMY_MAXIMUM_ANCESTOR_DISTANCE = 4
_LOCAL_FIELDS = frozenset(
    {
        "heading",
        "clause_type",
        "canonical_section",
        "annex_status",
        "node_kind",
        "document_categories",
        "semantic_sections",
    }
)
_SECTION_ROLES = frozenset(item.value for item in SemanticSectionRole)


def select_taxonomy_context(
    context: Mapping[str, Any],
    *,
    text: str | None = None,
    content_hash: str | None = None,
) -> dict[str, Any]:
    """Select source fields, validating content identity when text is available.

    Request builders must supply text and its declared hash. Context-only callers
    can inspect a source contract without text, but do not expose segment offsets
    they cannot validate. Historical contexts remain explicitly unattributed.
    """
    if text is not None:
        actual_hash = normalized_content_hash(text)
        if content_hash is not None and content_hash != actual_hash:
            raise ValueError("content hash does not match the normalized clause text")
    else:
        payload = context.get("source_structure")
        declared = payload.get("content_hash") if isinstance(payload, Mapping) else None
        actual_hash = content_hash or declared or normalized_content_hash("")
    source = read_source_structure(context, text=text or "", content_hash=actual_hash)
    values: dict[str, Any] = {
        "document_key": source.document_key,
        "reference": source.reference,
        "structure_origin": source.origin,
    }
    origins: dict[str, str] = {}
    ancestors = []
    for fact in source.facts:
        if fact.origin in {"excluded", "unavailable"} or fact.value is None:
            continue
        if fact.field == "ancestor_heading":
            if fact.distance <= TAXONOMY_MAXIMUM_ANCESTOR_DISTANCE:
                ancestors.append(
                    {
                        "reference": fact.source_reference,
                        "heading": fact.value,
                        "distance": fact.distance,
                        "origin": fact.origin,
                    }
                )
            continue
        if fact.field not in _LOCAL_FIELDS:
            continue
        value = fact.value
        if fact.field == "document_categories":
            value = _document_categories(value)
        elif fact.field == "semantic_sections":
            value = _semantic_sections(value, text=text)
        if value == []:
            continue  # No structure observation is not an evaluated semantic negative.
        values[fact.field] = value
        origins[fact.field] = fact.origin
    if ancestors:
        values["ancestor_headings"] = sorted(ancestors, key=lambda item: item["distance"])
    if origins:
        values["structure_sources"] = origins
    return values


def _document_categories(items: list[Any]) -> list[dict[str, str]]:
    """Only document-family categories; domain and semantic namespaces are hidden."""
    categories = []
    for item in items:
        if not isinstance(item, Mapping):
            continue  # A bare string has no independently identifiable taxonomy.
        taxonomy, category = item.get("taxonomy"), item.get("category")
        if not (
            isinstance(taxonomy, str)
            and taxonomy.startswith("document.")
            and isinstance(category, str)
            and category.strip()
        ):
            continue
        selected = {"taxonomy": taxonomy, "category": category}
        version = item.get("version")
        if isinstance(version, str) and version.strip():
            selected["version"] = version
        categories.append(selected)
    # Category collections are sets. Storage order is not additional evidence.
    unique = {json.dumps(item, sort_keys=True): item for item in categories}
    return [unique[key] for key in sorted(unique)]


def _semantic_sections(items: list[Any], *, text: str | None) -> list[dict[str, Any]]:
    """Expose labelled ranges only; never replace or truncate the clause content."""
    if text is None:
        return []
    result = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        start, end, label = item.get("start_offset"), item.get("end_offset"), item.get("label")
        if not (
            type(start) is int
            and type(end) is int
            and 0 <= start < end <= len(text)
            and isinstance(label, str)
            and label.strip()
        ):
            continue
        role = item.get("role")
        selected = {"label": label, "start_offset": start, "end_offset": end}
        if isinstance(role, str) and role in _SECTION_ROLES:
            selected["role"] = role
        result.append(selected)
    unique = {json.dumps(item, sort_keys=True): item for item in result}
    return sorted(
        unique.values(),
        key=lambda item: (item["start_offset"], item["end_offset"], item["label"], _json(item)),
    )


def render_taxonomy_context(values: Mapping[str, Any]) -> str:
    """Render only the selected fields; do not derive semantic answers from them."""
    lines = [
        "Source-structure observations (contextual hints, not semantic answer labels).",
        "Confirmed means the source field was confirmed, not that a semantic decision was made.",
        "Unattributed observations have no independent authority; resolve ambiguity from the text.",
        "Enclosing headings describe location; inherited scope is not explicit applicability here.",
    ]
    for field in ("document_key", "reference", "structure_origin"):
        if field in values:
            lines.append(f"{field}: {_json(values[field])}")
    origins = values.get("structure_sources", {})
    for field in sorted(_LOCAL_FIELDS):
        if field in values:
            origin = origins.get(field, "unattributed")
            lines.append(f"{field} [source origin: {origin}]: {_json(values[field])}")
    for parent in values.get("ancestor_headings", ()):
        lines.append(
            f"Enclosing section at distance {parent['distance']} "
            f"[source origin: {parent['origin']}]: "
            f"{_json(parent['reference'])}, {_json(parent['heading'])}"
        )
    return "\n".join(lines)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)
