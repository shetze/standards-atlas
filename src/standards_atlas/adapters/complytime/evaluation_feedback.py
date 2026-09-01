"""Import Gemara EvaluationLog results into deterministic Standards Atlas feedback."""

from __future__ import annotations

import json
from collections import Counter
from hashlib import sha256
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from standards_atlas.shared.artifacts import write_json

GemaraResult = Literal[
    "Not Run",
    "Passed",
    "Failed",
    "Needs Review",
    "Not Applicable",
    "Unknown",
]


class EvaluationEntryMapping(BaseModel):
    """Gemara EntryMapping subset needed to resolve evaluation provenance."""

    model_config = ConfigDict(frozen=True, populate_by_name=True, extra="ignore")

    reference_id: str = Field(alias="reference-id", min_length=1)
    entry_id: str = Field(alias="entry-id", min_length=1)


class EvaluationAssessmentLog(BaseModel):
    """AssessmentLog subset preserved by the feedback importer."""

    model_config = ConfigDict(frozen=True, populate_by_name=True, extra="ignore")

    requirement: EvaluationEntryMapping
    plan: EvaluationEntryMapping | None = None
    description: str
    result: GemaraResult
    message: str
    applicability: tuple[str, ...] = Field(min_length=1)
    steps: tuple[str, ...] = Field(min_length=1)
    steps_executed: int | None = Field(default=None, alias="steps-executed", ge=0)
    start: str
    end: str | None = None
    recommendation: str | None = None
    confidence_level: str | None = Field(default=None, alias="confidence-level")


class EvaluationControlLog(BaseModel):
    """ControlEvaluation subset needed for traceability feedback."""

    model_config = ConfigDict(frozen=True, populate_by_name=True, extra="ignore")

    name: str
    result: GemaraResult
    message: str
    control: EvaluationEntryMapping
    assessment_logs: tuple[EvaluationAssessmentLog, ...] = Field(
        alias="assessment-logs", min_length=1
    )


class EvaluationLogMetadata(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True, extra="ignore")

    id: str = Field(min_length=1)
    type: Literal["EvaluationLog"]
    gemara_version: str = Field(alias="gemara-version", min_length=1)


class GemaraEvaluationLog(BaseModel):
    """Stable EvaluationLog import surface used by Standards Atlas."""

    model_config = ConfigDict(frozen=True, populate_by_name=True, extra="ignore")

    metadata: EvaluationLogMetadata
    result: GemaraResult
    evaluations: tuple[EvaluationControlLog, ...] = Field(min_length=1)


class AssessmentFeedback(BaseModel):
    """One evaluated assessment requirement resolved to Standards Atlas provenance."""

    model_config = ConfigDict(frozen=True)

    control_id: str
    assessment_requirement_id: str
    clause_id: str
    guidance_catalog_id: str
    guidance_entry_id: str
    result: GemaraResult
    message: str
    description: str
    applicability: tuple[str, ...]
    recommendation: str | None = None
    plan_reference_id: str | None = None
    plan_entry_id: str | None = None
    start: str
    end: str | None = None


class ControlFeedback(BaseModel):
    """One evaluated control and its clause-resolved assessment results."""

    model_config = ConfigDict(frozen=True)

    control_id: str
    clause_id: str
    guidance_catalog_id: str
    guidance_entry_id: str
    result: GemaraResult
    message: str
    assessments: tuple[AssessmentFeedback, ...]


class EvaluationFeedbackSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    controls: int = Field(ge=0)
    assessments: int = Field(ge=0)
    assessment_results: dict[str, int]


