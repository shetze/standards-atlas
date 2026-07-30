"""Deterministic multidimensional semantic classification."""

from __future__ import annotations

import re
from dataclasses import dataclass

from standards_atlas.domain.model import (
    DocumentStructure,
    DocumentStructureClassification,
    DomainFunctionClassification,
    NormativeStatus,
    SemanticClassification,
    StatementFunction,
)


@dataclass(frozen=True)
class SemanticEvidence:
    kind: str
    value: str
    confidence: float


@dataclass(frozen=True)
class SemanticClassificationContext:
    reference: str
    heading: str
    text: str = ""
    document_family: str = "iso_iec_standard"
    knowledge_domain: str | None = None
    taxonomy_version: str = "1.0.0"
    ancestor_structures: tuple[DocumentStructure, ...] = ()
    annex_status: NormativeStatus = NormativeStatus.UNSPECIFIED
    document_title: str = ""
    document_normative_status: NormativeStatus = NormativeStatus.UNSPECIFIED


@dataclass(frozen=True)
class SemanticClassificationResult:
    classification: SemanticClassification
    confidence: float = 0.0
    evidence: tuple[SemanticEvidence, ...] = ()
    classifier: str = "deterministic"


_STRUCTURE_RULES = (
    (DocumentStructure.FOREWORD, re.compile(r"^(?:european\s+)?foreword$", re.I)),
    (DocumentStructure.INTRODUCTION, re.compile(r"^introduction$", re.I)),
    (DocumentStructure.SCOPE, re.compile(r"^(?:general\s+)?scope$", re.I)),
    (DocumentStructure.REFERENCES, re.compile(r"^(?:normative\s+)?references?$", re.I)),
    (
        DocumentStructure.TERMINOLOGY,
        re.compile(r"^(?:terms?.*definitions?|definitions?|abbreviations?|symbols?)$", re.I),
    ),
    (DocumentStructure.BIBLIOGRAPHY, re.compile(r"^bibliography(?:\s+of\s+.+)?$", re.I)),
)

_DOMAIN_PATTERNS = (
    ("objectives", re.compile(r"\bobjectives?\b", re.I)),
    ("requirements", re.compile(r"\brequirements?\b", re.I)),
    ("inputs", re.compile(r"\binputs?\b", re.I)),
    ("outputs", re.compile(r"\boutputs?\b", re.I)),
    ("work_products", re.compile(r"\b(?:work\s+products?|deliverables?)\b", re.I)),
    ("verification", re.compile(r"\bverification\b", re.I)),
    ("validation", re.compile(r"\bvalidation\b", re.I)),
    ("assessment", re.compile(r"\bassessment\b", re.I)),
    ("compliance", re.compile(r"\bcompliance\b", re.I)),
    ("conformance", re.compile(r"\bconformance\b", re.I)),
)


