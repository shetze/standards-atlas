"""Rebuild cascade consensus from verified local proposals, never from an LLM."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import yaml

from standards_atlas.application.evaluation.models import EvaluationExample
from standards_atlas.application.evaluation.repository import PromptRepository
from standards_atlas.application.semantic_qualification.consensus import ModelConsensusService
from standards_atlas.application.semantic_qualification.proposals import (
    ProposalRunConfig,
    SemanticTaskRepository,
    _safe,
    proposal_run_directory,
)
from standards_atlas.application.semantic_qualification.qualification_matrix import (
    CascadeResolutionConfig,
    CascadeStage,
    MatrixObservation,
    QualificationMatrixManifest,
    resolve_prompt_version,
)
from standards_atlas.application.semantic_qualification.request_builder import (
    build_clause_reference,
    build_proposal_request,
    serialize_generation_request,
)


class ProposalReplay:
    """Isolate only matching proposals before invoking the existing consensus service."""

    def __init__(
        self,
        *,
        manifest: QualificationMatrixManifest,
        runs_output: Path,
        resources: Path,
        corpus_root: Path,
        workspace: Path,
        examples: tuple[EvaluationExample, ...],
    ) -> None:
        self.manifest = manifest
        self.runs_output = runs_output
        self.resources = resources
        self.corpus_root = corpus_root
        self.workspace = workspace
        self.examples = {item.input["context"]["clause_id"]: item for item in examples}
        self.observations: list[MatrixObservation] = []
        self.current: list[MatrixObservation] = []
        self.requires_inference: list[dict[str, object]] = []
        self.known_failures: list[dict[str, object]] = []
        self.fingerprints: dict[str, str] = {}
        self.task, _ = SemanticTaskRepository(resources / "tasks").load(
            manifest.task, manifest.task_version
        )

    def prepare(self, stage: CascadeStage, clause_ids: tuple[str, ...]) -> None:
        manifest = self.manifest
        self.current = []
        for model in manifest.models:
            if model.id not in stage.models:
                continue
            for candidate in manifest.prompts_for_stage(stage):
                version = resolve_prompt_version(
                    candidate, resources=self.resources, task=manifest.task
                )
                prompt = PromptRepository(self.resources / "prompts").load(manifest.task, version)
                for repetition in range(1, manifest.repetitions_for(model) + 1):
                    config = ProposalRunConfig(
                        corpus_id=manifest.corpus_id,
                        task=manifest.task,
                        task_version=manifest.task_version,
                        dataset_version=manifest.dataset_version,
                        prompt_version=version,
                        cbox_frame=candidate.cbox_frame,
                        provider=model.provider,
                        model=model.model_ref or model.id,
                        seed=repetition,
                        max_tokens=(
                            model.generation.max_output_tokens or candidate.max_output_tokens
                        ),
                        adaptive_interview=candidate.adaptive_interview,
                        adaptive_question_max_tokens=(
                            model.generation.adaptive_question_max_tokens
                            or model.generation.max_output_tokens
                            or candidate.max_output_tokens
                        ),
                        truncation_retry_max_tokens=model.generation.truncation_retry_max_tokens,
                        retry_on_truncation=model.generation.retry_on_truncation,
                        reasoning_enabled=(
                            next(
                                item.enabled
                                for item in manifest.reasoning_modes
                                if item.id == manifest.consensus.reasoning_mode_id
                            )
                            if manifest.consensus.reasoning_mode_id != "disabled"
                            else model.generation.reasoning_mode == "enabled"
                        ),
                    )
                    run_root = (
                        self.runs_output
                        / "qualification-runs"
                        / manifest.matrix_id
                        / manifest.consensus.reasoning_mode_id
                        / f"repeat-{repetition}"
                    )
                    original = proposal_run_directory(config, run_root)
                    target = self.workspace / "proposals" / str(len(self.observations))
                    target.mkdir(parents=True)
                    for clause_id in clause_ids:
                        # Production selections use example IDs at the request
                        # boundary. The caller has checked their coordinate mapping.
                        example = self.examples[clause_id]
                        case = original / _safe(example.id)
                        request = build_proposal_request(config, prompt, example.input, self.task)
                        request_path = case / "request.json"
                        missing = {
                            "stage_id": stage.id,
                            "clause_id": clause_id,
                            "model_id": model.id,
                            "prompt_id": candidate.id,
                            "repetition": repetition,
                        }
                        if not request_path.is_file():
                            self.requires_inference.append(
                                {**missing, "reason": "request_not_available"}
                            )
                            continue
                        stored = json.loads(request_path.read_text(encoding="utf-8"))
                        if stored != serialize_generation_request(request):
                            self.requires_inference.append(
                                {**missing, "reason": "request_identity_changed"}
                            )
                            continue
                        evaluation = case / "evaluation.yaml"
                        if not evaluation.is_file():
                            if (case / "failure.json").is_file():
                                self.known_failures.append(missing)
                            else:
                                self.requires_inference.append(
                                    {**missing, "reason": "proposal_not_available"}
                                )
                            continue
                        payload = yaml.safe_load(evaluation.read_text(encoding="utf-8"))
                        annotation = payload.get("annotation_candidate", {})
                        coordinate = annotation.get("clause", {})
                        expected = example.input.get("context", {})
                        if coordinate.get("clause_id") != clause_id:
                            raise ValueError(f"proposal clause identity mismatch: {evaluation}")
                        # The source selection and request identity also tie the
                        # document/text to this input; never substitute another case.
                        if expected.get("document_key") and (
                            coordinate.get("document_key") != expected["document_key"]
                        ):
                            raise ValueError(f"proposal document identity mismatch: {evaluation}")
                        expected_reference = build_clause_reference(example.input)
                        if coordinate.get("content_hash") != expected_reference.content_hash:
                            raise ValueError(f"proposal content identity mismatch: {evaluation}")
                        destination = target / _safe(clause_id)
                        destination.mkdir(parents=True)
                        for name in (
                            "evaluation.yaml",
                            "request.json",
                            "response.json",
                            "interview.json",
                        ):
                            source = case / name
                            if source.is_file():
                                self.fingerprints[str(source.resolve())] = hashlib.sha256(
                                    source.read_bytes()
                                ).hexdigest()
                                shutil.copyfile(source, destination / name)
                    observation = MatrixObservation(
                        prompt_id=candidate.id,
                        model_id=model.id,
                        reasoning_mode_id=manifest.consensus.reasoning_mode_id,
                        repetition=repetition,
                        run_directory=target,
                        # Consensus consumes proposals, not Gold qualification metrics.
                        qualification_report=target / "not-evaluated.json",
                    )
                    self.current.append(observation)
                    self.observations.append(observation)

    def consensus(
        self,
        stage: CascadeStage,
        clause_ids: tuple[str, ...],
        resolution: CascadeResolutionConfig,
        *,
        resolver: bool,
    ):
        manifest = self.manifest
        report, *_ = ModelConsensusService().evaluate(
            matrix_id=manifest.matrix_id,
            corpus_id=manifest.corpus_id,
            prompt_id=manifest.consensus.prompt_id,
            reasoning_mode_id=manifest.consensus.reasoning_mode_id,
            observations=tuple(self.current if resolver else self.observations),
            output_directory=(
                self.workspace / "consensus" / stage.id / ("local" if resolver else "cumulative")
            ),
            corpus_root=self.corpus_root,
            min_models=1 if resolver else resolution.minimum_successful_models,
            strong_threshold=manifest.consensus.strong_threshold,
            majority_threshold=manifest.consensus.majority_threshold,
            label_threshold=manifest.consensus.label_threshold,
            prompt_selection=manifest.consensus.prompt_selection.model_dump(),
            review_policy=manifest.consensus.review_policy.model_dump(),
            adjudication=manifest.consensus.adjudication.model_dump(),
            structural_priors=manifest.consensus.structural_priors.model_dump(),
            example_ids=clause_ids,
            model_dimension_eligibility=manifest.model_dimension_eligibility,
            min_applicability_presence_models=(
                None if resolver else resolution.minimum_applicability_presence_models
            ),
        )
        return report

    def final_consensus(self, clause_ids: tuple[str, ...], resolutions: dict):
        """Re-aggregate existing proposals with the corrected frozen dimensions."""
        manifest = self.manifest
        return ModelConsensusService().evaluate(
            matrix_id=manifest.matrix_id,
            corpus_id=manifest.corpus_id,
            prompt_id=manifest.consensus.prompt_id,
            reasoning_mode_id=manifest.consensus.reasoning_mode_id,
            observations=tuple(self.observations),
            output_directory=self.workspace / "consensus" / "final",
            corpus_root=self.corpus_root,
            min_models=manifest.consensus.min_models,
            strong_threshold=manifest.consensus.strong_threshold,
            majority_threshold=manifest.consensus.majority_threshold,
            label_threshold=manifest.consensus.label_threshold,
            prompt_selection=manifest.consensus.prompt_selection.model_dump(),
            review_policy=manifest.consensus.review_policy.model_dump(),
            adjudication=manifest.consensus.adjudication.model_dump(),
            structural_priors=manifest.consensus.structural_priors.model_dump(),
            example_ids=clause_ids,
            resolution_overrides=resolutions,
            model_dimension_eligibility=manifest.model_dimension_eligibility,
        )
