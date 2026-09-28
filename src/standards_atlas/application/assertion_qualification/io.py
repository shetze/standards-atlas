"""File I/O for assertion golden suites, proposal artifacts and evaluation reports."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from standards_atlas.application.assertion_qualification.audit import (
    AssertionReviewAudit,
    load_mapping_bytes,
)
from standards_atlas.application.assertion_qualification.cascade_models import (
    AssertionQualificationCascadeReport,
)
from standards_atlas.application.assertion_qualification.models import (
    AssertionGoldenSuite,
    AssertionQualificationReport,
)
from standards_atlas.application.assertion_qualification.policy_models import (
    AssertionAutoAdoptionPolicy,
    AssertionAutoAdoptionReport,
)
from standards_atlas.application.assertion_qualification.reporting import (
    render_assertion_qualification_summary,
)
from standards_atlas.application.assertion_qualification.review_pilot_models import (
    ApplicabilitySelectionCorpus,
    AssertionReviewPilot,
)
from standards_atlas.application.schema import require_current_payload, require_supported_schema
from standards_atlas.domain.model import DocumentKnowledgeProposal


def load_applicability_selection_corpus(path: Path) -> ApplicabilitySelectionCorpus:
    """Load the current applicability gold contract only as a pilot selection source."""
    payload = _load_mapping(path)
    require_supported_schema("applicability-golden-corpus", payload.get("schema_version"))
    return ApplicabilitySelectionCorpus.model_validate(payload)


def load_assertion_review_pilot(path: Path) -> AssertionReviewPilot:
    payload = _load_mapping(path)
    require_supported_schema("assertion-review-pilot", payload.get("schema_version"))
    return AssertionReviewPilot.model_validate(payload)


def write_assertion_review_pilot(review: AssertionReviewPilot, path: Path) -> Path:
    payload = review.model_dump(mode="json")
    require_current_payload("assertion-review-pilot", payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return path


def write_assertion_golden_suite(suite: AssertionGoldenSuite, path: Path) -> Path:
    payload = suite.model_dump(mode="json")
    AssertionGoldenSuite.model_validate(payload)
    require_current_payload("assertion-golden-suite", payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".json":
        rendered = json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    else:
        rendered = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)
    path.write_text(rendered, encoding="utf-8")
    return path


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


def load_assertion_qualification_report(path: Path) -> AssertionQualificationReport:
    payload = _load_mapping(path)
    require_supported_schema("assertion-qualification-report", payload.get("schema_version"))
    return AssertionQualificationReport.model_validate(payload)


def load_assertion_auto_adoption_policy(path: Path) -> AssertionAutoAdoptionPolicy:
    payload = _load_mapping(path)
    require_supported_schema("assertion-auto-adoption-policy", payload.get("schema_version"))
    return AssertionAutoAdoptionPolicy.model_validate(payload)


def load_assertion_auto_adoption_report(path: Path) -> AssertionAutoAdoptionReport:
    payload = _load_mapping(path)
    require_supported_schema("assertion-auto-adoption-report", payload.get("schema_version"))
    return AssertionAutoAdoptionReport.model_validate(payload)


def write_assertion_auto_adoption_report(
    report: AssertionAutoAdoptionReport,
    path: Path,
) -> Path:
    payload = report.model_dump(mode="json")
    require_current_payload("assertion-auto-adoption-report", payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def write_assertion_qualification_report(
    report: AssertionQualificationReport,
    path: Path,
) -> Path:
    payload = report.model_dump(mode="json")
    AssertionQualificationReport.model_validate(payload)
    require_current_payload("assertion-qualification-report", payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def write_assertion_qualification_summary(
    report: AssertionQualificationReport,
    path: Path,
) -> Path:
    """Write a deterministic Markdown rendering of the validated report."""
    AssertionQualificationReport.model_validate(report.model_dump(mode="json"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_assertion_qualification_summary(report), encoding="utf-8")
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
    return load_mapping_bytes(path.read_bytes(), json_format=path.suffix.lower() == ".json")


def load_assertion_review_audit(path: Path) -> AssertionReviewAudit:
    """Load a complete audit without rewriting or repairing its original bytes."""
    return AssertionReviewAudit(path.read_bytes(), json_format=path.suffix.lower() == ".json")


def copy_assertion_review_audit(audit: AssertionReviewAudit, path: Path) -> Path:
    """Preserve original bytes; never overwrite a different existing artifact."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as output:
            output.write(audit.original_bytes)
    except FileExistsError:
        if path.read_bytes() != audit.original_bytes:
            raise ValueError(f"refusing to overwrite a different audit artifact: {path}") from None
    return path


def ensure_distinct_output(output: Path, *inputs: Path) -> None:
    """Protect source artifacts, including symlink and hardlink aliases."""
    for source in inputs:
        if output.resolve() == source.resolve() or (
            output.exists() and source.exists() and output.samefile(source)
        ):
            raise ValueError(f"output must not overwrite input artifact: {source}")