class SemanticClassifier:
    """Classify independent semantic dimensions without flattening them."""

    def classify(self, context: SemanticClassificationContext) -> SemanticClassificationResult:
        return self.classify_deterministically(context)

    def classify_deterministically(
        self, context: SemanticClassificationContext
    ) -> SemanticClassificationResult:
        heading = _normalize_heading(context.heading)
        evidence: list[SemanticEvidence] = []
        structure = self._structure(context, heading, evidence)
        statement_functions = self._statement_functions(
            "\n".join(value for value in (context.heading, context.text) if value), evidence
        )
        domain_functions = self._domain_functions(context, heading, evidence)
        normative_status = self._normative_status(
            context, structure.category, statement_functions, evidence
        )
        confidence = max((item.confidence for item in evidence), default=0.0)
        return SemanticClassificationResult(
            classification=SemanticClassification(
                statement_functions=statement_functions,
                document_structure=structure,
                normative_status=normative_status,
                domain_functions=domain_functions,
            ),
            confidence=confidence,
            evidence=tuple(evidence),
        )

    @staticmethod
    def _normative_status(context, structure, statement_functions, evidence):
        # Notes, examples and guidelines never carry normative provisions.
        informative_functions = {
            StatementFunction.NOTE,
            StatementFunction.EXAMPLE,
            StatementFunction.GUIDELINE,
        }
        if informative_functions.intersection(statement_functions):
            evidence.append(
                SemanticEvidence("informative_statement_function", "semantic_role", 1.0)
            )
            return NormativeStatus.INFORMATIVE

        # Explicit annex declarations govern the complete annex subtree.
        if context.annex_status is not NormativeStatus.UNSPECIFIED:
            evidence.append(
                SemanticEvidence("annex_normative_status", context.annex_status.value, 1.0)
            )
            return context.annex_status

        if structure in {
            DocumentStructure.FOREWORD,
            DocumentStructure.INTRODUCTION,
            DocumentStructure.BIBLIOGRAPHY,
            DocumentStructure.FRONT_MATTER,
            DocumentStructure.BACK_MATTER,
        }:
            evidence.append(
                SemanticEvidence("informative_document_structure", structure.value, 1.0)
            )
            return NormativeStatus.INFORMATIVE

        document_status = context.document_normative_status
        if document_status is NormativeStatus.UNSPECIFIED:
            document_status = _document_normative_status(context.document_title)
        if document_status is not NormativeStatus.UNSPECIFIED:
            evidence.append(
                SemanticEvidence("document_normative_status", document_status.value, 0.98)
            )
            return document_status

        # Annexes without an explicit marker remain genuinely undecidable.
        if structure is DocumentStructure.ANNEX:
            return NormativeStatus.UNSPECIFIED

        # ISO/IEC standards use the main body as the normative default.
        if context.document_family == "iso_iec_standard":
            evidence.append(SemanticEvidence("standard_body_default", "normative", 0.9))
            return NormativeStatus.NORMATIVE
        return NormativeStatus.UNSPECIFIED

    @staticmethod
    def _structure(context, heading, evidence):
        if _is_annex_heading(heading) or _is_annex_reference(context.reference):
            evidence.append(SemanticEvidence("annex_reference", context.reference, 1.0))
            return DocumentStructureClassification(
                family=context.document_family,
                category=DocumentStructure.ANNEX,
                annex_identifier=context.reference.split(".", 1)[0],
            )
        for category, pattern in _STRUCTURE_RULES:
            if pattern.fullmatch(heading):
                evidence.append(SemanticEvidence("heading_structure", category.value, 1.0))
                return DocumentStructureClassification(
                    family=context.document_family, category=category
                )
        if DocumentStructure.TERMINOLOGY in context.ancestor_structures:
            return DocumentStructureClassification(
                family=context.document_family, category=DocumentStructure.TERMINOLOGY
            )
        return DocumentStructureClassification(
            family=context.document_family, category=DocumentStructure.BODY
        )

    @staticmethod
    def _statement_functions(text, evidence):
        text = text.strip()
        functions: list[StatementFunction] = []
        prefix_patterns = (
            (StatementFunction.NOTE, r"^\s*note(?:\s+\d+)?\s*[:.—-]"),
            (StatementFunction.EXAMPLE, r"^\s*example(?:\s+\d+)?\s*[:.—-]"),
            (StatementFunction.GUIDELINE, r"^\s*guidelines?\b"),
        )
        for function, pattern in prefix_patterns:
            if re.search(pattern, text, re.I):
                functions.append(function)
                evidence.append(SemanticEvidence("statement_marker", function.value, 1.0))

        patterns = (
            (StatementFunction.PROHIBITION, r"\bshall\s+not\b"),
            (StatementFunction.REQUIREMENT, r"\bshall\b"),
            (StatementFunction.RECOMMENDATION, r"\bshould\b"),
            (StatementFunction.PERMISSION, r"\bmay\b"),
        )
        for function, pattern in patterns:
            if re.search(pattern, text, re.I):
                functions.append(function)
                evidence.append(SemanticEvidence("modal_verb", function.value, 0.95))
        return tuple(dict.fromkeys(functions))

    @staticmethod
    def _domain_functions(context, heading, evidence):
        if not context.knowledge_domain:
            return ()
        functions = tuple(name for name, pattern in _DOMAIN_PATTERNS if pattern.search(heading))
        if functions:
            evidence.append(SemanticEvidence("heading_domain_function", ",".join(functions), 0.86))
        return (
            DomainFunctionClassification(
                knowledge_domain=context.knowledge_domain,
                taxonomy_version=context.taxonomy_version,
                functions=functions,
            ),
        )


def _normalize_heading(value: str) -> str:
    heading = re.sub(r"\s+", " ", value).strip()
    heading = re.sub(r"^(?:0\.\d+(?:\.\d+)*|[1-9]\d*(?:\.\d+)*|[A-Z](?:\.\d+)*)\s+", "", heading)
    return heading.strip(" :-")


def _is_annex_heading(heading: str) -> bool:
    return re.match(r"^annex\s+[A-Z]{1,2}\b", heading, re.I) is not None


def _is_annex_reference(reference: str) -> bool:
    return re.fullmatch(r"[A-Z]{1,2}(?:\.\d+)*", reference) is not None


def _document_normative_status(title: str) -> NormativeStatus:
    normalized = re.sub(r"\s+", " ", title).strip()
    if not normalized:
        return NormativeStatus.UNSPECIFIED
    if re.search(r"\bguidelines?\s+(?:on|for|to)\b", normalized, re.I):
        return NormativeStatus.INFORMATIVE
    return NormativeStatus.UNSPECIFIED