class EvaluationFeedbackManifest(BaseModel):
    """Read-only feedback projection from a Gemara EvaluationLog."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    document_key: str
    evaluation_log_id: str
    evaluation_log_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    governance_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    aggregate_result: GemaraResult
    summary: EvaluationFeedbackSummary
    controls: tuple[ControlFeedback, ...]


class EvaluationLogFeedbackImporter:
    """Resolve EvaluationLog IDs against one Standards Atlas governance bundle."""

    def import_log(
        self,
        evaluation_log: Path,
        governance_bundle: Path,
        output: Path,
    ) -> Path:
        log = _load_evaluation_log(evaluation_log)
        manifest_path = governance_bundle / "manifest.yaml"
        traceability_path = governance_bundle / "traceability.json"
        manifest = _load_yaml_mapping(manifest_path)
        traceability = _load_json_mapping(traceability_path)
        _verify_bundle_traceability(manifest, traceability_path)

        document_key = _required_string(traceability, "document_key")
        expected_gemara_version = _required_string(manifest, "gemara-version")
        if log.metadata.gemara_version != expected_gemara_version:
            raise ValueError(
                "EvaluationLog Gemara version does not match governance bundle: "
                f"log={log.metadata.gemara_version!r}, bundle={expected_gemara_version!r}"
            )
        controls_trace = _required_mapping(traceability, "controls")
        expected_catalog_id = _required_string(controls_trace, "gemara_catalog_id")
        entries = controls_trace.get("entries")
        if not isinstance(entries, list):
            raise ValueError("Governance bundle control traceability has no entries list")

        controls_by_id: dict[str, dict[str, object]] = {}
        requirements_by_id: dict[str, dict[str, object]] = {}
        for raw in entries:
            if not isinstance(raw, dict):
                raise ValueError("Governance bundle control traceability entry must be an object")
            entry_id = _required_string(raw, "gemara_entry_id")
            entry_type = _required_string(raw, "entry_type")
            if entry_type == "control":
                controls_by_id[entry_id] = raw
            elif entry_type == "assessment_requirement":
                requirements_by_id[entry_id] = raw

        feedback_controls: list[ControlFeedback] = []
        assessment_results: Counter[str] = Counter()
        for evaluation in log.evaluations:
            _require_reference(evaluation.control, expected_catalog_id, "control")
            control_trace = _resolve_entry(
                controls_by_id,
                evaluation.control.entry_id,
                "control",
            )
            assessments: list[AssessmentFeedback] = []
            for assessment in evaluation.assessment_logs:
                _require_reference(assessment.requirement, expected_catalog_id, "requirement")
                requirement_trace = _resolve_entry(
                    requirements_by_id,
                    assessment.requirement.entry_id,
                    "assessment requirement",
                )
                owner_control = _required_string(requirement_trace, "owner_control_id")
                if owner_control != evaluation.control.entry_id:
                    raise ValueError(
                        "Assessment requirement owner does not match evaluated control: "
                        f"{assessment.requirement.entry_id} -> {owner_control}, "
                        f"evaluation uses {evaluation.control.entry_id}"
                    )
                assessment_results[assessment.result] += 1
                assessments.append(
                    AssessmentFeedback(
                        control_id=evaluation.control.entry_id,
                        assessment_requirement_id=assessment.requirement.entry_id,
                        clause_id=_required_string(requirement_trace, "clause_id"),
                        guidance_catalog_id=_required_string(
                            requirement_trace, "guidance_catalog_id"
                        ),
                        guidance_entry_id=_required_string(requirement_trace, "guidance_entry_id"),
                        result=assessment.result,
                        message=assessment.message,
                        description=assessment.description,
                        applicability=assessment.applicability,
                        recommendation=assessment.recommendation,
                        plan_reference_id=(
                            assessment.plan.reference_id if assessment.plan is not None else None
                        ),
                        plan_entry_id=(
                            assessment.plan.entry_id if assessment.plan is not None else None
                        ),
                        start=assessment.start,
                        end=assessment.end,
                    )
                )
            feedback_controls.append(
                ControlFeedback(
                    control_id=evaluation.control.entry_id,
                    clause_id=_required_string(control_trace, "clause_id"),
                    guidance_catalog_id=_required_string(control_trace, "guidance_catalog_id"),
                    guidance_entry_id=_required_string(control_trace, "guidance_entry_id"),
                    result=evaluation.result,
                    message=evaluation.message,
                    assessments=tuple(assessments),
                )
            )

        feedback = EvaluationFeedbackManifest(
            document_key=document_key,
            evaluation_log_id=log.metadata.id,
            evaluation_log_sha256=_sha256_file(evaluation_log),
            governance_manifest_sha256=_sha256_file(manifest_path),
            aggregate_result=log.result,
            summary=EvaluationFeedbackSummary(
                controls=len(feedback_controls),
                assessments=sum(len(item.assessments) for item in feedback_controls),
                assessment_results={
                    result: assessment_results[result]
                    for result in (
                        "Passed",
                        "Failed",
                        "Needs Review",
                        "Not Applicable",
                        "Unknown",
                        "Not Run",
                    )
                },
            ),
            controls=tuple(feedback_controls),
        )
        write_json(
            output,
            feedback.model_dump(mode="json"),
            sort_keys=True,
        )
        return output


def _load_evaluation_log(path: Path) -> GemaraEvaluationLog:
    payload = _load_yaml_mapping(path)
    return GemaraEvaluationLog.model_validate(payload)


def _load_yaml_mapping(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise ValueError(f"Required file does not exist: {path}")
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected YAML object in {path}")
    return payload


def _load_json_mapping(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise ValueError(f"Required file does not exist: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return payload


def _verify_bundle_traceability(manifest: dict[str, object], path: Path) -> None:
    traceability = _required_mapping(manifest, "traceability")
    expected = _required_string(traceability, "sha256")
    actual = _sha256_file(path)
    if actual != expected:
        raise ValueError(
            f"Governance bundle traceability hash mismatch: manifest={expected}, actual={actual}"
        )


def _require_reference(
    mapping: EvaluationEntryMapping,
    expected_catalog_id: str,
    label: str,
) -> None:
    if mapping.reference_id != expected_catalog_id:
        raise ValueError(
            f"Evaluation {label} references catalog {mapping.reference_id!r}; "
            f"expected {expected_catalog_id!r}"
        )


def _resolve_entry(
    entries: dict[str, dict[str, object]],
    entry_id: str,
    label: str,
) -> dict[str, object]:
    try:
        return entries[entry_id]
    except KeyError as exc:
        raise ValueError(f"Evaluation references unknown {label}: {entry_id}") from exc


def _required_mapping(payload: dict[str, object], key: str) -> dict[str, object]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"Expected object field {key!r}")
    return value


def _required_string(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"Expected non-empty string field {key!r}")
    return value


def _sha256_file(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()
