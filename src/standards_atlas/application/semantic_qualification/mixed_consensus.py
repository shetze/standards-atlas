"""Accept real partial observations and qualified structural decisions together.

The default full-answer consensus remains unchanged. This resolver is called by
ModelConsensusService's explicit partial entry point; cascade routing consumes
exactly these same acceptance decisions rather than a second review heuristic.
"""

from __future__ import annotations

import json
from collections import Counter
from typing import Any

from jsonschema import Draft202012Validator

from standards_atlas.application.evaluation.models import EvaluationExample
from standards_atlas.application.model.source_structure import structure_fingerprint
from standards_atlas.application.semantic_qualification.mixed_evidence import (
    AttributeAcceptance,
    CompletionProfile,
    MixedClauseConsensus,
    MixedConsensusReport,
    StagedPartialObservation,
)
from standards_atlas.application.semantic_qualification.partial_observations import (
    PARTIAL_ATTRIBUTES,
    PRIMARY_SET_FIELDS,
    validate_partial_response,
)
from standards_atlas.application.semantic_qualification.partial_requests import (
    PartialProposalConfig,
    PartialTaskResources,
)
from standards_atlas.application.semantic_qualification.qualification_matrix import (
    CascadeResolutionConfig,
    ConsensusConfig,
)
from standards_atlas.application.semantic_qualification.taxonomy_decisions import (
    derive_clause_decision_plan,
    load_taxonomy_rules,
)


def input_selection_fingerprint(examples: tuple[EvaluationExample, ...]) -> str:
    # Expected annotations/tags are not inputs, even in run identity or archives.
    return structure_fingerprint([{"id": e.id, "input": e.input} for e in examples])


