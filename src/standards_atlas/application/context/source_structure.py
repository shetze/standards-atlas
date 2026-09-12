"""Project baseline structure and its actual provenance, excluding interpretations."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from standards_atlas.application.model.source_structure import (
    SOURCE_PATHS,
    SourceStructure,
    SourceStructureFact,
)
from standards_atlas.application.schema import require_supported_schema
from standards_atlas.domain.model.clause import Clause
from standards_atlas.domain.model.knowledge_state import GenerationMethod


def project_source_structure(
    clause: Clause,
    *,
    document_key: str,
    content_hash: str,
    ancestors: tuple[Clause, ...] = (),
) -> SourceStructure:
    """Use real parent clauses, not interpreted routing or subject-context ancestors."""
    baseline = clause.baseline.model_dump(
        mode="json",
        include={
            "heading": True,
            "parent_id": True,
            "structural_profile": {
                "canonical_section",
                "document_categories",
                "domain_categories",
                "semantic_sections",
                "annex_status",
            },
            "structural_context": {"node_kind", "child_clause_ids"},
        },
    )
    facts = []
    for field, path in SOURCE_PATHS.items():
        if field == "ancestor_heading":
            continue
        value: Any = clause.clause_type.value if field == "clause_type" else baseline
        if field != "clause_type":
            for part in path.split(".")[1:]:
                value = value.get(part) if isinstance(value, dict) else None
        if field == "parent_id":
            value = clause.parent_id.value if clause.parent_id else None
        facts.append(_source_fact(clause, field=field, value=value))
    for distance, parent in enumerate(ancestors, start=1):
        facts.append(
            _source_fact(parent, field="ancestor_heading", value=parent.heading, distance=distance)
        )
    return SourceStructure(
        document_key=document_key,
        clause_id=clause.id.value,
        reference=clause.reference.clause,
        content_hash=content_hash,
        facts=tuple(facts),
    )


def _source_fact(
    clause: Clause,
    *,
    field: str,
    value: Any,
    distance: int = 0,
) -> SourceStructureFact:
    path = SOURCE_PATHS[field]
    provenance = clause.provenance
    confirmed = [
        item
        for item in provenance.confirmed_attributes
        if path == item.path or path.startswith(item.path + ".")
    ]
    generated = [
        item
        for item in provenance.generated_attributes
        if path == item.path or path.startswith(item.path + ".")
    ]
    metadata: dict[str, Any] = {}
    if confirmed:
        source = max(confirmed, key=lambda item: len(item.path))
        metadata.update(origin="confirmed", authority=source.authority)
    elif generated:
        source = max(generated, key=lambda item: len(item.path))
        if source.method not in {
            GenerationMethod.DETERMINISTIC,
            GenerationMethod.SOURCE_EXTRACTION,
        }:
            # Even an LLM value stored under baseline must not become independent source truth.
            metadata.update(origin="excluded")
            value = None
        elif source.availability != "known":
            metadata.update(origin="unavailable")
            value = None
        else:
            metadata.update(
                origin=source.method.value,
                generator=source.generator,
                evidence=source.evidence,
            )
    # A generated descendant cannot confirm its parent collection. Exclude the
    # complete observed collection if any child is interpreted or unavailable.
    children = [
        item for item in provenance.generated_attributes if item.path.startswith(path + ".")
    ]
    if not confirmed and any(
        item.method not in {GenerationMethod.DETERMINISTIC, GenerationMethod.SOURCE_EXTRACTION}
        or item.availability != "known"
        for item in children
    ):
        metadata = {"origin": "excluded"}
        value = None
    return SourceStructureFact(
        field=field,
        value=value,
        source_clause_id=clause.id.value,
        source_reference=clause.reference.clause,
        source_path=path,
        distance=distance,
        **metadata,
    )


def read_source_structure(
    context: Mapping[str, Any],
    *,
    text: str,
    content_hash: str,
) -> SourceStructure:
    """Explicit read boundary for canonical context and historical heading/title inputs.

    Old archives carry values but no structural authority. They remain unattributed.
    No fields under semantic/subject_context/context_routing/attribute_sources are read.
    """
    if context.get("source_structure") is not None:
        require_supported_schema(
            "source-structure",
            context["source_structure"].get("schema_version"),
        )
        source = SourceStructure.model_validate(context["source_structure"])
        if (source.document_key, source.clause_id, source.reference, source.content_hash) != (
            context.get("document_key"),
            context.get("clause_id"),
            str(context.get("reference") or ""),
            content_hash,
        ):
            raise ValueError("source structure identity/content hash does not match the clause")
        for fact in source.facts:
            if (
                fact.distance == 0
                and fact.field in context
                and fact.field in {"heading", "clause_type", "parent_id", "canonical_section"}
                and fact.origin not in {"excluded", "unavailable"}
                and context[fact.field] != fact.value
            ):
                raise ValueError(f"source structure conflicts with canonical context: {fact.field}")
        return source

    clause_id = str(context.get("clause_id") or "")
    reference = str(context.get("reference") or "")
    facts = []
    structural = context.get("structural_context")
    structural = structural if isinstance(structural, Mapping) else {}
    for field in SOURCE_PATHS:
        if field == "ancestor_heading":
            continue
        if field == "heading":
            # A present canonical key, including None, wins over the legacy alias.
            value = context.get("heading") if "heading" in context else context.get("title")
        elif field in {"node_kind", "child_clause_ids"}:
            value = structural.get(field)
        else:
            value = context.get(field)
        if field in {"document_categories", "domain_categories", "semantic_sections"}:
            value = _clean_collection(field, value)
        facts.append(
            SourceStructureFact(
                field=field,
                value=value,
                source_clause_id=clause_id,
                source_reference=reference,
                source_path=SOURCE_PATHS[field],
            )
        )
    # canonical ancestor_headings are nearest first; legacy structural_context is root first.
    ancestors = context.get("ancestor_headings")
    if ancestors is None:
        ancestors = list(reversed(structural.get("ancestors") or []))
    for distance, ancestor in enumerate(ancestors, start=1):
        if not isinstance(ancestor, Mapping):
            continue  # No invented source identity for a bare heading string.
        ancestor_id = str(ancestor.get("clause_id") or "")
        if not ancestor_id:
            continue
        value = ancestor.get("heading") if "heading" in ancestor else ancestor.get("title")
        facts.append(
            SourceStructureFact(
                field="ancestor_heading",
                value=value,
                source_clause_id=ancestor_id,
                source_reference=str(ancestor.get("reference") or ""),
                source_path="baseline.heading",
                distance=distance,
            )
        )
    return SourceStructure(
        document_key=str(context.get("document_key") or ""),
        clause_id=clause_id,
        reference=reference,
        content_hash=content_hash,
        origin="legacy-context",
        facts=tuple(facts),
    )


def _clean_collection(field: str, value: Any) -> list | None:
    """Preserve only structural fields; never copy arbitrary attached interpretations."""
    if value is None:
        return None
    if not isinstance(value, (tuple, list)):
        raise ValueError("structural collections must be lists, not implicit empty values")
    keys = (
        ("label", "role", "start_offset", "end_offset")
        if field == "semantic_sections"
        else ("taxonomy", "version", "category")
    )
    return [
        {key: item[key] for key in keys if key in item} if isinstance(item, Mapping) else item
        for item in value
        if isinstance(item, (str, Mapping))
    ]
