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
        statement_functions = self._statement_functions(context.text, evidence)
        domain_functions = self._domain_functions(context, heading, evidence)
        confidence = max((item.confidence for item in evidence), default=0.0)
        normative_status = self._normative_status(context, structure, evidence)
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
    def _normative_status(context, structure, evidence):
        if structure.category is DocumentStructure.ANNEX:
            annex_status = NormativeStatus(context.annex_status)
            if annex_status is not NormativeStatus.UNSPECIFIED:
                evidence.append(SemanticEvidence("explicit_annex_status", annex_status.value, 1.0))
                return annex_status
            heading_status = _explicit_normative_status(context.heading)
            if heading_status is not None:
                evidence.append(SemanticEvidence("annex_heading_status", heading_status.value, 1.0))
                return heading_status
            return NormativeStatus.UNSPECIFIED

        if structure.category in {
            DocumentStructure.FRONT_MATTER,
            DocumentStructure.FOREWORD,
            DocumentStructure.INTRODUCTION,
            DocumentStructure.BIBLIOGRAPHY,
            DocumentStructure.BACK_MATTER,
        }:
            evidence.append(SemanticEvidence("structural_normative_default", "informative", 0.95))
            return NormativeStatus.INFORMATIVE

        evidence.append(SemanticEvidence("main_body_normative_default", "normative", 0.95))
        return NormativeStatus.NORMATIVE

    @staticmethod
    def _statement_functions(text, evidence):
        text = text.strip()
        functions: list[StatementFunction] = []
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


def _explicit_normative_status(value: str) -> NormativeStatus | None:
    match = re.search(r"\b(normative|informative)\b", value, re.I)
    if match is None:
        return None
    return NormativeStatus(match.group(1).lower())
