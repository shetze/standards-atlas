"""Deterministic framing of canonical CBox context for prompt consumers.

A frame is an information-selection boundary: it may expose or omit facts that
already exist in the canonical qualification context, but it must not derive new
semantic facts.  Rendering is intentionally kept in a separate module so task-
specific framing can evolve without coupling information selection to prose.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class CBoxFramePolicy:
    """Versioned policy describing which canonical CBox facts are visible."""

    id: str
    version: str
    identity: bool = True
    heading: bool = True
    clause_type: bool = True
    canonical_section: bool = True
    ancestor_identity: bool = True
    ancestor_heading: bool = True
    sibling_position: bool = True
    document_categories: bool = True
    semantic_sections: bool = True
    scope_routing: bool = True
    reference_routing: bool = True
    reference_mentions: bool = True


@dataclass(frozen=True, slots=True)
class FramedCBoxContext:
    """Structured, non-enriching projection of canonical CBox context."""

    policy_id: str
    policy_version: str
    values: Mapping[str, Any]


FULL_CONTEXT_V1 = CBoxFramePolicy(id="full-context", version="1")


def cbox_frame_key(policy: CBoxFramePolicy) -> str:
    """Return the stable external identifier of a CBox frame policy."""
    return f"{policy.id}-v{policy.version}"


_CBOX_FRAME_POLICIES = {cbox_frame_key(FULL_CONTEXT_V1): FULL_CONTEXT_V1}


def resolve_cbox_frame_policy(frame: str) -> CBoxFramePolicy:
    """Resolve a versioned external frame identifier to its policy."""
    try:
        return _CBOX_FRAME_POLICIES[frame]
    except KeyError as exc:
        available = ", ".join(sorted(_CBOX_FRAME_POLICIES))
        raise ValueError(f"unknown CBox frame {frame!r}; available frames: {available}") from exc


def frame_cbox_context(
    context: Mapping[str, Any],
    policy: CBoxFramePolicy = FULL_CONTEXT_V1,
) -> FramedCBoxContext:
    """Select existing CBox facts according to ``policy`` without deriving facts."""
    values: dict[str, Any] = {}

    if policy.identity:
        _copy_if_present(context, values, "document_key")
        _copy_if_present(context, values, "reference")
    if policy.heading:
        _copy_if_present(context, values, "heading")
    if policy.clause_type:
        _copy_if_present(context, values, "clause_type")
    if policy.canonical_section:
        _copy_if_present(context, values, "canonical_section")

    _frame_ancestors(context, values, policy)
    _frame_structural_context(context, values, policy)

    if policy.document_categories:
        _copy_sequence(context, values, "document_categories")
    if policy.semantic_sections:
        _copy_sequence(context, values, "semantic_sections")

    routing = _mapping(context.get("context_routing"))
    framed_routing: dict[str, Any] = {}
    if policy.scope_routing:
        scopes = [_frame_scope(_mapping(item)) for item in _sequence(routing.get("scopes"))]
        scopes = [item for item in scopes if item]
        if scopes:
            framed_routing["scopes"] = scopes
    if policy.reference_routing:
        references = [
            _frame_reference_routing(_mapping(item))
            for item in _sequence(routing.get("references"))
        ]
        references = [item for item in references if item]
        if references:
            framed_routing["references"] = references
    if framed_routing:
        values["context_routing"] = framed_routing

    if policy.reference_mentions:
        mentions = [
            _frame_reference_mention(_mapping(item))
            for item in _sequence(context.get("reference_mentions"))
        ]
        mentions = [item for item in mentions if item]
        if mentions:
            values["reference_mentions"] = mentions

    return FramedCBoxContext(
        policy_id=policy.id,
        policy_version=policy.version,
        values=values,
    )


def _frame_ancestors(
    context: Mapping[str, Any],
    values: dict[str, Any],
    policy: CBoxFramePolicy,
) -> None:
    if not (policy.ancestor_identity or policy.ancestor_heading):
        return
    ancestors = [
        _frame_ancestor(_mapping(item), policy)
        for item in _sequence(context.get("ancestor_headings"))
    ]
    ancestors = [item for item in ancestors if item]
    if ancestors:
        values["ancestor_headings"] = ancestors


def _frame_structural_context(
    context: Mapping[str, Any],
    values: dict[str, Any],
    policy: CBoxFramePolicy,
) -> None:
    structural = _mapping(context.get("structural_context"))
    framed: dict[str, Any] = {}

    if policy.sibling_position:
        sibling = _mapping(structural.get("sibling"))
        framed_sibling = _selected(sibling, "index", "count")
        if framed_sibling:
            framed["sibling"] = framed_sibling

    if policy.ancestor_identity or policy.ancestor_heading:
        ancestors = [
            _frame_ancestor(_mapping(item), policy)
            for item in _sequence(structural.get("ancestors"))
        ]
        ancestors = [item for item in ancestors if item]
        if ancestors:
            framed["ancestors"] = ancestors

    if framed:
        values["structural_context"] = framed


def _frame_ancestor(ancestor: Mapping[str, Any], policy: CBoxFramePolicy) -> dict[str, Any]:
    framed: dict[str, Any] = {}
    if policy.ancestor_identity:
        _copy_if_present(ancestor, framed, "reference")
    if policy.ancestor_heading:
        _copy_if_present(ancestor, framed, "heading")
    return framed


def _frame_scope(scope: Mapping[str, Any]) -> dict[str, Any]:
    framed: dict[str, Any] = {}
    reaches = [
        _selected(_mapping(item), "kind", "document_key", "part", "reference")
        for item in _sequence(scope.get("reaches"))
    ]
    reaches = [item for item in reaches if item]
    if reaches:
        framed["reaches"] = reaches
    for field in ("conditions", "exclusions", "qualifications"):
        items = list(_sequence(scope.get(field)))
        if items:
            framed[field] = items
    return framed


def _frame_reference_routing(routing: Mapping[str, Any]) -> dict[str, Any]:
    framed: dict[str, Any] = {}
    target = _selected(
        _mapping(routing.get("target")),
        "document_key",
        "standard",
        "document",
        "part",
        "clause",
        "reference",
    )
    if target:
        framed["target"] = target
    _copy_if_present(routing, framed, "role")
    return framed


def _frame_reference_mention(mention: Mapping[str, Any]) -> dict[str, Any]:
    framed = _selected(mention, "surface_text", "reference")
    targets = [
        _selected(
            _mapping(item),
            "document_key",
            "standard",
            "document",
            "part",
            "clause",
            "reference",
        )
        for item in _sequence(mention.get("targets"))
    ]
    targets = [item for item in targets if item]
    if targets:
        framed["targets"] = targets
    return framed


def _selected(source: Mapping[str, Any], *keys: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in keys:
        _copy_if_present(source, result, key)
    return result


def _copy_if_present(source: Mapping[str, Any], target: dict[str, Any], key: str) -> None:
    if key in source and source[key] is not None:
        target[key] = source[key]


def _copy_sequence(source: Mapping[str, Any], target: dict[str, Any], key: str) -> None:
    items = list(_sequence(source.get(key)))
    if items:
        target[key] = items


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()
