"""Bridge accepted sparse Presence gates to the unchanged D4 OR (D3 AND D1).

Only accepted gates enter the legacy detail interface. Unresolved gates are not
converted into false and are explicitly absent from its qualified population.
The projection is never used as general semantic consensus or an adoption source.
"""

from __future__ import annotations

import json
import tempfile
from collections import Counter
from collections.abc import Callable
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path

from standards_atlas.application.evaluation.repository import PromptRepository
from standards_atlas.application.model.source_structure import structure_fingerprint
from standards_atlas.application.semantic_qualification.applicability_decision_policy import (
    confirmation_is_required,
    rescue_is_required,
)
from standards_atlas.application.semantic_qualification.applicability_detail_enrichment import (
    ApplicabilityDetailEnrichmentConfig,
    ApplicabilityDetailEnrichmentReport,
    ApplicabilityDetailEnrichmentService,
    ApplicabilityDetailSelection,
    _canonical_sha256,
    build_applicability_detail_selection,
)
from standards_atlas.application.semantic_qualification.applicability_policy_runner import (
    ApplicabilityPolicyRunReport,
    _normalized_results,
    _role_selection,
    run_applicability_policy,
)
from standards_atlas.application.semantic_qualification.consensus import (
    ClauseConsensus,
    ConsensusCategory,
    ConsensusReport,
    OverallConsensusStatus,
)
from standards_atlas.application.semantic_qualification.mixed_evidence import MixedConsensusReport
from standards_atlas.application.semantic_qualification.partial_proposals import _atomic_json
from standards_atlas.application.semantic_qualification.performance import MeasuredLlmGateway
from standards_atlas.application.semantic_qualification.proposals import SemanticTaskRepository
from standards_atlas.application.semantic_qualification.qualification_coverage import (
    build_qualification_coverage,
)
from standards_atlas.application.semantic_qualification.run_selection import (
    QualificationRunSelection,
    QualificationSelectionClause,
)


def mixed_policy_inputs(report, examples, *, task_version="2.0.0", generated_at=None):
    indexed = {e.id: e for e in examples}
    known = [c for c in report.clauses if c.decision("applicability_present").known]
    clauses = []
    for clause in known:
        decision = clause.decision("applicability_present")
        # Insufficient means no numerical *model* consensus for a deterministic
        # source; deterministic acceptance remains explicit in the mixed report.
        category = (
            ConsensusCategory(decision.category)
            if decision.source == "models"
            else (ConsensusCategory.INSUFFICIENT)
        )
        clauses.append(
            ClauseConsensus(
                clause_id=clause.clause_id,
                document_key=clause.document_key,
                reference=clause.reference,
                heading=clause.heading,
                clause_text=indexed[clause.example_id].input["content"]["text"],
                category=category,
                confidence=decision.confidence or 0,
                applicability_category=category,
                applicability_present=decision.value,
                applicability_confidence=decision.confidence or 0,
                applicability_presence_confidence=decision.confidence or 0,
                applicability_decision_confidence=decision.confidence or 0,
                participating_models=decision.observed_model_count,
                applicability_participating_models=decision.observed_model_count,
                requires_review=False,
                overall_status=OverallConsensusStatus.PARTIAL,
                resolution_sources={"applicability": f"{decision.source}:{decision.stage}"},
            )
        )
    counts = dict(Counter(c.category.value for c in clauses))
    projection = ConsensusReport(
        matrix_id=report.matrix_id,
        corpus_id=report.corpus_id,
        prompt_id="taxonomy-partial-v2",
        reasoning_mode_id="disabled",
        generated_at=generated_at or datetime.now(UTC),
        model_count=len(
            {m for c in known for m in c.decision("applicability_present").model_values}
        ),
        clause_count=len(clauses),
        clauses=tuple(clauses),
        categories=counts,
        review_count=0,
    )
    selection = QualificationRunSelection(
        task="semantic-attribute-observation",
        dataset_version="1.0.0",
        corpus_id=report.corpus_id,
        dataset_sha256=report.selection_sha256,
        corpus_sha256=report.selection_sha256,
        dataset_clause_count=len(examples),
        corpus_clause_count=len(examples),
        selected_clause_count=len(examples),
        clauses=tuple(
            QualificationSelectionClause(
                example_id=c.example_id, document_key=c.document_key, clause_id=c.clause_id
            )
            for c in report.clauses
        ),
    )
    coverage = build_qualification_coverage(selection=selection, report=projection)
    detail_selection = build_applicability_detail_selection(
        run_selection=selection,
        examples=examples,
        consensus=projection,
        coverage=coverage,
        task_version=task_version,
    )
    return projection, detail_selection, coverage


