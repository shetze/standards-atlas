"""One canonical projection shared by corpus, workbench and post-import inspection.

Only the accepted EngineeringDocument state is read. Evaluation reports and gold
labels are not consulted. Fingerprints intentionally do not contain rendered prose.
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any

from standards_atlas.application.model.cbox import CBoxAttribute, CBoxEnrichments
from standards_atlas.domain.model.clause import Clause, ClauseEnrichments
from standards_atlas.domain.model.enrichment_patch import SemanticEnrichmentPatch
from standards_atlas.domain.model.knowledge_state import paths_overlap

if TYPE_CHECKING:
    from standards_atlas.application.semantic_qualification.clause_access import ClauseDescriptor

CBOX_CONTRACT_VERSION = "1.0"
CBOX_ATTRIBUTE_PATHS = tuple(
    f"enrichments.semantic.{name}" for name in SemanticEnrichmentPatch.model_fields
) + ("enrichments.subject_context", "enrichments.context_routing")


def context_fingerprint(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def project_clause_enrichments(clause: Clause) -> CBoxEnrichments:
    """Keep explicit False/empty/unknown distinct from untouched defaults.

    A parent confirmation covers its descendants, but a single confirmed child
    does not magically confirm an entire context object. Non-default historical
    values without attribution remain visible as unattributed, never as gold.
    """
    state = clause.enrichments.model_dump(mode="json")
    defaults = ClauseEnrichments().model_dump(mode="json")
    attributes = []
    for path in CBOX_ATTRIBUTE_PATHS:
        value, default = state, defaults
        for part in path.split(".")[1:]:
            value, default = value[part], default[part]
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
        data: dict[str, Any] = {"path": path, "value": value}
        if confirmed:
            data.update(
                availability="known",
                origin="confirmed",
                confirmed=max(confirmed, key=lambda item: len(item.path)),
            )
        elif generated:
            source = max(generated, key=lambda item: len(item.path))
            data.update(availability=source.availability, origin="generated", generated=source)
            if source.availability != "known":
                data["value"] = None
        elif any(
            paths_overlap(path, item.path)
            for item in (*provenance.confirmed_attributes, *provenance.generated_attributes)
        ):
            data.update(availability="partial", origin="partial", value=None)
        elif value != default or provenance.protection(path):
            data.update(availability="known", origin="unattributed")
        else:
            data.update(availability="not_evaluated", origin="not_evaluated", value=None)
        attributes.append(CBoxAttribute(**data))
    return CBoxEnrichments(attributes=tuple(attributes))


def canonical_cbox_context(
    clause: ClauseDescriptor,
    *,
    knowledge_domain: str = "functional-safety",
    ancestor_headings: list[dict] | None = None,
) -> dict[str, Any]:
    """Build auditable context from a fresh canonical descriptor, never old run outputs."""
    structural = dict(clause.structural_context or {})
    if clause.ancestor_headings is not None:
        ancestor_headings = list(clause.ancestor_headings)
    attributes = clause.enrichment_context.attributes

    def effective_context(name: str, fallback: object) -> object:
        match = next((item for item in attributes if item.path == "enrichments." + name), None)
        if match is None:
            return fallback  # compatibility for explicit in-process test descriptors
        return match.value if match.availability == "known" else None

    # Structural priors must not become yesterday's semantic predictions. Source
    # clause_type/profile are carried separately; no semantic-label feedback here.
    return {
        "canonical_cbox_version": CBOX_CONTRACT_VERSION,
        "knowledge_domain": knowledge_domain,
        "document_key": clause.document_key,
        "clause_id": clause.id,
        "reference": clause.clause_reference,
        "heading": clause.heading,
        "parent_id": clause.parent_id,
        "ancestor_headings": (
            ancestor_headings
            if ancestor_headings is not None
            else list(structural.get("ancestors", ()))
        ),
        "structural_roles": [],
        "clause_type": clause.clause_type.value,
        "canonical_section": clause.canonical_section.value if clause.canonical_section else None,
        "document_categories": list(clause.document_categories),
        "domain_categories": list(clause.domain_categories),
        "semantic_sections": [item.model_dump(mode="json") for item in clause.semantic_sections],
        "structural_context": clause.structural_context,
        "reference_mentions": list(clause.reference_mentions),
        "context_routing": effective_context("context_routing", clause.context_routing),
        "subject_context": effective_context("subject_context", clause.subject_context),
        "semantic": {
            item.path.rsplit(".", 1)[-1]: item.value
            for item in attributes
            if item.path.startswith("enrichments.semantic.") and item.availability == "known"
        },
        "attribute_sources": {
            item.path: item.model_dump(mode="json", exclude={"value"}) for item in attributes
        },
        "content_profile": clause.content_profile.value,
        "table_block_count": clause.table_block_count,
    }
