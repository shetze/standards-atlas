"""Deterministic natural-language projection of CBox context for LLM prompts.

Qualification datasets keep their complete structured context for auditability and
routing.  Prompt consumers should not have to infer semantics from that storage
shape, so this module renders only stable, task-relevant contextual evidence.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def project_cbox_context(context: Mapping[str, Any]) -> str:
    """Render stable structural and contextual-routing evidence as concise prose.

    The projection deliberately excludes workflow bookkeeping, opaque clause ids,
    eligibility data, content-profile statistics, and semantic classification
    targets such as ``structural_roles``.  Missing information is omitted rather
    than represented as empty JSON structures.
    """
    lines: list[str] = []

    document_key = _text(context.get("document_key"))
    reference = _text(context.get("reference"))
    heading = _text(context.get("heading"))
    clause_type = _text(context.get("clause_type"))
    canonical_section = _text(context.get("canonical_section"))

    identity = _join_identity(document_key, reference)
    if identity and heading:
        lines.append(f'This clause is {identity}, "{heading}".')
    elif identity:
        lines.append(f"This clause is {identity}.")
    elif heading:
        lines.append(f'The clause heading is "{heading}".')

    if clause_type:
        sentence = f"It is classified structurally as {clause_type.replace('_', ' ')}"
        if canonical_section:
            sentence += f" in the {canonical_section.replace('_', ' ')} section"
        lines.append(sentence + ".")
    elif canonical_section:
        lines.append(
            f"It occurs in the {canonical_section.replace('_', ' ')} section of the document."
        )

    ancestors = _ancestor_entries(context)
    if ancestors:
        immediate = ancestors[0]
        immediate_label = _ancestor_label(immediate)
        if immediate_label:
            lines.append(f"Its immediate enclosing section is {immediate_label}.")
        higher = [_ancestor_label(item) for item in ancestors[1:]]
        higher = [item for item in higher if item]
        if higher:
            lines.append("Higher enclosing sections are " + "; then ".join(higher) + ".")

    structural = _mapping(context.get("structural_context"))
    sibling = _mapping(structural.get("sibling"))
    if sibling:
        index = _int(sibling.get("index"))
        count = _int(sibling.get("count"))
        if index is not None and count is not None and count > 0:
            lines.append(
                f"Within its immediate parent, it is clause {index + 1} of {count} sibling clauses."
            )

    document_categories = _strings(context.get("document_categories"))
    if document_categories:
        lines.append(
            "Document-structure categories: "
            + ", ".join(item.replace("_", " ") for item in document_categories)
            + "."
        )

    semantic_sections = _semantic_section_labels(context.get("semantic_sections"))
    if semantic_sections:
        lines.append("Semantic section context: " + ", ".join(semantic_sections) + ".")

    routing = _mapping(context.get("context_routing"))
    lines.extend(_project_scope_routing(routing.get("scopes")))
    lines.extend(_project_reference_routing(routing.get("references")))

    # Deterministic reference evidence remains useful when no interpreted routing
    # is available yet, but expose readable target/surface values only.
    if not _sequence(routing.get("references")):
        references = _readable_reference_mentions(context.get("reference_mentions"))
        if references:
            lines.append("The clause contains references to " + "; ".join(references) + ".")

    return "\n".join(lines) if lines else "No additional contextual evidence is available."


def _join_identity(document_key: str | None, reference: str | None) -> str | None:
    if document_key and reference:
        return f"{document_key} {reference}"
    return document_key or reference


def _ancestor_entries(context: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    raw = _sequence(context.get("ancestor_headings"))
    entries = [_mapping(item) for item in raw]
    entries = [item for item in entries if item]
    if entries:
        return entries
    structural = _mapping(context.get("structural_context"))
    return [
        item
        for item in (_mapping(value) for value in _sequence(structural.get("ancestors")))
        if item
    ]


def _ancestor_label(ancestor: Mapping[str, Any]) -> str | None:
    reference = _text(ancestor.get("reference"))
    heading = _text(ancestor.get("heading"))
    if reference and heading:
        return f'{reference}, "{heading}"'
    return reference or (f'"{heading}"' if heading else None)


def _semantic_section_labels(value: Any) -> list[str]:
    labels: list[str] = []
    for item in _sequence(value):
        if isinstance(item, str) and item.strip():
            labels.append(item.replace("_", " "))
            continue
        mapping = _mapping(item)
        for key in ("section", "category", "value", "name"):
            label = _text(mapping.get(key))
            if label:
                labels.append(label.replace("_", " "))
                break
    return labels


def _project_scope_routing(value: Any) -> list[str]:
    lines: list[str] = []
    for scope in (_mapping(item) for item in _sequence(value)):
        if not scope:
            continue
        reaches = [_scope_reach_text(_mapping(item)) for item in _sequence(scope.get("reaches"))]
        reaches = [item for item in reaches if item]
        if reaches:
            lines.append("Scope routing: this declaration governs " + "; ".join(reaches) + ".")
        for field, label in (
            ("conditions", "Scope conditions"),
            ("exclusions", "Scope exclusions"),
            ("qualifications", "Scope qualifications"),
        ):
            items = _strings(scope.get(field))
            if items:
                lines.append(f"{label}: " + "; ".join(items) + ".")
    return lines


def _scope_reach_text(reach: Mapping[str, Any]) -> str | None:
    kind = _text(reach.get("kind"))
    document_key = _text(reach.get("document_key"))
    part = _text(reach.get("part"))
    reference = _text(reach.get("reference"))
    if kind == "document":
        return f"document {document_key}" if document_key else "the source document"
    if kind == "part":
        if document_key and part:
            return f"part {part} of {document_key}"
        if part:
            return f"part {part} of the source document"
        return "the declared document part"
    if kind in {"subtree", "clause"}:
        noun = "the subtree rooted at" if kind == "subtree" else "clause"
        target = " ".join(item for item in (document_key, reference) if item)
        return f"{noun} {target}" if target else f"a {kind} target"
    return kind.replace("_", " ") if kind else None


def _project_reference_routing(value: Any) -> list[str]:
    lines: list[str] = []
    for routing in (_mapping(item) for item in _sequence(value)):
        if not routing:
            continue
        target = _mapping(routing.get("target"))
        target_text = _reference_target_text(target)
        role = _text(routing.get("role"))
        if target_text and role:
            lines.append(
                f"Reference routing: {target_text} {role.replace('_', ' ')} for this clause."
            )
        elif target_text:
            lines.append(f"Reference routing: this clause refers to {target_text}.")
    return lines


def _readable_reference_mentions(value: Any) -> list[str]:
    result: list[str] = []
    for mention in (_mapping(item) for item in _sequence(value)):
        if not mention:
            continue
        rendered_targets = [
            rendered
            for item in _sequence(mention.get("targets"))
            if (rendered := _reference_target_text(_mapping(item)))
        ]
        if not rendered_targets:
            fallback = _text(mention.get("surface_text")) or _text(mention.get("reference"))
            rendered_targets = [fallback] if fallback else []
        for rendered in rendered_targets:
            if rendered not in result:
                result.append(rendered)
    return result


def _reference_target_text(target: Mapping[str, Any]) -> str | None:
    if not target:
        return None
    document = (
        _text(target.get("document_key"))
        or _text(target.get("standard"))
        or _text(target.get("document"))
    )
    part = _text(target.get("part"))
    clause = _text(target.get("clause")) or _text(target.get("reference"))
    bits = [item for item in (document, f"part {part}" if part else None, clause) if item]
    return " ".join(bits) if bits else None


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()


def _strings(value: Any) -> list[str]:
    return [text for item in _sequence(value) if (text := _text(item))]


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
