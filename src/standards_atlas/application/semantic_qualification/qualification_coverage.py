"""Explicit accounting of persisted qualification-run selections."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from standards_atlas.application.semantic_qualification.consensus import ConsensusReport
from standards_atlas.application.semantic_qualification.run_selection import (
    QualificationRunSelection,
)

QUALIFICATION_COVERAGE_SCHEMA_VERSION = "1.0"
QUALIFICATION_COVERAGE_FILENAME = "qualification-coverage.json"


class QualificationCoverageClause(BaseModel):
    """One selected clause and its qualification outcome."""

    model_config = ConfigDict(frozen=True)

    example_id: str = Field(min_length=1)
    document_key: str = Field(min_length=1)
    clause_id: str = Field(min_length=1)
    status: Literal["qualified", "unqualified"]
    reason: str | None = None


class QualificationCoverage(BaseModel):
    """Complete accounting of one persisted qualification selection."""

    model_config = ConfigDict(frozen=True)

    schema_version: str = QUALIFICATION_COVERAGE_SCHEMA_VERSION
    selected_clause_count: int = Field(ge=0)
    qualified_clause_count: int = Field(ge=0)
    unqualified_clause_count: int = Field(ge=0)
    accounted_clause_count: int = Field(ge=0)
    clauses: tuple[QualificationCoverageClause, ...]


def build_qualification_coverage(
    *,
    selection: QualificationRunSelection,
    report: ConsensusReport,
) -> QualificationCoverage:
    """Account for every selected clause, including clauses without consensus output."""
    qualified = {(item.document_key, item.clause_id) for item in report.clauses}
    selected = {(item.document_key, item.clause_id) for item in selection.clauses}
    unexpected = qualified - selected
    if unexpected:
        details = ", ".join(
            f"{document_key}:{clause_id}" for document_key, clause_id in sorted(unexpected)
        )
        raise ValueError(
            "qualification consensus contains clauses outside the persisted run selection: "
            f"{details}"
        )

    clauses = tuple(
        QualificationCoverageClause(
            example_id=item.example_id,
            document_key=item.document_key,
            clause_id=item.clause_id,
            status=(
                "qualified" if (item.document_key, item.clause_id) in qualified else "unqualified"
            ),
            reason=(
                None if (item.document_key, item.clause_id) in qualified else "no_consensus_result"
            ),
        )
        for item in selection.clauses
    )
    qualified_count = sum(item.status == "qualified" for item in clauses)
    unqualified_count = len(clauses) - qualified_count
    return QualificationCoverage(
        selected_clause_count=len(clauses),
        qualified_clause_count=qualified_count,
        unqualified_clause_count=unqualified_count,
        accounted_clause_count=len(clauses),
        clauses=clauses,
    )


def persist_qualification_coverage(
    coverage: QualificationCoverage,
    path: Path,
) -> Path:
    """Persist one qualification coverage contract."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(coverage.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return path


def load_qualification_coverage(path: Path) -> QualificationCoverage:
    """Load one persisted qualification coverage contract."""
    return QualificationCoverage.model_validate(json.loads(path.read_text(encoding="utf-8")))