class _LazyGateway:
    def __init__(self, factory):
        self.factory, self.gateway = factory, None

    def _get(self):
        if self.gateway is None:
            self.gateway = self.factory()
        return self.gateway

    def health(self):
        return self._get().health()

    def generate_structured(self, request):
        return self._get().generate_structured(request)


def run_mixed_applicability(
    *,
    report: MixedConsensusReport,
    examples,
    manifest,
    root: Path,
    resources: Path,
    gateway_context: Callable,
):
    """Run/reuse existing detail services, including their normal three-valued failures."""
    if not manifest.applicability_decision_policy.enabled:
        return None
    directory = root / "policy"
    directory.mkdir(exist_ok=True)
    projection_path = directory / "known-gate-consensus.json"
    existing_projection = (
        ConsensusReport.model_validate_json(projection_path.read_bytes())
        if (projection_path.exists())
        else None
    )
    projection, selection, coverage = mixed_policy_inputs(
        report,
        examples,
        generated_at=existing_projection.generated_at if existing_projection else None,
    )
    if existing_projection and existing_projection != projection:
        # A repaired cascade failure can make a previously unknown gate known.
        # Preserve the old detail population, never mix its decisions into the
        # new population or silently reuse a report with a different selection.
        history = root / "policy-history"
        history.mkdir(exist_ok=True)
        revision = history / structure_fingerprint(existing_projection.model_dump(mode="json"))
        if revision.exists():
            raise ValueError("conflicting archived detail revision; choose a new output")
        directory.rename(revision)
        directory.mkdir()

    _atomic_json(projection_path, projection.model_dump(mode="json"))
    _atomic_json(directory / "known-gate-coverage.json", coverage.model_dump(mode="json"))
    _atomic_json(
        directory / "applicability-policy-selection.json", selection.model_dump(mode="json")
    )
    policy = manifest.applicability_decision_policy
    model = next(m for m in manifest.models if m.id == policy.model)
    with ExitStack() as stack:
        measured = MeasuredLlmGateway(
            _LazyGateway(lambda: stack.enter_context(gateway_context(model)))
        )
        services, existing = {}, {}
        for role in ("primary", "rescue", "confirmation"):
            spec = getattr(policy, role)
            config = ApplicabilityDetailEnrichmentConfig.model_validate(
                {
                    **manifest.applicability_detail_enrichment.model_dump(mode="json"),
                    "task_version": spec.task_version,
                    "prompt_version": spec.prompt_version,
                }
            )
            _task, schema = SemanticTaskRepository(resources / "tasks").load(
                config.task, spec.task_version
            )
            prompt = PromptRepository(resources / "prompts").load(config.task, spec.prompt_version)
            role_root = directory / role
            role_root.mkdir(exist_ok=True)
            services[role] = ApplicabilityDetailEnrichmentService(
                measured,
                config=config,
                prompt=prompt,
                canonical_schema=schema,
                model_id=model.id,
                model_ref=model.model_ref or model.id,
                artifact_root=role_root / "artifacts",
            )
            path = role_root / "applicability-detail-enrichment.json"
            existing[role] = (
                ApplicabilityDetailEnrichmentReport.model_validate_json(path.read_bytes())
                if path.is_file()
                else None
            )

        def checkpoint(role, role_selection, detail_report):
            _atomic_json(
                directory / role / "applicability-detail-selection.json",
                role_selection.model_dump(mode="json"),
            )
            _atomic_json(
                directory / role / "applicability-detail-enrichment.json",
                detail_report.model_dump(mode="json"),
            )

        try:
            result = run_applicability_policy(
                selection=selection,
                consensus=projection,
                examples=examples,
                primary_service=services["primary"],
                rescue_service=services["rescue"],
                confirmation_service=services["confirmation"],
                existing_primary=existing["primary"],
                existing_rescue=existing["rescue"],
                existing_confirmation=existing["confirmation"],
                checkpoint=checkpoint,
                request_count=lambda: measured.timing.request_count,
            )
        finally:
            executions = directory / "executions"
            executions.mkdir(exist_ok=True)
            timing_dir = Path(tempfile.mkdtemp(prefix="execution-", dir=executions))
            _atomic_json(
                timing_dir / "request-timing.json", measured.timing.model_dump(mode="json")
            )
    for role in services:
        checkpoint(role, result.selections[role], result.reports[role])
    _atomic_json(directory / "applicability-policy-run.json", result.report.model_dump(mode="json"))
    from standards_atlas.application.semantic_qualification.partial_cascade import (
        write_partial_cascade_costs,
    )

    write_partial_cascade_costs(root)
    return result.report


