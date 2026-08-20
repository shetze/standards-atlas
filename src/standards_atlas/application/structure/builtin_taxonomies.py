"""Built-in deterministic structural-taxonomy algorithms."""

from __future__ import annotations

from dataclasses import dataclass

from standards_atlas.application.structure.taxonomy_engine import (
    StructuralTaxonomyClassifier,
    StructuralTaxonomyContext,
    StructuralTaxonomyRegistry,
)


@dataclass(frozen=True)
class IecDirectives2Classifier:
    """Classify ISO/IEC-style document elements without LLM inference."""

    taxonomy_id: str = "document.iec-directives-2"
    taxonomy_version: str = "1.0.0"

    def classify(self, context: StructuralTaxonomyContext) -> tuple[str, ...]:
        normalized = context.heading.casefold().strip()
        if context.reference.isalpha() or normalized.startswith("annex "):
            return ("supplementary_elements",)
        if normalized in {"foreword", "introduction"}:
            return ("preliminary_elements",)
        if normalized in {"scope", "normative references", "terms and definitions"}:
            return ("normative_general_elements",)
        if normalized == "bibliography":
            return ("bibliography",)
        if context.reference and context.reference[0].isdigit():
            return ("normative_technical_elements",)
        return ()


def builtin_structural_taxonomy_registry() -> StructuralTaxonomyRegistry:
    """Return the registry of algorithms shipped with Standards Atlas."""

    classifiers: tuple[StructuralTaxonomyClassifier, ...] = (IecDirectives2Classifier(),)
    return StructuralTaxonomyRegistry(classifiers)
