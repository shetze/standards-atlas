"""Versioned public semantic-tag codec for AtlasData TOC records."""

from __future__ import annotations

from standards_atlas.application.ontology import ResourceOntologyDefinitionRepository
from standards_atlas.application.semantic_classification import (
    ResourceSemanticProfileRepository,
    SemanticProfile,
)
from standards_atlas.domain.model import NormativeStatus, SemanticClassification

CURRENT_SEMANTIC_PROFILE = "functional-safety:1.0.0"
_DOCUMENT_STRUCTURE_CODES = {
    "front_matter": "FMT",
    "foreword": "FRW",
    "introduction": "INT",
    "scope": "SCP",
    "references": "REF",
    "terminology": "TRM",
    "body": "BDY",
    "annex": "ANX",
    "bibliography": "BIB",
    "back_matter": "BMT",
}
_NORMATIVE_STATUS_CODES = {
    "normative": "NRM",
    "informative": "INF",
    "mixed": "MIX",
    "unspecified": "UNS",
    "not_applicable": "NAP",
}


def canonical_semantic_profile(reference: str) -> str:
    """Validate and return one canonical semantic-profile reference."""
    profile_id, separator, version = reference.rpartition(":")
    if not separator or not profile_id or not version:
        raise ValueError(f"Invalid semantic profile reference: {reference!r}")
    try:
        ResourceSemanticProfileRepository().load(profile_id, version)
    except FileNotFoundError as exc:
        raise ValueError(f"Unsupported semantic profile: {reference!r}") from exc
    return reference


def load_semantic_profile(reference: str) -> SemanticProfile:
    """Load the profile declared by AtlasData."""
    canonical = canonical_semantic_profile(reference)
    profile_id, version = canonical.rsplit(":", 1)
    return ResourceSemanticProfileRepository().load(profile_id, version)


def is_supported_semantic_profile(reference: str) -> bool:
    """Return whether an AtlasData semantic profile reference is supported."""
    try:
        canonical_semantic_profile(reference)
    except (FileNotFoundError, ValueError):
        return False
    return True


def _semantic_codes(profile: SemanticProfile) -> dict[str, dict[str, str]]:
    repository = ResourceOntologyDefinitionRepository()
    result = {
        dimension: repository.load(reference.id, reference.version).codes
        for dimension, reference in profile.dimensions.items()
    }
    result["document_structure"] = _DOCUMENT_STRUCTURE_CODES
    result["normative_status"] = _NORMATIVE_STATUS_CODES
    return result


def encode_semantic_tags(
    classification: SemanticClassification,
    *,
    semantic_profile: str = CURRENT_SEMANTIC_PROFILE,
) -> tuple[str, ...]:
    """Encode one accepted classification using the declared semantic profile."""
    codes = _semantic_codes(load_semantic_profile(semantic_profile))
    tags: list[str] = []

    if classification.statement_functions:
        primary = classification.statement_functions[0]
        tags.append(f"SP-{codes['statement_functions'][primary.value]}")
        tags.extend(
            f"SS-{codes['statement_functions'][value.value]}"
            for value in classification.statement_functions[1:]
        )

    tags.extend(
        f"KK-{codes['knowledge_kinds'][value.value]}" for value in classification.knowledge_kinds
    )
    tags.extend(
        f"PF-{codes['process_functions'][value.value]}"
        for value in classification.process_functions
    )
    tags.extend(
        f"AF-{codes['applicability_functions'][value.value]}"
        for value in classification.applicability_functions
    )
    tags.extend(
        f"RR-{codes['role_relation_types'][value.value]}"
        for value in classification.role_relation_types
        if "role_relation_types" in codes
    )

    if classification.document_structure is not None:
        structure = classification.document_structure.category.value
        if structure in codes.get("document_structure", {}):
            tags.append(f"DS-{codes['document_structure'][structure]}")

    if (
        classification.normative_status is not NormativeStatus.UNSPECIFIED
        and classification.normative_status.value in codes.get("normative_status", {})
    ):
        tags.append(f"NS-{codes['normative_status'][classification.normative_status.value]}")

    return tuple(tags)


def decode_semantic_tags(
    tags: tuple[str, ...],
    *,
    semantic_profile: str,
) -> dict[str, tuple[str, ...]]:
    """Decode public taxonomy tags using the declared semantic profile."""
    codes = _semantic_codes(load_semantic_profile(semantic_profile))
    reverse = {
        dimension: {code: value for value, code in values.items()}
        for dimension, values in codes.items()
    }
    result: dict[str, list[str]] = {
        "primary_statement_function": [],
        "secondary_statement_functions": [],
        "knowledge_kinds": [],
        "process_functions": [],
        "applicability_functions": [],
        "role_relation_types": [],
        "document_structure": [],
        "normative_status": [],
    }
    namespaces = {
        "SP": ("statement_functions", "primary_statement_function"),
        "SS": ("statement_functions", "secondary_statement_functions"),
        "KK": ("knowledge_kinds", "knowledge_kinds"),
        "PF": ("process_functions", "process_functions"),
        "AF": ("applicability_functions", "applicability_functions"),
        "RR": ("role_relation_types", "role_relation_types"),
        "RF": ("responsibility_functions", "role_relation_types"),
        "DS": ("document_structure", "document_structure"),
        "NS": ("normative_status", "normative_status"),
    }

    for tag in tags:
        namespace, separator, code = tag.partition("-")
        if not separator or namespace not in namespaces:
            continue
        dimension, target = namespaces[namespace]
        value = reverse.get(dimension, {}).get(code)
        if value is not None:
            result[target].append(value)

    return {key: tuple(values) for key, values in result.items()}