def _key(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


def _canonical_value(attribute: str, value: Any) -> Any:
    if attribute == "role_relations":
        from standards_atlas.domain.model import RoleRelation

        relations = [RoleRelation.model_validate(item).model_dump(mode="json") for item in value]
        return sorted(relations, key=_key)
    if isinstance(value, list):
        return sorted(value, key=_key)
    return value


def _changed(item: AttributeAcceptance, **changes: Any) -> AttributeAcceptance:
    return AttributeAcceptance.model_validate({**item.model_dump(mode="json"), **changes})


def _model_decision(
    attribute: str,
    values: dict[str, Any],
    evidence_ids: tuple[str, ...],
    *,
    stage: str,
    resolution: CascadeResolutionConfig,
    consensus: ConsensusConfig,
    stage_model_count: int,
    attempted: bool,
) -> AttributeAcceptance:
    from standards_atlas.application.semantic_qualification.consensus import (
        _category_for_confidence,
    )

    count = len(values)
    base = dict(
        attribute=attribute,
        model_values=values,
        observed_model_count=count,
        evidence_ids=evidence_ids,
        stage=stage,
        source="models" if values else "none",
        rule="attribute-model-consensus-v1" if values else None,
    )
    if not count:
        return AttributeAcceptance(
            **base,
            status="unresolved" if attempted else "not_evaluated",
            reasons=("missing_model_evidence",) if attempted else ("not_evaluated",),
        )
    minimum = resolution.minimum_successful_models
    threshold = consensus.majority_threshold
    unanimity = False
    resolver = False
    if attribute == "primary_function":
        threshold = max(threshold, resolution.minimum_confidence)
        resolver = resolution.statement_function_resolution_mode == "stage_resolver"
        if resolver:
            threshold = max(threshold, resolution.statement_function_resolver_min_confidence)
    elif attribute == "primary_knowledge_kind":
        threshold = max(threshold, resolution.minimum_knowledge_kind_confidence or 0)
        unanimity = (
            resolution.minimum_knowledge_kind_confidence is None
            and resolution.escalate_on_knowledge_kind_disagreement
        )
    elif attribute == "applicability_present":
        minimum = resolution.minimum_applicability_presence_models or minimum
        configured = resolution.minimum_applicability_presence_confidence
        if configured is None:
            configured = resolution.minimum_applicability_confidence
        threshold = max(threshold, configured or 0)
        unanimity = configured is None and (
            resolution.escalate_on_applicability_presence_disagreement
            if resolution.escalate_on_applicability_presence_disagreement is not None
            else resolution.escalate_on_applicability_disagreement
        )
    elif attribute == "role_semantics_present":
        configured = resolution.minimum_role_relation_confidence
        threshold = max(threshold, configured or 0)
        unanimity = configured is None and resolution.escalate_on_role_relation_disagreement
    elif attribute == "primary_process_function":
        threshold = max(threshold, resolution.minimum_process_function_confidence or 0)
        unanimity = (
            resolution.minimum_process_function_confidence is None
            and resolution.escalate_on_process_function_disagreement
        )
        resolver = resolution.process_function_resolution_mode == "stage_resolver"
        if resolver:
            threshold = max(threshold, resolution.process_function_resolver_min_confidence)
    elif attribute == "process_functions":
        threshold = max(threshold, resolution.minimum_process_set_confidence or 0)
        unanimity = (
            resolution.minimum_process_set_confidence is None
            and resolution.escalate_on_process_set_disagreement
        )
    if resolver:
        # Stage resolvers use only that stage's actual voters, never the cumulative
        # model count. Requiring its full configured population prevents a lone
        # surviving answer in a two-model stage from masquerading as unanimity.
        minimum = min(minimum, stage_model_count) if stage_model_count else minimum

    is_set = attribute in {pair[1] for pair in PRIMARY_SET_FIELDS} | {"role_relations"}
    if is_set:
        labels = {_key(label): label for value in values.values() for label in value}
        candidate = [
            labels[key]
            for key in sorted(labels)
            if sum(key in {_key(label) for label in value} for value in values.values()) / count
            >= consensus.label_threshold
        ]
    else:
        frequencies = Counter(_key(value) for value in values.values())
        winner = sorted(frequencies, key=lambda key: (-frequencies[key], key))[0]
        candidate = json.loads(winner)
    supporting = tuple(sorted(model for model, value in values.items() if value == candidate))
    confidence = len(supporting) / count
    category = _category_for_confidence(
        confidence, count, minimum, consensus.strong_threshold, consensus.majority_threshold
    ).value
    reasons = []
    if count < minimum:
        reasons.append("insufficient_models")
    if category not in resolution.accepted_categories:
        reasons.append("consensus_category")
    if category in consensus.review_policy.review_categories:
        reasons.append("review_category")
    if attribute == "primary_function" and category == "majority_consensus":
        threshold = max(threshold, consensus.review_policy.accept_majority_min_confidence)
        if count < consensus.review_policy.accept_majority_min_models:
            reasons.append("review_minimum_models")
    if attribute == "applicability_present" and candidate is True:
        threshold = max(threshold, consensus.review_policy.applicability_min_confidence)
    if attribute == "role_semantics_present" and candidate is True:
        threshold = max(threshold, consensus.review_policy.role_relation_min_confidence)
    if confidence < threshold:
        reasons.append("decision_confidence")
    if unanimity and confidence < 1:
        reasons.append("disagreement")
    # A primary null is an observed absent primary, not absent evidence. It cannot
    # answer a required statement/knowledge primary classification, however.
    if candidate is None and attribute in {"primary_function", "primary_knowledge_kind"}:
        reasons.append("no_primary_classification")
    return AttributeAcceptance(
        **base,
        status="unresolved" if reasons else "accepted",
        value=None if reasons else candidate,
        proposed_value=candidate,
        category=category,
        confidence=confidence,
        supporting_models=supporting,
        reasons=tuple(dict.fromkeys(reasons)),
    )


def evaluate_mixed_consensus(
    *,
    matrix_id: str,
    corpus_id: str,
    stage_id: str,
    examples: tuple[EvaluationExample, ...],
    observations: tuple[StagedPartialObservation, ...],
    resolution: CascadeResolutionConfig,
    consensus: ConsensusConfig,
    resources,
    completion_profile: CompletionProfile | None = None,
    stage_model_count: int = 0,
    previous: MixedConsensusReport | None = None,
) -> MixedConsensusReport:
    """Re-derive structure, count sparse evidence, and retain accepted attributes.

    Historical observations can be repeated on resume but are never independent
    votes. Changed same-model answers at a later stage replace that model's open
    attribute answer, not add a voter. Within-stage contradictions are rejected.
    """
    if not examples or len({e.id for e in examples}) != len(examples):
        raise ValueError("mixed selection must be nonempty with unique example ids")
    completion_profile = completion_profile or CompletionProfile()
    fingerprint = input_selection_fingerprint(examples)
    if previous and (
        previous.matrix_id != matrix_id
        or previous.corpus_id != corpus_id
        or previous.selection_sha256 != fingerprint
        or previous.completion_profile != completion_profile
        or previous.consensus_policy != consensus.model_dump(mode="json")
    ):
        raise ValueError("previous mixed consensus belongs to a different selection or policy")
    cfg = PartialProposalConfig(
        corpus_id=corpus_id, dataset_version="schema", provider="schema", model="schema"
    )
    schema = dict(PartialTaskResources.load(resources, cfg).schema)
    validator = Draft202012Validator(schema)
    plans = {
        e.id: derive_clause_decision_plan(
            e.input["context"],
            text=e.input["content"]["text"],
            content_hash=e.input["content"]["hash"],
        )
        for e in examples
    }
    by_coordinate = {(p.source.document_key, p.source.clause_id): key for key, p in plans.items()}
    if len(by_coordinate) != len(examples):
        raise ValueError("mixed selection contains duplicate clause coordinates")
    by_example: dict[str, list[StagedPartialObservation]] = {key: [] for key in plans}
    seen: dict[tuple[str, str, str, str], Any] = {}
    for staged in observations:
        observation = staged.observation
        coordinate = (observation.plan.clause.document_key, observation.plan.clause.clause_id)
        if coordinate not in by_coordinate:
            raise ValueError("partial observation outside the frozen selection")
        key = by_coordinate[coordinate]
        if observation.plan.decision_plan.fingerprint != plans[key].fingerprint:
            raise ValueError("partial observation uses a different source or rule plan")
        if observation.outcome == "evaluated":
            errors = list(validator.iter_errors(observation.values))
            if errors:
                raise ValueError(f"invalid partial model evidence: {errors[0].message}")
            validate_partial_response(observation.values, schema, observation.plan)
            for attribute, value in observation.model_evidence().items():
                identity = (staged.stage, key, observation.voter_key, attribute)
                value = _canonical_value(attribute, value)
                if identity in seen and seen[identity] != value:
                    raise ValueError("conflicting answers from the same model in one stage")
                seen[identity] = value
        by_example[key].append(staged)
    previous_clauses = {item.example_id: item for item in previous.clauses} if previous else {}
    clauses = []
    for example in examples:
        plan = plans[example.id]
        old = previous_clauses.get(example.id)
        if old and old.decision_plan.fingerprint != plan.fingerprint:
            raise ValueError("accepted source structure changed; start a new mixed run")
        choices: dict[str, AttributeAcceptance] = {}
        for attribute in PARTIAL_ATTRIBUTES:
            source_decision = plan.decision(attribute)
            values: dict[str, Any] = {}
            ids: dict[str, str] = {}
            attempted = False
            resolver = (
                attribute == "primary_function"
                and resolution.statement_function_resolution_mode == "stage_resolver"
            ) or (
                attribute == "primary_process_function"
                and resolution.process_function_resolution_mode == "stage_resolver"
            )
            for staged in by_example[example.id]:
                obs = staged.observation
                if resolver and staged.stage != stage_id:
                    continue
                if attribute == "applicability_present" and not staged.applicability_eligible:
                    continue
                attempted |= attribute in obs.plan.requested_attributes
                evidence = obs.model_evidence()
                if attribute in evidence:
                    values[obs.voter_key] = _canonical_value(attribute, evidence[attribute])
                    ids[obs.voter_key] = obs.observation_id
            if source_decision.state == "conflict":
                choices[attribute] = AttributeAcceptance(
                    attribute=attribute,
                    status="conflict",
                    reasons=("source_conflict",),
                    evidence_ids=tuple(
                        e for item in source_decision.evidence for e in item.source_fingerprints
                    ),
                )
            elif source_decision.state == "fixed":
                choices[attribute] = AttributeAcceptance(
                    attribute=attribute,
                    status="accepted",
                    value=source_decision.value,
                    source="deterministic",
                    stage=old.decision(attribute).stage if old else stage_id,
                    rule=f"{plan.rules_id}:{plan.rules_version}",
                    category="deterministic",
                    evidence_ids=tuple(
                        e
                        for item in source_decision.evidence
                        if item.fixes_attribute
                        for e in item.source_fingerprints
                    ),
                    diagnostics=("model_dissent_to_structural_decision",)
                    if any(value != source_decision.value for value in values.values())
                    else (),
                )
            elif old and old.decision(attribute).known:
                frozen = old.decision(attribute)
                choices[attribute] = _changed(
                    frozen,
                    diagnostics=tuple(
                        dict.fromkeys(
                            (
                                *frozen.diagnostics,
                                *(
                                    ("later_model_dissent",)
                                    if any(value != frozen.value for value in values.values())
                                    else ()
                                ),
                            )
                        )
                    ),
                )
            else:
                choices[attribute] = _model_decision(
                    attribute,
                    values,
                    tuple(sorted(set(ids.values()))),
                    stage=stage_id,
                    resolution=resolution,
                    consensus=consensus,
                    stage_model_count=stage_model_count,
                    attempted=attempted,
                )
        consistency = []
        for primary, collection in PRIMARY_SET_FIELDS:
            p, s = choices[primary], choices[collection]
            if p.known and p.value is not None and s.known and p.value not in s.value:
                reason = f"primary_set_conflict:{primary}:{collection}"
                # Keep the accepted primary, but do not fabricate set membership.
                # If the set was frozen earlier, keep it and reject the new primary.
                reject = primary if old and old.decision(collection).known else collection
                item = choices[reject]
                choices[reject] = _changed(
                    item,
                    status="conflict",
                    value=None,
                    proposed_value=item.value,
                    reasons=(reason,),
                )
                if set((primary, collection)) & set(completion_profile.required_attributes):
                    consistency.append(reason)
        presence = choices["role_semantics_present"]
        tuple_evidence = choices["role_relations"].model_values
        if presence.known and presence.value is False and any(tuple_evidence.values()):
            if old and old.decision("role_semantics_present").known:
                choices["role_semantics_present"] = _changed(
                    presence,
                    diagnostics=tuple(
                        dict.fromkeys((*presence.diagnostics, "later_role_tuple_dissent"))
                    ),
                )
            else:
                choices["role_semantics_present"] = _changed(
                    presence,
                    status="conflict",
                    value=None,
                    proposed_value=False,
                    reasons=("role_semantics_evidence_conflict",),
                )
        context = example.input["context"]
        clauses.append(
            MixedClauseConsensus(
                example_id=example.id,
                clause_id=plan.source.clause_id,
                document_key=plan.source.document_key,
                content_hash=plan.source.content_hash,
                reference=str(context.get("reference") or plan.source.clause_id),
                heading=context.get("heading"),
                decision_plan=plan,
                required_attributes=completion_profile.required_attributes,
                decisions=tuple(choices[key] for key in PARTIAL_ATTRIBUTES),
                consistency_reasons=tuple(consistency),
                resolution_sha256=structure_fingerprint(resolution.model_dump(mode="json")),
            )
        )
    return MixedConsensusReport(
        matrix_id=matrix_id,
        corpus_id=corpus_id,
        stage_id=stage_id,
        completion_profile=completion_profile,
        selection_sha256=fingerprint,
        resolution=resolution.model_dump(mode="json"),
        consensus_policy=consensus.model_dump(mode="json"),
        stage_model_count=stage_model_count,
        source_rules_sha256=load_taxonomy_rules().fingerprint,
        previous_report_sha256=previous.fingerprint if previous else None,
        clauses=tuple(clauses),
    )
