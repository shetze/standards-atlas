"""Model-free AP03 qualification preflight and frozen B0 integrity checks."""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from standards_atlas.application.assertion_qualification.evaluation import golden_suite_sha256
from standards_atlas.application.assertion_qualification.io import (
    load_assertion_golden_suite,
    load_assertion_qualification_report,
    load_assertion_review_audit,
)
from standards_atlas.application.assertion_qualification.policy import (
    qualification_report_sha256,
)
from standards_atlas.application.context.context_selection import (
    STRUCTURED_CONTEXT_SELECTION_CONTRACT,
    ContextSelectionProfile,
)
from standards_atlas.application.context.source_surfaces import SOURCE_SURFACE_CONTRACT
from standards_atlas.application.context.structured_candidates import (
    STRUCTURED_CONTEXT_CANDIDATE_CONTRACT,
)
from standards_atlas.application.evaluation.repository import PromptRepository
from standards_atlas.application.knowledge_proposal_extraction.context import (
    ASSERTION_CBOX_CONTRACT_VERSION,
)
from standards_atlas.domain.model import (
    CONTEXT_SOURCE_PACKAGE_BINDING_CONTRACT,
    CONTEXT_SOURCE_PACKAGE_CONTRACT,
)

AP03_PREFLIGHT_CONTRACT = "ap03-qualification-preflight-v1"
AP03_B0_RESOURCE = "ap03-b0.json"


class Ap03ArtifactStatus(StrEnum):
    AVAILABLE = "available"
    MISSING = "missing"
    AMBIGUOUS = "ambiguous"
    INVALID = "invalid"