def verify_mixed_applicability(*, read, names, report, examples, manifest):
    """Check accepted gates, per-role results and selective routes before adoption."""
    path = "policy/applicability-policy-run.json"
    if path not in names:
        return None
    if not manifest.applicability_decision_policy.enabled:
        raise ValueError("unexpected applicability policy for a disabled configuration")
    projection = ConsensusReport.model_validate_json(read("policy/known-gate-consensus.json"))
    expected, selection, coverage = mixed_policy_inputs(
        report, examples, generated_at=projection.generated_at
    )
    if projection != expected:
        raise ValueError("policy gates differ from accepted mixed Presence decisions")
    if json.loads(read("policy/known-gate-coverage.json")) != coverage.model_dump(mode="json"):
        raise ValueError("policy gate coverage differs from mixed consensus")
    if json.loads(read("policy/applicability-policy-selection.json")) != selection.model_dump(
        mode="json"
    ):
        raise ValueError("policy selection differs from accepted gates")
    policy_report = ApplicabilityPolicyRunReport.model_validate_json(read(path))
    if (
        policy_report.source_consensus_sha256 != selection.source_consensus_sha256
        or policy_report.source_selection_sha256 != selection.fingerprint
        or policy_report.source_matrix_id != report.matrix_id
        or policy_report.source_corpus_id != report.corpus_id
    ):
        raise ValueError("policy report source identity differs from mixed gates")
    policy = manifest.applicability_decision_policy
    model = next(m for m in manifest.models if m.id == policy.model)
    normalized = {}
    role_clauses = {"primary": selection.clauses}
    for role in ("primary", "rescue", "confirmation"):
        spec = getattr(policy, role)
        expected_role = _role_selection(
            selection, clauses=role_clauses[role], task_version=spec.task_version
        )
        role_selection = ApplicabilityDetailSelection.model_validate_json(
            read(f"policy/{role}/applicability-detail-selection.json")
        )
        detail = ApplicabilityDetailEnrichmentReport.model_validate_json(
            read(f"policy/{role}/applicability-detail-enrichment.json")
        )
        config = ApplicabilityDetailEnrichmentConfig.model_validate(
            {
                **manifest.applicability_detail_enrichment.model_dump(mode="json"),
                "task_version": spec.task_version,
                "prompt_version": spec.prompt_version,
            }
        )
        if (
            detail.config_sha256 != _canonical_sha256(config.model_dump(mode="json"))
            or role_selection != expected_role
            or detail.selection_sha256 != expected_role.fingerprint
            or detail.model_id != model.id
            or detail.model_ref != (model.model_ref or model.id)
            or detail.task_version != spec.task_version
            or detail.prompt_version != spec.prompt_version
        ):
            raise ValueError("detail role provenance differs from the qualified policy")
        if detail.processed_clause_count != expected_role.selected_clause_count:
            raise ValueError("incomplete detail role cannot be adopted")
        normalized[role] = _normalized_results(detail, expected_role, role=role)
        if role == "primary":
            role_clauses["rescue"] = tuple(
                c
                for c in selection.clauses
                if rescue_is_required(normalized[role].get((c.document_key, c.clause_id)))
            )
        elif role == "rescue":
            role_clauses["confirmation"] = tuple(
                c
                for c in role_clauses["rescue"]
                if confirmation_is_required(
                    primary=normalized["primary"].get((c.document_key, c.clause_id)),
                    rescue=normalized["rescue"].get((c.document_key, c.clause_id)),
                )
            )
    known = {(c.document_key, c.clause_id): c for c in projection.clauses}
    if set(known) != {(c.document_key, c.clause_id) for c in policy_report.cases}:
        raise ValueError("policy results must cover exactly accepted gates, not unknown ones")
    for case in policy_report.cases:
        key = (case.document_key, case.clause_id)
        if case.gate_present != known[key].applicability_present:
            raise ValueError("policy result gate differs from mixed consensus")
        for role in normalized:
            if getattr(case, f"{role}_present") != normalized[role].get(key):
                raise ValueError("policy detail result differs from archived role evidence")
    return policy_report
