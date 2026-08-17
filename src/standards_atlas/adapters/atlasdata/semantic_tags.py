"""Versioned public semantic-tag codec for AtlasData TOC records."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from standards_atlas.domain.model import NormativeStatus, SemanticClassification

PROFILE_PREFIX = "statement-function-classification:"


def _taxonomy(version: str) -> dict[str, Any]:
    root = (
        Path(__file__).parents[2]
        / "resources"
        / "semantic"
        / "tasks"
        / "statement-function-classification"
        / version
    )
    return yaml.safe_load((root / "taxonomy.yaml").read_text(encoding="utf-8")) or {}


def encode_semantic_tags(
    classification: SemanticClassification,
    *,
    version: str,
) -> tuple[str, ...]:
    """Encode one accepted classification into stable public taxonomy tags."""
    codes = _taxonomy(version)["semantic_codes"]
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
        f"RF-{codes['responsibility_functions'][value.value]}"
        for value in classification.responsibility_functions
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
    version: str,
) -> dict[str, tuple[str, ...]]:
    """Decode public taxonomy tags using the declared semantic profile."""
    codes = _taxonomy(version)["semantic_codes"]
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
        "responsibility_functions": [],
        "document_structure": [],
        "normative_status": [],
    }
    namespaces = {
        "SP": ("statement_functions", "primary_statement_function"),
        "SS": ("statement_functions", "secondary_statement_functions"),
        "KK": ("knowledge_kinds", "knowledge_kinds"),
        "PF": ("process_functions", "process_functions"),
        "AF": ("applicability_functions", "applicability_functions"),
        "RF": ("responsibility_functions", "responsibility_functions"),
        "DS": ("document_structure", "document_structure"),
        "NS": ("normative_status", "normative_status"),
    }

    for tag in tags:
        namespace, separator, code = tag.partition("-")
        if not separator or namespace not in namespaces:
            raise ValueError(f"Unknown semantic tag namespace: {tag!r}")
        dimension, target = namespaces[namespace]
        value = reverse.get(dimension, {}).get(code)
        if value is None:
            raise ValueError(f"Unknown semantic tag for {version}: {tag!r}")
        result[target].append(value)

    return {key: tuple(values) for key, values in result.items()}