class Ap03ArtifactCheck(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    artifact_id: str = Field(min_length=1)
    required_for: tuple[str, ...]
    required: bool = True
    status: Ap03ArtifactStatus
    path: str | None = None
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    model_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    details: dict[str, object] = Field(default_factory=dict)
    issue: str | None = None


class Ap03ModelDeclaration(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    provider: str | None = None
    model_ref: str | None = None
    runtime: str | None = None
    quantization: str | None = None
    availability_verified: Literal[False] = False


class Ap03B0Check(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    baseline_id: Literal["B0-AP02"] = "B0-AP02"
    manifest_path: str = Field(min_length=1)
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    intact: bool
    prompt_bindings: tuple[dict[str, object], ...]
    context_binding: dict[str, object]
    generation_binding: dict[str, object]
    issues: tuple[str, ...] = ()


class Ap03PreflightReport(BaseModel):
    """Text-free readiness report; it performs no inference and mutates no project artifact."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    contract_id: Literal["ap03-qualification-preflight-v1"] = AP03_PREFLIGHT_CONTRACT
    model_execution: Literal[False] = False
    network_access: Literal[False] = False
    golden_or_knowledge_write: Literal[False] = False
    project_root: str = Field(min_length=1)
    registered_roots: tuple[str, ...]
    b0: Ap03B0Check
    historical_artifacts: tuple[Ap03ArtifactCheck, ...]
    declared_models: tuple[Ap03ModelDeclaration, ...]
    historical_input_state_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    historical_replay_ready: bool
    b0_experiment_inputs_ready: bool
    release_state: Literal["not_ready_for_release"] = "not_ready_for_release"
    release_blockers: tuple[str, ...]
    gaps: tuple[str, ...]


def run_ap03_preflight(project_root: Path) -> Ap03PreflightReport:
    """Inspect only registered project locations and installed packaged resources.

    The preflight does not inspect arbitrary user directories, contact a model endpoint, download a
    model, execute a prompt or write Golden/DocumentKnowledge state.  It deliberately distinguishes
    declarations from effective runtime availability.
    """

    root = project_root.resolve()
    review_root = root / "local" / "review" / "assertions"
    evaluation_root = root / "local" / "evaluation" / "assertions"
    manifest_root = root / "manifests"
    config_root = root / "cfg"
    registered_roots = (review_root, evaluation_root, manifest_root, config_root)

    b0 = _check_b0(root)
    artifacts = _check_historical_artifacts(review_root, evaluation_root)
    declared_models = _declared_models(root)

    artifacts_by_id = {item.artifact_id: item for item in artifacts}
    audit = artifacts_by_id["v8_review_audit"]
    golden = artifacts_by_id["development_golden_suite"]
    report = artifacts_by_id["v8_qualification_report"]
    historical_replay_ready = all(
        item.status is Ap03ArtifactStatus.AVAILABLE for item in (audit, golden, report)
    )
    b0_experiment_inputs_ready = (
        b0.intact and golden.status is Ap03ArtifactStatus.AVAILABLE and bool(declared_models)
    )

    gaps: list[str] = []
    for item in artifacts:
        if item.required and item.status is not Ap03ArtifactStatus.AVAILABLE:
            gaps.append(f"{item.artifact_id}: {item.issue or item.status.value}")
    gaps.extend(f"B0: {issue}" for issue in b0.issues)
    if not declared_models:
        gaps.append(
            "no model configurations are declared in cfg/llm.yaml or qualification manifests"
        )

    release_blockers = [
        "AP03 quality thresholds and minimum supports are not yet approved",
        "no frozen finalist configuration exists",
        "no isolated AP03 holdout campaign has been evaluated",
        "no real B0/AP03 semantic model measurements were executed by this preflight",
    ]
    return Ap03PreflightReport(
        project_root=str(root),
        registered_roots=tuple(str(item) for item in registered_roots),
        b0=b0,
        historical_artifacts=artifacts,
        declared_models=declared_models,
        historical_input_state_sha256=_historical_input_state_hash(artifacts),
        historical_replay_ready=historical_replay_ready,
        b0_experiment_inputs_ready=b0_experiment_inputs_ready,
        release_blockers=tuple(release_blockers),
        gaps=tuple(gaps),
    )


def _check_b0(project_root: Path, *, semantic_root: Path | None = None) -> Ap03B0Check:
    semantic_root = semantic_root or (
        Path(__file__).resolve().parents[2] / "resources" / "semantic"
    )
    manifest_path = semantic_root / "prompts" / AP03_B0_RESOURCE
    manifest_bytes = manifest_path.read_bytes()
    payload = json.loads(manifest_bytes)
    if payload.get("schema_version") != 1 or payload.get("baseline_id") != "B0-AP02":
        raise ValueError("AP03 B0 manifest has an unsupported identity")

    issues: list[str] = []
    prompt_repository = PromptRepository(
        semantic_root / "prompts", task_root=semantic_root / "tasks"
    )
    for binding in payload.get("prompt_bindings", []):
        if not isinstance(binding, dict):
            issues.append("invalid prompt binding entry")
            continue
        task = str(binding.get("task", ""))
        prompt_version = str(binding.get("prompt_version", ""))
        task_schema_version = str(binding.get("task_schema_version", ""))
        try:
            definition = prompt_repository.load(task, prompt_version)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            issues.append(f"{task}@{prompt_version}: {exc}")
            continue
        if definition.task_schema_version != task_schema_version:
            issues.append(
                f"{task}@{prompt_version}: task schema binding changed from "
                f"{task_schema_version!r} to {definition.task_schema_version!r}"
            )
        expected_files = binding.get("files", {})
        if not isinstance(expected_files, dict):
            issues.append(f"{task}@{prompt_version}: invalid file fingerprint mapping")
            continue
        prompt_dir = semantic_root / "prompts" / task / prompt_version
        task_dir = semantic_root / "tasks" / task / task_schema_version
        paths = {
            "prompt_json_sha256": prompt_dir / "prompt.json",
            "system_sha256": prompt_dir / "system.txt",
            "user_template_sha256": prompt_dir / "user.txt",
            "prompt_schema_sha256": prompt_dir / "schema.json",
            "task_yaml_sha256": task_dir / "task.yaml",
            "task_schema_sha256": task_dir / "schema.json",
        }
        for key, path in paths.items():
            actual = _file_sha256(path) if path.is_file() else None
            expected = expected_files.get(key)
            if actual != expected:
                issues.append(
                    f"{task}@{prompt_version}: {path.name} fingerprint changed "
                    f"(expected {expected}, got {actual})"
                )

    expected_context = payload.get("context_binding", {})
    actual_profile = ContextSelectionProfile().model_dump(mode="json")
    actual_context: dict[str, object] = {
        "source_surface_contract": SOURCE_SURFACE_CONTRACT,
        "candidate_contract": STRUCTURED_CONTEXT_CANDIDATE_CONTRACT,
        "selection_contract": STRUCTURED_CONTEXT_SELECTION_CONTRACT,
        "selection_profile": actual_profile,
        "source_package_contract": CONTEXT_SOURCE_PACKAGE_CONTRACT,
        "source_package_schema_version": 1,
        "source_binding_contract": CONTEXT_SOURCE_PACKAGE_BINDING_CONTRACT,
        "assertion_cbox_contract_version": ASSERTION_CBOX_CONTRACT_VERSION,
    }
    if expected_context != actual_context:
        issues.append("post-AP02 context/source contract differs from frozen B0 binding")

    generation = payload.get("generation_binding", {})
    if not isinstance(generation, dict):
        issues.append("invalid B0 generation binding")
        generation = {}
    config_rel = generation.get("declared_runtime_config_path")
    if isinstance(config_rel, str):
        config_path = project_root / config_rel
        actual = _file_sha256(config_path) if config_path.is_file() else None
        if actual != generation.get("declared_runtime_config_sha256"):
            issues.append("declared B0 runtime configuration bytes have changed or are missing")

    return Ap03B0Check(
        manifest_path=str(manifest_path),
        manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
        intact=not issues,
        prompt_bindings=tuple(dict(item) for item in payload.get("prompt_bindings", [])),
        context_binding=dict(expected_context),
        generation_binding=dict(generation),
        issues=tuple(issues),
    )


def _check_historical_artifacts(
    review_root: Path,
    evaluation_root: Path,
) -> tuple[Ap03ArtifactCheck, ...]:
    audit_path = _resolve_named_artifact(
        review_root, "assertion-review-pilot-v8-reviewed-complete.yaml"
    )
    golden_path = _resolve_named_artifact(review_root, "assertion-golden-suite.yaml")
    report_path = _resolve_named_artifact(evaluation_root, "assertion-qualification-v8.json")
    summary_path = _resolve_named_artifact(evaluation_root, "assertion-qualification-v8-summary.md")

    audit = _audit_check(audit_path)
    golden = _golden_check(golden_path, audit)
    report = _report_check(report_path, golden, audit)
    summary = _plain_file_check(
        "v8_qualification_summary",
        summary_path,
        required_for=("human_reference",),
        required=False,
    )
    return (audit, golden, report, summary)


def _audit_check(path_or_issue: Path | tuple[Ap03ArtifactStatus, str]) -> Ap03ArtifactCheck:
    if not isinstance(path_or_issue, Path):
        status, issue = path_or_issue
        return Ap03ArtifactCheck(
            artifact_id="v8_review_audit",
            required_for=("historical_v8_replay", "golden_binding_validation"),
            status=status,
            issue=issue,
        )
    try:
        audit = load_assertion_review_audit(path_or_issue)
    except (OSError, ValueError) as exc:
        return Ap03ArtifactCheck(
            artifact_id="v8_review_audit",
            required_for=("historical_v8_replay", "golden_binding_validation"),
            status=Ap03ArtifactStatus.INVALID,
            path=str(path_or_issue),
            sha256=_file_sha256(path_or_issue),
            issue=str(exc),
        )
    expected = _b0_historical_reference()["audit_sha256"]
    issue = (
        None if audit.audit_sha256 == expected else "audit SHA-256 differs from frozen AP01 bytes"
    )
    return Ap03ArtifactCheck(
        artifact_id="v8_review_audit",
        required_for=("historical_v8_replay", "golden_binding_validation"),
        status=Ap03ArtifactStatus.AVAILABLE if issue is None else Ap03ArtifactStatus.INVALID,
        path=str(path_or_issue),
        sha256=audit.audit_sha256,
        details={
            "review_id": audit.review.review_id,
            "review_version": audit.review.review_version,
            "cases": len(audit.review.cases),
        },
        issue=issue,
    )


def _golden_check(
    path_or_issue: Path | tuple[Ap03ArtifactStatus, str],
    audit_check: Ap03ArtifactCheck,
) -> Ap03ArtifactCheck:
    if not isinstance(path_or_issue, Path):
        status, issue = path_or_issue
        return Ap03ArtifactCheck(
            artifact_id="development_golden_suite",
            required_for=("historical_v8_replay", "B0_development_experiment"),
            status=status,
            issue=issue,
        )
    try:
        suite = load_assertion_golden_suite(path_or_issue)
        model_hash = golden_suite_sha256(suite)
    except (OSError, ValueError) as exc:
        return Ap03ArtifactCheck(
            artifact_id="development_golden_suite",
            required_for=("historical_v8_replay", "B0_development_experiment"),
            status=Ap03ArtifactStatus.INVALID,
            path=str(path_or_issue),
            sha256=_file_sha256(path_or_issue),
            issue=str(exc),
        )
    expected = _b0_historical_reference()
    issues: list[str] = []
    if model_hash != expected["golden_suite_sha256"]:
        issues.append("golden suite model hash differs from frozen AP01 suite")
    if suite.id != expected["suite_id"] or suite.version != expected["suite_version"]:
        issues.append("golden suite identity differs from frozen AP01 suite")
    if suite.partition.value != expected["partition"]:
        issues.append("golden suite partition differs from frozen Development partition")
    if suite.audit.audit_sha256 != expected["audit_sha256"]:
        issues.append("golden suite audit binding differs from frozen AP01 audit")
    if audit_check.status is Ap03ArtifactStatus.AVAILABLE and (
        suite.audit.audit_sha256 != audit_check.sha256
    ):
        issues.append("golden suite does not bind the resolved audit bytes")
    return Ap03ArtifactCheck(
        artifact_id="development_golden_suite",
        required_for=("historical_v8_replay", "B0_development_experiment"),
        status=Ap03ArtifactStatus.AVAILABLE if not issues else Ap03ArtifactStatus.INVALID,
        path=str(path_or_issue),
        sha256=_file_sha256(path_or_issue),
        model_sha256=model_hash,
        details={
            "suite_id": suite.id,
            "suite_version": suite.version,
            "partition": suite.partition.value,
            "cases": len(suite.cases),
            "entities": sum(len(case.entities) for case in suite.cases),
            "assertions": sum(len(case.assertions) for case in suite.cases),
            "audit_sha256": suite.audit.audit_sha256,
        },
        issue="; ".join(issues) or None,
    )


def _report_check(
    path_or_issue: Path | tuple[Ap03ArtifactStatus, str],
    golden_check: Ap03ArtifactCheck,
    audit_check: Ap03ArtifactCheck,
) -> Ap03ArtifactCheck:
    if not isinstance(path_or_issue, Path):
        status, issue = path_or_issue
        return Ap03ArtifactCheck(
            artifact_id="v8_qualification_report",
            required_for=("historical_v8_replay", "historical_comparison"),
            status=status,
            issue=issue,
        )
    try:
        report = load_assertion_qualification_report(path_or_issue)
        model_hash = qualification_report_sha256(report)
    except (OSError, ValueError) as exc:
        return Ap03ArtifactCheck(
            artifact_id="v8_qualification_report",
            required_for=("historical_v8_replay", "historical_comparison"),
            status=Ap03ArtifactStatus.INVALID,
            path=str(path_or_issue),
            sha256=_file_sha256(path_or_issue),
            issue=str(exc),
        )
    expected = _b0_historical_reference()
    issues: list[str] = []
    if model_hash != expected["qualification_report_sha256"]:
        issues.append("qualification report model hash differs from frozen AP01 report")
    if report.golden_suite_id != expected["suite_id"] or (
        report.golden_suite_version != expected["suite_version"]
    ):
        issues.append("qualification report suite identity differs from frozen AP01 suite")
    if report.golden_partition.value != expected["partition"]:
        issues.append("qualification report partition differs from Development")
    if report.audit.audit_sha256 != expected["audit_sha256"]:
        issues.append("qualification report audit binding differs from frozen AP01 audit")
    if golden_check.status is Ap03ArtifactStatus.AVAILABLE and (
        report.golden_suite_hash != golden_check.model_sha256
    ):
        issues.append("qualification report does not bind the resolved golden suite")
    if audit_check.status is Ap03ArtifactStatus.AVAILABLE and (
        report.audit.audit_sha256 != audit_check.sha256
    ):
        issues.append("qualification report does not bind the resolved audit bytes")
    return Ap03ArtifactCheck(
        artifact_id="v8_qualification_report",
        required_for=("historical_v8_replay", "historical_comparison"),
        status=Ap03ArtifactStatus.AVAILABLE if not issues else Ap03ArtifactStatus.INVALID,
        path=str(path_or_issue),
        sha256=_file_sha256(path_or_issue),
        model_sha256=model_hash,
        details={
            "candidate_mode": report.candidate_mode,
            "evaluation_contract": report.evaluation_contract,
            "cases": len(report.cases),
            "golden_suite_hash": report.golden_suite_hash,
        },
        issue="; ".join(issues) or None,
    )


def _plain_file_check(
    artifact_id: str,
    path_or_issue: Path | tuple[Ap03ArtifactStatus, str],
    *,
    required_for: tuple[str, ...],
    required: bool,
) -> Ap03ArtifactCheck:
    if isinstance(path_or_issue, Path):
        return Ap03ArtifactCheck(
            artifact_id=artifact_id,
            required_for=required_for,
            required=required,
            status=Ap03ArtifactStatus.AVAILABLE,
            path=str(path_or_issue),
            sha256=_file_sha256(path_or_issue),
        )
    status, issue = path_or_issue
    if not required and status is Ap03ArtifactStatus.MISSING:
        issue = "optional artifact is not present"
    return Ap03ArtifactCheck(
        artifact_id=artifact_id,
        required_for=required_for,
        required=required,
        status=status,
        issue=issue,
    )


def _resolve_named_artifact(
    root: Path,
    filename: str,
) -> Path | tuple[Ap03ArtifactStatus, str]:
    if not root.is_dir():
        return (Ap03ArtifactStatus.MISSING, f"registered root does not exist: {root}")
    matches = tuple(path for path in root.rglob(filename) if path.is_file())
    if not matches:
        return (Ap03ArtifactStatus.MISSING, f"{filename} not found below registered root {root}")
    if len(matches) > 1:
        return (
            Ap03ArtifactStatus.AMBIGUOUS,
            f"multiple {filename} files found below registered root; explicit resolution required",
        )
    return matches[0]


def _declared_models(project_root: Path) -> tuple[Ap03ModelDeclaration, ...]:
    declarations: dict[tuple[str, str], Ap03ModelDeclaration] = {}
    llm_path = project_root / "cfg" / "llm.yaml"
    if llm_path.is_file():
        payload = yaml.safe_load(llm_path.read_text(encoding="utf-8")) or {}
        llm = payload.get("llm", payload) if isinstance(payload, dict) else {}
        if isinstance(llm, dict) and llm.get("model"):
            model_ref = str(llm["model"])
            server = llm.get("server", {})
            runtime = server.get("runtime") if isinstance(server, dict) else None
            declaration = Ap03ModelDeclaration(
                source="cfg/llm.yaml",
                model_id="configured-default",
                provider="openai-compatible",
                model_ref=model_ref,
                runtime=str(runtime) if runtime else None,
            )
            declarations[(declaration.source, declaration.model_id)] = declaration

    manifest_root = project_root / "manifests"
    if manifest_root.is_dir():
        for path in sorted(manifest_root.glob("*.yaml")):
            payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if (
                not isinstance(payload, dict)
                or payload.get("manifest_type") != "qualification_matrix"
            ):
                continue
            model_payloads = list(payload.get("models", []) or [])
            challenger = payload.get("challenger_qualification", {}) or {}
            if isinstance(challenger, dict):
                model_payloads.extend(challenger.get("models", []) or [])
            for item in model_payloads:
                if not isinstance(item, dict) or not item.get("id"):
                    continue
                declaration = Ap03ModelDeclaration(
                    source=str(path.relative_to(project_root)),
                    model_id=str(item["id"]),
                    provider=str(item.get("provider")) if item.get("provider") else None,
                    model_ref=str(item.get("model_ref")) if item.get("model_ref") else None,
                    quantization=(
                        str(item.get("quantization")) if item.get("quantization") else None
                    ),
                )
                declarations[(declaration.source, declaration.model_id)] = declaration
    return tuple(declarations[key] for key in sorted(declarations))


def _historical_input_state_hash(artifacts: tuple[Ap03ArtifactCheck, ...]) -> str:
    """Bind historical semantic inputs without making reports part of their source identity."""

    included = [
        item
        for item in artifacts
        if item.artifact_id in {"v8_review_audit", "development_golden_suite"}
    ]
    payload = [
        {
            "artifact_id": item.artifact_id,
            "status": item.status.value,
            "sha256": item.sha256,
            "model_sha256": item.model_sha256,
        }
        for item in included
    ]
    return _canonical_sha256(payload)


def _b0_historical_reference() -> dict[str, str]:
    semantic_root = Path(__file__).resolve().parents[2] / "resources" / "semantic"
    payload = json.loads((semantic_root / "prompts" / AP03_B0_RESOURCE).read_text(encoding="utf-8"))
    reference = payload["historical_reference"]
    if not isinstance(reference, dict):
        raise ValueError("AP03 B0 historical reference must be an object")
    return {str(key): str(value) for key, value in reference.items()}


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha256(value: Any) -> str:
    rendered = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()
