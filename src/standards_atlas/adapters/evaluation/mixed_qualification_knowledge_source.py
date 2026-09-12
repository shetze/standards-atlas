"""Adopt verified sparse cascade decisions without manufacturing missing values.

The archive reader supplies checksum-verified bytes. Replaying the sparse
acceptance chain establishes its source/stage identity before any patch is built.
The applicability gate is never used in place of the final detail policy.
"""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path
from typing import Any

from standards_atlas.application.model.knowledge_adoption import (
    ClauseKnowledgeCandidate,
    KnowledgeAdoptionBatch,
)
from standards_atlas.application.semantic_qualification.mixed_applicability import (
    verify_mixed_applicability,
)
from standards_atlas.application.semantic_qualification.partial_cascade_archive import (
    verify_partial_cascade,
)
from standards_atlas.domain.model.enrichment_patch import (
    ClauseEnrichmentPatch,
    SemanticEnrichmentPatch,
)
from standards_atlas.domain.model.knowledge_state import (
    DecisionSupport,
    GeneratedAttribute,
    GenerationMethod,
)

GENERATOR = "taxonomy-partial-adoption-v1"
DIMENSIONS = {
    "primary_function": "statement_functions",
    "statement_functions": "statement_functions",
    "primary_knowledge_kind": "knowledge_kinds",
    "knowledge_kinds": "knowledge_kinds",
    "primary_process_function": "process_functions",
    "process_functions": "process_functions",
    "applicability_present": "applicability",
    "role_semantics_present": "role_semantics",
    "role_relations": "role_semantics",
}


def load_mixed_qualification_knowledge(
    archive, dimensions: tuple[str, ...]
) -> KnowledgeAdoptionBatch:
    resources = Path(str(files("standards_atlas.resources").joinpath("semantic")))
    report, examples, manifest = verify_partial_cascade(
        read=archive.read,
        names=archive.names,
        resources=resources,
    )
    policy = verify_mixed_applicability(
        read=archive.read,
        names=archive.names,
        report=report,
        examples=examples,
        manifest=manifest,
    )
    cases = {(c.document_key, c.clause_id): c for c in policy.cases} if policy else {}
    candidates = []
    for clause in report.clauses:
        values: dict[str, Any] = {}
        generated = []
        not_evaluated = ["enrichments.semantic.applicability_functions"]
        for decision in clause.decisions:
            field = decision.attribute
            path = f"enrichments.semantic.{field}"
            if DIMENSIONS[field] not in dimensions:
                not_evaluated.append(path)
                continue
            if field == "applicability_present":
                case = cases.get((clause.document_key, clause.clause_id))
                if case is None and decision.status == "not_evaluated":
                    not_evaluated.append(path)
                    continue
                known = case is not None and case.final_present is not None
                if known:
                    values[field] = case.final_present
                artifact = (
                    "policy/applicability-policy-run.json"
                    if case
                    else "mixed-consensus-report.json"
                )
                support = DecisionSupport(
                    rule=(
                        f"{policy.policy_id}:{policy.policy_version}"
                        if case
                        else "final-policy-unavailable"
                    ),
                    source_artifact=f"{archive.id}/{artifact}",
                    source_sha256=archive.sha256(artifact),
                    stage="final-policy" if case else None,
                    # This is a Boolean policy, not a numerical vote. Detailed
                    # model identities/results are retained in its source files.
                    model_ids=tuple(sorted({s.model_id for s in policy.stages})) if case else (),
                )
                generated.append(
                    GeneratedAttribute(
                        path=path,
                        generator=GENERATOR,
                        method=GenerationMethod.IMPORTED,
                        availability="known" if known else "unknown",
                        decision=support,
                        evidence=(clause.decision_plan.source_sha256,),
                    )
                )
                continue
            if decision.status == "not_evaluated":
                not_evaluated.append(path)
                continue
            if decision.known:
                values[field] = decision.value
            # An accepted decision may have been frozen several stages earlier.
            # Its source counts/identity must not become cumulative final counts.
            stage = decision.stage or report.stage_id
            artifact = f"stages/{stage}/mixed-stage-report.json"
            deterministic = (
                decision.source == "deterministic" or "source_conflict" in decision.reasons
            )
            source = DecisionSupport(
                rule=decision.rule or f"sparse-{decision.status}",
                source_artifact=f"{archive.id}/{artifact}",
                source_sha256=archive.sha256(artifact),
                stage=stage,
                prompt_id=None if deterministic else "taxonomy-partial-v2",
                model_ids=() if deterministic else tuple(decision.model_values),
                valid_votes=None if deterministic else decision.observed_model_count,
                supporting_votes=None if deterministic else len(decision.supporting_models),
                category=decision.category,
            )
            generated.append(
                GeneratedAttribute(
                    path=path,
                    generator=GENERATOR,
                    method=GenerationMethod.DETERMINISTIC
                    if deterministic
                    else GenerationMethod.LLM,
                    availability="known" if decision.known else "unknown",
                    decision=source,
                    evidence=(
                        clause.decision_plan.source_sha256,
                        clause.decision_plan.rules_sha256,
                        *decision.evidence_ids,
                    ),
                )
            )
        candidates.append(
            ClauseKnowledgeCandidate(
                document_key=clause.document_key,
                clause_id=clause.clause_id,
                reference=clause.reference,
                heading=clause.heading,
                content_hash=clause.content_hash,
                patch=ClauseEnrichmentPatch(semantic=SemanticEnrichmentPatch(**values)),
                attributes=tuple(generated),
                not_evaluated=tuple(not_evaluated),
                source_requirements=tuple(
                    fact
                    for fact in clause.decision_plan.source.facts
                    if any(
                        fact.fingerprint in a.evidence
                        and a.method == GenerationMethod.DETERMINISTIC
                        and a.availability == "known"
                        for a in generated
                    )
                ),
            )
        )
    return KnowledgeAdoptionBatch(
        schema_version="1.1",
        source_id=archive.id,
        source_sha256=archive.digest,
        selected_clause_count=report.clause_count,
        # Every selected coordinate has a record, including unresolved records.
        # This count describes missing records, not semantic completion.
        unqualified_clause_count=0,
        candidates=tuple(candidates),
    )
