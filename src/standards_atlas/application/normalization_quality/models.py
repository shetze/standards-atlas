"""Models for observational LLM review of normalized EngineeringDocument clauses."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class QualityStatus(StrEnum):
    OK = "ok"
    SUSPICIOUS = "suspicious"


class FindingType(StrEnum):
    HYPHENATION_ERROR = "hyphenation_error"
    WORD_BOUNDARY_ERROR = "word_boundary_error"
    BLOCK_SPLIT_ERROR = "block_split_error"
    BLOCK_MERGE_ERROR = "block_merge_error"
    READING_ORDER_ERROR = "reading_order_error"
    DUPLICATE_CONTENT = "duplicate_content"
    PAGE_FURNITURE_LEAK = "page_furniture_leak"
    LIST_STRUCTURE_ERROR = "list_structure_error"
    TABLE_TEXT_LEAK = "table_text_leak"
    INCOMPLETE_FRAGMENT = "incomplete_fragment"
    OTHER = "other"


class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True)
class NormalizationQualityFinding:
    type: FindingType
    severity: Severity
    evidence: str
    explanation: str
    confidence: float


@dataclass(frozen=True)
class NormalizationQualityCase:
    example_id: str
    document_key: str
    reference: str
    title: str | None
    text: str
    status: QualityStatus | None
    findings: tuple[NormalizationQualityFinding, ...]
    model_id: str
    model_ref: str
    provider: str
    duration_ms: int
    cached: bool
    input_hash: str
    raw_response_hash: str
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.error is None and self.status is not None


@dataclass(frozen=True)
class NormalizationQualityRun:
    corpus_path: str
    prompt_version: str
    model_id: str
    model_ref: str
    provider: str
    cases: tuple[NormalizationQualityCase, ...]

    @property
    def reviewed(self) -> int:
        return sum(case.succeeded for case in self.cases)

    @property
    def suspicious(self) -> int:
        return sum(case.status is QualityStatus.SUSPICIOUS for case in self.cases)

    @property
    def failed(self) -> int:
        return sum(not case.succeeded for case in self.cases)

    @property
    def cached(self) -> int:
        return sum(case.cached for case in self.cases if case.succeeded)

    def finding_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for case in self.cases:
            for finding in case.findings:
                counts[finding.type.value] = counts.get(finding.type.value, 0) + 1
        return dict(sorted(counts.items()))

    def to_dict(self) -> dict[str, Any]:
        return {
            "corpus_path": self.corpus_path,
            "prompt_version": self.prompt_version,
            "model_id": self.model_id,
            "model_ref": self.model_ref,
            "provider": self.provider,
            "summary": {
                "cases": len(self.cases),
                "reviewed": self.reviewed,
                "ok": self.reviewed - self.suspicious,
                "suspicious": self.suspicious,
                "failed": self.failed,
                "cached": self.cached,
                "finding_types": self.finding_counts(),
            },
            "cases": [_case_dict(case) for case in self.cases],
        }


def _case_dict(case: NormalizationQualityCase) -> dict[str, Any]:
    return {
        "example_id": case.example_id,
        "document_key": case.document_key,
        "reference": case.reference,
        "title": case.title,
        "text": case.text,
        "status": case.status.value if case.status else None,
        "findings": [
            {
                "type": finding.type.value,
                "severity": finding.severity.value,
                "evidence": finding.evidence,
                "explanation": finding.explanation,
                "confidence": finding.confidence,
            }
            for finding in case.findings
        ],
        "model_id": case.model_id,
        "model_ref": case.model_ref,
        "provider": case.provider,
        "duration_ms": case.duration_ms,
        "cached": case.cached,
        "input_hash": case.input_hash,
        "raw_response_hash": case.raw_response_hash,
        "error": case.error,
    }
