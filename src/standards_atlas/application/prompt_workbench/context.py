"""Task-aware assembly of clause context for prompt experiments."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from standards_atlas.application.context.canonical_cbox import canonical_cbox_context
from standards_atlas.application.prompt_workbench.models import (
    AssembledPromptContext,
    ContextVariantDescriptor,
)
from standards_atlas.application.semantic_qualification.clause_access import ClauseDescriptor
from standards_atlas.application.semantic_qualification.context_framing import (
    cbox_frame_key,
    frame_cbox_context,
    list_cbox_frame_policies,
    resolve_cbox_frame_policy,
)
from standards_atlas.application.semantic_qualification.context_projection import (
    render_cbox_context,
)

NONE_CONTEXT = ContextVariantDescriptor(
    id="none",
    description="No context beyond clause content and identity template variables.",
)
STRUCTURAL_CONTEXT_V1 = ContextVariantDescriptor(
    id="structural-context-v1",
    description="Complete deterministic StructuralContext plus compact clause metadata.",
    recommended_tasks=("role-relation-extraction", "role-semantics-presence"),
)
ROUTING_SOURCE_V1 = ContextVariantDescriptor(
    id="routing-source-v1",
    description="Pre-enrichment structural evidence used by context-routing-enrichment.",
    recommended_tasks=("context-routing-enrichment",),
)


def list_context_variants() -> tuple[ContextVariantDescriptor, ...]:
    """Return custom and CBox-backed context variants in stable order."""
    cbox_variants = tuple(
        ContextVariantDescriptor(
            id=cbox_frame_key(policy),
            description=f"Versioned CBox frame {policy.id} v{policy.version}.",
            recommended_tasks=(
                "statement-function-classification",
                "semantic-profile-classification",
            ),
        )
        for policy in list_cbox_frame_policies()
    )
    return (NONE_CONTEXT, *cbox_variants, ROUTING_SOURCE_V1, STRUCTURAL_CONTEXT_V1)


class ClausePromptContextAssembler:
    """Build every supported template value from a canonical clause descriptor."""

    def __init__(self, *, knowledge_domain: str = "functional-safety") -> None:
        if not knowledge_domain.strip():
            raise ValueError("knowledge_domain must not be empty")
        self._knowledge_domain = knowledge_domain

    def assemble(
        self,
        clause: ClauseDescriptor,
        *,
        variant_id: str,
        document_title: str | None = None,
    ) -> AssembledPromptContext:
        variants = {item.id: item for item in list_context_variants()}
        try:
            variant = variants[variant_id]
        except KeyError as exc:
            available = ", ".join(sorted(variants))
            raise ValueError(
                f"unknown prompt context variant {variant_id!r}; available: {available}"
            ) from exc

        canonical = self._canonical_context(clause)
        structural = dict(clause.structural_context or {})
        metadata = self._metadata(clause, document_title=document_title)

        if variant_id == NONE_CONTEXT.id:
            selected: Mapping[str, Any] = {}
            context_text = "No additional contextual evidence is available."
        elif variant_id == STRUCTURAL_CONTEXT_V1.id:
            selected = {"metadata": metadata, "structural_context": structural}
            context_text = _pretty_json(selected)
        elif variant_id == ROUTING_SOURCE_V1.id:
            selected = self._routing_source_context(
                clause,
                document_title=document_title,
                structural=structural,
                subject_context=canonical.get("subject_context"),
            )
            context_text = _pretty_json(selected)
        else:
            framed = frame_cbox_context(
                canonical,
                resolve_cbox_frame_policy(variant_id),
                text=clause.text,
                content_hash=clause.content_hash,
            )
            selected = dict(framed.values)
            context_text = render_cbox_context(framed)

        if variant_id in {STRUCTURAL_CONTEXT_V1.id, ROUTING_SOURCE_V1.id}:
            template_structural_context: Mapping[str, Any] = structural
        else:
            template_structural_context = dict(selected.get("structural_context", {}))

        source_bound = variant_id == "taxonomy-grounded-v1"
        if source_bound:
            # Alternate template variables must not reintroduce excluded fields.
            metadata = {
                key: selected[key]
                for key in (
                    "document_key",
                    "reference",
                    "heading",
                    "clause_type",
                    "canonical_section",
                )
                if key in selected
            }
        if "isolated-v" in variant_id:
            # Explicit isolated frames also constrain alternate template variables.
            metadata = {
                key: value
                for key, value in metadata.items()
                if key in {"document_key", "clause_id", "reference", "clause_reference"}
                or key in selected
            }
        values = {
            "content": clause.text,
            "text": clause.text,
            "content_hash": clause.content_hash,
            "reference": clause.reference,
            "clause_reference": clause.clause_reference,
            "document_key": clause.document_key,
            "clause_id": clause.id,
            "heading": (
                str(selected.get("heading") or "")
                if "isolated-v" in variant_id or source_bound
                else clause.heading or ""
            ),
            "metadata": _compact_json(metadata),
            "structural_context": _compact_json(template_structural_context),
            "context_json": _compact_json(selected),
            "context_text": context_text,
        }
        return AssembledPromptContext(
            variant=variant,
            values=values,
            canonical_context=canonical,
            selected_context=selected,
            context_text=context_text,
        )

    def _canonical_context(self, clause: ClauseDescriptor) -> dict[str, Any]:
        return canonical_cbox_context(clause, knowledge_domain=self._knowledge_domain)

    @staticmethod
    def _metadata(clause: ClauseDescriptor, *, document_title: str | None) -> dict[str, Any]:
        return {
            "document_key": clause.document_key,
            "document_title": document_title,
            "clause_id": clause.id,
            "reference": clause.reference,
            "clause_reference": clause.clause_reference,
            "heading": clause.heading,
            "clause_type": clause.clause_type.value,
            "canonical_section": (
                clause.canonical_section.value if clause.canonical_section is not None else None
            ),
        }

    @staticmethod
    def _routing_source_context(
        clause: ClauseDescriptor,
        *,
        document_title: str | None,
        structural: Mapping[str, Any],
        subject_context: object = None,
    ) -> dict[str, Any]:
        return {
            "document_key": clause.document_key,
            "document_title": document_title,
            "reference": clause.reference,
            "heading": clause.heading,
            "clause_type": clause.clause_type.value,
            "ancestors": list(structural.get("ancestors", ())),
            "scope_mentions": list(structural.get("scope_mentions", ())),
            "scope_edges": list(structural.get("scopes", ())),
            "structural_references": list(structural.get("references", ())),
            "reference_mentions": list(clause.reference_mentions),
            "subject_context": subject_context or {},
        }


def _compact_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _pretty_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
