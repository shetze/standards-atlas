"""File I/O for assertion golden suites, proposal artifacts and evaluation reports."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from standards_atlas.application.assertion_qualification.cascade_models import (
    AssertionQualificationCascadeReport,
)
from standards_atlas.application.assertion_qualification.models import (
    AssertionGoldenSuite,
    AssertionQualificationReport,
)
from standards_atlas.application.schema import require_current_payload, require_supported_schema
from standards_atlas.domain.model import DocumentKnowledgeProposal


def load_assertion_golden_suite(path: Path) -> AssertionGoldenSuite:
    payload = _load_mapping(path)
    require_supported_schema("assertion-golden-suite", payload.get("schema_version"))
    return AssertionGoldenSuite.model_validate(payload)


def load_document_knowledge_proposal(path: Path) -> DocumentKnowledgeProposal:
    payload = _load_mapping(path)
    if "proposal" in payload:
        require_supported_schema("document-knowledge-proposal", payload.get("schema_version"))
        proposal_payload = payload.get("proposal")
        if not isinstance(proposal_payload, dict):
            raise ValueError(f"proposal artifact {path} has no proposal mapping")
    else:
        proposal_payload = payload
    require_supported_schema(
        "document-knowledge-proposal",
        proposal_payload.get("schema_version"),
    )
    return DocumentKnowledgeProposal.model_validate(proposal_payload)


def write_assertion_qualification_report(
    report: AssertionQualificationReport,
    path: Path,
) -> Path:
    payload = report.model_dump(mode="json")
    require_current_payload("assertion-qualification-report", payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def load_assertion_qualification_cascade_report(
    path: Path,
) -> AssertionQualificationCascadeReport:
    payload = _load_mapping(path)
    require_supported_schema(
        "assertion-qualification-cascade-report", payload.get("schema_version")
    )
    return AssertionQualificationCascadeReport.model_validate(payload)


def write_assertion_qualification_cascade_report(
    report: AssertionQualificationCascadeReport,
    path: Path,
) -> Path:
    payload = report.model_dump(mode="json")
    require_current_payload("assertion-qualification-cascade-report", payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def _load_mapping(path: Path) -> dict[str, object]:
    raw = path.read_text(encoding="utf-8")
    payload = json.loads(raw) if path.suffix.lower() == ".json" else yaml.safe_load(raw)
    if not isinstance(payload, dict):
        raise ValueError(f"expected mapping in {path}")
    return payload
