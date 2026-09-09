"""Filesystem implementation of workflow artifact operations."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from standards_atlas.adapters.docling import DoclingArtifactRepository
from standards_atlas.adapters.filesystem.document_repository import (
    CURRENT_DOCUMENT_SCHEMA_VERSION,
)
from standards_atlas.application.ports import ExtractionState
from standards_atlas.application.workflow.knowledge_plan import KNOWLEDGE_STAGES
from standards_atlas.application.workflow.models import WorkflowPlan, WorkflowStage, WorkflowStep


class FileSystemWorkflowArtifactStore:
    """Inspect and mutate workflow artifacts below a project root."""

    def docling_extraction_state(
        self, step: WorkflowStep, project_root: Path
    ) -> ExtractionState | None:
        if step.stage is not WorkflowStage.DOCLING:
            return None
        try:
            document_option = step.command.index("-d")
            document_key = step.command[document_option + 1]
            source = Path(step.command[document_option + 2])
        except (ValueError, IndexError):
            return None
        if not source.is_absolute():
            source = project_root / source
        repository = DoclingArtifactRepository(project_root / ".atlas" / "data")
        return repository.extraction_state(document_key, source)

    def outputs_exist(self, step: WorkflowStep, project_root: Path) -> bool:
        if step.stage in KNOWLEDGE_STAGES:
            return False  # Always validate against the current source and accepted state.
        if not step.output_paths and not step.output_globs:
            return False
        paths_exist = all(
            self._output_is_current(project_root / path, path, step) for path in step.output_paths
        )
        globs_exist = all(any(project_root.glob(pattern)) for pattern in step.output_globs)
        if not (paths_exist and globs_exist):
            return False
        fingerprint = _tracked_input_fingerprint(step, project_root)
        if fingerprint is None:
            return True
        try:
            stored = json.loads(_input_marker(step, project_root).read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return False
        return isinstance(stored, dict) and stored.get("fingerprint") == fingerprint

    @staticmethod
    def _output_is_current(path: Path, relative_path: str, step: WorkflowStep) -> bool:
        if not path.exists():
            return False
        normalized = relative_path.replace("\\", "/")
        if normalized.startswith(".atlas/work/workflow/"):
            return _workflow_marker_is_current(path, step)
        if (
            normalized.startswith(".atlas/data/documents/")
            or normalized.startswith(".atlas/work/family-sources/documents/")
        ) and normalized.endswith(".json"):
            return _json_schema_version(path) == CURRENT_DOCUMENT_SCHEMA_VERSION
        return True

    def record_completion(self, step: WorkflowStep, project_root: Path) -> None:
        fingerprint = _tracked_input_fingerprint(step, project_root)
        if fingerprint is not None:
            marker = _input_marker(step, project_root)
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(json.dumps({"schema_version": 1, "fingerprint": fingerprint}) + "\n")
        for relative_path in step.output_paths:
            if not relative_path.startswith(".atlas/work/workflow/"):
                continue
            marker = project_root / relative_path
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "step_fingerprint": _workflow_step_fingerprint(step),
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )

    def remove_outputs(self, step: WorkflowStep, project_root: Path) -> None:
        _input_marker(step, project_root).unlink(missing_ok=True)
        targets = [project_root / path for path in step.output_paths]
        for pattern in step.output_globs:
            targets.extend(project_root.glob(pattern))
        for target in targets:
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink(missing_ok=True)

    def begin_fresh_repetition(self, plan: WorkflowPlan, project_root: Path) -> None:
        if not plan.fresh_repetition_stages:
            return
        completed_marker = _fresh_repetition_marker(plan, project_root)
        in_progress_marker = _fresh_repetition_in_progress_marker(plan, project_root)
        if _fresh_repetition_marker_is_current(in_progress_marker, plan):
            return
        for step in plan.steps:
            if step.stage not in plan.fresh_repetition_stages:
                continue
            for relative_path in step.output_paths:
                if relative_path.startswith(".atlas/work/workflow/"):
                    (project_root / relative_path).unlink(missing_ok=True)
        completed_marker.unlink(missing_ok=True)
        _write_fresh_repetition_marker(in_progress_marker, plan)

    def record_fresh_repetition_completion(self, plan: WorkflowPlan, project_root: Path) -> None:
        if not plan.fresh_repetition_stages:
            return
        in_progress_marker = _fresh_repetition_in_progress_marker(plan, project_root)
        completed_marker = _fresh_repetition_marker(plan, project_root)
        in_progress_marker.unlink(missing_ok=True)
        _write_fresh_repetition_marker(completed_marker, plan)

    def alignment_requires_review(self, project_root: Path, document_key: str) -> bool:
        path = project_root / ".atlas" / "data" / "alignments" / document_key / "alignment.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            statistics = payload["metadata"]["statistics"]
            return bool(statistics.get("missing", 0) or statistics.get("conflicting", 0))
        except (OSError, ValueError, KeyError, TypeError):
            return True


def _json_schema_version(path: Path) -> object | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload.get("schema_version")


def _workflow_step_fingerprint(step: WorkflowStep) -> str:
    payload = {
        "family": step.family,
        "document": step.document,
        "stage": step.stage.value,
        "command": list(step.command),
        "artifact_policy": step.artifact_policy.value,
        "manual_gate": step.manual_gate,
        "output_paths": list(step.output_paths),
        "output_globs": list(step.output_globs),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _fresh_repetition_fingerprint(plan: WorkflowPlan) -> str:
    fresh_stages = set(plan.fresh_repetition_stages)
    payload = {
        "families": list(plan.families),
        "fresh_repetition_stages": [stage.value for stage in plan.fresh_repetition_stages],
        "steps": [
            _workflow_step_fingerprint(step) for step in plan.steps if step.stage in fresh_stages
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _fresh_repetition_marker(plan: WorkflowPlan, project_root: Path) -> Path:
    fingerprint = _fresh_repetition_fingerprint(plan)
    return (
        project_root
        / ".atlas"
        / "work"
        / "workflow"
        / "fresh-repetitions"
        / f"{fingerprint}.complete"
    )


def _fresh_repetition_in_progress_marker(plan: WorkflowPlan, project_root: Path) -> Path:
    fingerprint = _fresh_repetition_fingerprint(plan)
    return (
        project_root
        / ".atlas"
        / "work"
        / "workflow"
        / "fresh-repetitions"
        / f"{fingerprint}.in-progress"
    )


def _write_fresh_repetition_marker(path: Path, plan: WorkflowPlan) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "plan_fingerprint": _fresh_repetition_fingerprint(plan),
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _fresh_repetition_marker_is_current(path: Path, plan: WorkflowPlan) -> bool:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return False
    return (
        isinstance(payload, dict)
        and payload.get("schema_version") == 1
        and payload.get("plan_fingerprint") == _fresh_repetition_fingerprint(plan)
    )


def _workflow_marker_is_current(path: Path, step: WorkflowStep) -> bool:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return False
    return (
        isinstance(payload, dict)
        and payload.get("schema_version") == 1
        and payload.get("step_fingerprint") == _workflow_step_fingerprint(step)
    )


_TRACKED_INPUT_STAGES = {
    WorkflowStage.CORPUS_BUILD,
    WorkflowStage.CONTEXT_ENRICHMENT,
    WorkflowStage.QUALIFICATION_MATRIX,
}


def _input_marker(step: WorkflowStep, root: Path) -> Path:
    return root / ".atlas/work/workflow/input-state" / (_workflow_step_fingerprint(step) + ".json")


def _option(step: WorkflowStep, flag: str, default: str) -> str:
    try:
        return step.command[step.command.index(flag) + 1]
    except (ValueError, IndexError):
        return default


def _tracked_input_fingerprint(step: WorkflowStep, root: Path) -> str | None:
    """Hash live inputs, not file existence. Context writes exclude their own outputs
    in other documents so the repository-wide vocabulary does not cause a loop.
    Renderer code is deliberately not an inference input.
    """
    if step.stage not in _TRACKED_INPUT_STAGES:
        return None
    entries = {}
    workspace = root / _option(step, "--workspace", ".atlas/data")
    if step.stage in {WorkflowStage.CORPUS_BUILD, WorkflowStage.CONTEXT_ENRICHMENT}:
        for path in sorted((workspace / "documents").glob("*.json")):
            content = path.read_bytes()
            if step.stage is WorkflowStage.CONTEXT_ENRICHMENT:
                try:
                    payload = json.loads(content)
                    document = payload["document"]
                    for clause in document.get("clauses", ()):
                        # Only the processed document's accepted contextual output
                        # is tracked, so restoration can invalidate its checkpoint.
                        if path.stem == step.document:
                            clause["enrichments"] = {
                                key: value
                                for key, value in clause.get("enrichments", {}).items()
                                if key in {"subject_context", "context_routing"}
                            }
                        else:
                            clause.pop("enrichments", None)
                        clause.pop("provenance", None)
                    content = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
                except (ValueError, TypeError, KeyError):
                    pass  # Hash invalid bytes too; the command itself reports schema errors.
            entries[str(path)] = hashlib.sha256(content).hexdigest()
    files: set[Path] = set()
    resources = root / "src/standards_atlas/resources"
    if step.stage is WorkflowStage.CORPUS_BUILD:
        files.add(root / "src/standards_atlas/application/context/canonical_cbox.py")
        files.add(root / "src/standards_atlas/application/semantic_qualification/eligibility.py")
        files.update((resources / "semantic/tasks").rglob("*"))
    if step.stage is WorkflowStage.CONTEXT_ENRICHMENT:
        files.add(root / _option(step, "--context-config", "cfg/context-enrichment.yaml"))
        files.update((resources / "semantic/prompts/context-routing-enrichment").rglob("*"))
        files.update((root / "src/standards_atlas/application/context").glob("subject*.py"))
        files.add(root / "src/standards_atlas/application/services/context_enrichment_service.py")
    if step.stage is WorkflowStage.QUALIFICATION_MATRIX:
        policy_root = root / "src/standards_atlas/application/semantic_qualification"
        for name in ("context_framing.py", "request_builder.py", "adaptive_interview.py"):
            files.add(policy_root / name)
        files.add(root / _option(step, "--manifest", "manifests/qualification.yaml"))
        corpus = root / _option(step, "--corpus-root", ".atlas/data/evaluation/corpora")
        files.update(corpus.rglob("dataset.json"))
        files.update(corpus.rglob("corpus.yaml"))
        files.update((resources / "semantic").rglob("*"))
        files.update((resources / "ontologies").rglob("*"))
    for path in sorted(files):
        if path.is_file() and "__pycache__" not in path.parts:
            entries[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        elif not path.exists():
            entries[str(path)] = "missing"
    return hashlib.sha256(
        json.dumps(
            {
                "contract": "workflow-cbox-inputs-v1",
                "step": _workflow_step_fingerprint(step),
                "inputs": entries,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
