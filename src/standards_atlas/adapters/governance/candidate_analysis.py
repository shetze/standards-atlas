"""Deterministic policy-candidate analysis for governance selection profiles."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

from standards_atlas.adapters.gemara import GemaraControlMapper
from standards_atlas.adapters.gemara.control_traceability import build_control_traceability
from standards_atlas.adapters.governance.subject_group_resources import (
    ResourceGovernanceSubjectGroupProfileRepository,
)
from standards_atlas.application.governance.subject_groups import (
    GovernanceSubjectGroupProfileReader,
    resolve_governance_subject_selection,
)
from standards_atlas.application.model import PublicationDocument
from standards_atlas.domain.model import (
    Clause,
    GovernanceCandidateAnalysis,
    GovernanceCandidateDecision,
    GovernanceCandidateSignal,
    GovernanceClauseSelectionResult,
    GovernancePolicyCandidate,
    GovernanceSelectionProfile,
    GovernanceSubjectSelectionResolution,
)


class GovernanceCandidateAnalyzer:
    """Evaluate generated Gemara controls with clause-local selector semantics."""

    def __init__(
        self,
        *,
        subject_groups: GovernanceSubjectGroupProfileReader | None = None,
    ) -> None:
        self._subject_groups = subject_groups or ResourceGovernanceSubjectGroupProfileRepository()

    def analyze(
        self,
        profile: GovernanceSelectionProfile,
        documents: tuple[PublicationDocument, ...],
    ) -> GovernanceCandidateAnalysis:
        subject_selection = resolve_governance_subject_selection(profile, self._subject_groups)
        candidates: list[GovernancePolicyCandidate] = []
        for document in sorted(documents, key=lambda item: item.key.value):
            candidates.extend(
                self._document_candidates(
                    profile,
                    document,
                    effective_subjects=subject_selection.effective_subjects,
                )
            )

        ordered = tuple(sorted(candidates, key=lambda item: (item.document_key, item.control_id)))
        return GovernanceCandidateAnalysis(
            **{
                "profile-id": profile.id,
                "profile-version": profile.version,
                "documents": tuple(sorted(document.key.value for document in documents)),
                "subject-selection": GovernanceSubjectSelectionResolution(
                    **{
                        "subject-group-profile": (
                            profile.selection.subject_group_profile
                            if subject_selection.profile is not None
                            else None
                        ),
                        "primary-subject-groups": subject_selection.requested_groups,
                        "explicit-primary-subjects": subject_selection.explicit_subjects,
                        "effective-primary-subjects": subject_selection.effective_subjects,
                    }
                ),
                "selected": sum(
                    item.decision is GovernanceCandidateDecision.SELECTED for item in ordered
                ),
                "excluded": sum(
                    item.decision is GovernanceCandidateDecision.EXCLUDED for item in ordered
                ),
                "undetermined": sum(
                    item.decision is GovernanceCandidateDecision.UNDETERMINED for item in ordered
                ),
                "candidates": ordered,
            }
        )

    def _document_candidates(
        self,
        profile: GovernanceSelectionProfile,
        document: PublicationDocument,
        *,
        effective_subjects: tuple[str, ...],
    ) -> list[GovernancePolicyCandidate]:
        catalog = GemaraControlMapper().map(document)
        traceability = build_control_traceability(
            document,
            catalog,
            exported_artifact_sha256="0" * 64,
        )
        entries_by_control: dict[str, list[object]] = {}
        for entry in traceability.entries:
            entries_by_control.setdefault(entry.owner_control_id, []).append(entry)
        clauses = {clause.id.value: clause for clause in document.clauses}

        result: list[GovernancePolicyCandidate] = []
        for control in catalog.controls or ():
            trace_entries = entries_by_control.get(control.id, [])
            source_clause_ids = tuple(sorted({entry.clause_id for entry in trace_entries}))
            source_clauses = tuple(clauses[item] for item in source_clause_ids if item in clauses)
            standard_signal = self._standard_signal(profile, document, source_clauses)
            clause_results = tuple(
                self._evaluate_clause(profile, clause, effective_subjects=effective_subjects)
                for clause in source_clauses
            )
            decision = _control_decision(standard_signal, clause_results)
            aggregate_signal = _clause_aggregate_signal(decision, clause_results)
            result.append(
                GovernancePolicyCandidate(
                    document_key=document.key.value,
                    control_id=control.id,
                    title=control.title,
                    source_clause_ids=source_clause_ids,
                    assessment_requirement_ids=tuple(
                        requirement.id for requirement in control.assessment_requirements
                    ),
                    decision=decision,
                    signals=(standard_signal, aggregate_signal),
                    **{
                        "matching-clause-ids": tuple(
                            item.clause_id
                            for item in clause_results
                            if item.decision is GovernanceCandidateDecision.SELECTED
                        ),
                        "undetermined-clause-ids": tuple(
                            item.clause_id
                            for item in clause_results
                            if item.decision is GovernanceCandidateDecision.UNDETERMINED
                        ),
                        "clause-results": clause_results,
                    },
                )
            )
        return result

    def _standard_signal(
        self,
        profile: GovernanceSelectionProfile,
        document: PublicationDocument,
        clauses: tuple[Clause, ...],
    ) -> GovernanceCandidateSignal:
        keys = {document.key.value}
        for clause in clauses:
            ref = clause.reference
            keys.add(ref.standard)
            if ref.part:
                keys.add(f"{ref.standard}-{ref.part}")

        excluded = tuple(sorted(keys & set(profile.standards.exclude)))
        if excluded:
            return _signal(
                "standards",
                GovernanceCandidateDecision.EXCLUDED,
                "candidate matches excluded standard",
                profile.standards.exclude,
                excluded,
            )
        if profile.standards.include:
            included = tuple(sorted(keys & set(profile.standards.include)))
            if included:
                return _signal(
                    "standards",
                    GovernanceCandidateDecision.SELECTED,
                    "candidate is inside included standard boundary",
                    profile.standards.include,
                    included,
                )
            return _signal(
                "standards",
                GovernanceCandidateDecision.EXCLUDED,
                "candidate is outside included standard boundary",
                profile.standards.include,
                tuple(sorted(keys)),
            )
        return _signal(
            "standards",
            GovernanceCandidateDecision.SELECTED,
            "profile does not restrict standards",
            (),
            tuple(sorted(keys)),
        )

    def _evaluate_clause(
        self,
        profile: GovernanceSelectionProfile,
        clause: Clause,
        *,
        effective_subjects: tuple[str, ...],
    ) -> GovernanceClauseSelectionResult:
        signals: list[GovernanceCandidateSignal] = []
        semantic = profile.selection
        dimensions = (
            ("process-functions", semantic.process_functions, "process_functions"),
            ("knowledge-kinds", semantic.knowledge_kinds, "knowledge_kinds"),
            ("statement-functions", semantic.statement_functions, "statement_functions"),
        )
        for label, expected_values, attr in dimensions:
            if not expected_values:
                continue
            expected = tuple(item.value for item in expected_values)
            observed = tuple(
                sorted(item.value for item in getattr(clause.semantic_classification, attr))
            )
            signals.append(_dimension_signal(label, expected, observed))

        primary_subject = (
            clause.primary_subject.normalized_label if clause.primary_subject else None
        )
        ambiguous = tuple(sorted(clause.subject_context.ambiguous_candidates))
        if effective_subjects:
            if primary_subject is not None:
                signals.append(
                    _dimension_signal(
                        "primary-subject",
                        effective_subjects,
                        (primary_subject,),
                    )
                )
            elif ambiguous:
                signals.append(
                    _signal(
                        "primary-subject",
                        GovernanceCandidateDecision.UNDETERMINED,
                        "clause primary subject is ambiguous",
                        effective_subjects,
                        ambiguous,
                    )
                )
            else:
                signals.append(
                    _signal(
                        "primary-subject",
                        GovernanceCandidateDecision.UNDETERMINED,
                        "clause has no qualified primary subject",
                        effective_subjects,
                        (),
                    )
                )

        return GovernanceClauseSelectionResult(
            **{
                "clause-id": clause.id.value,
                "decision": _clause_decision(tuple(signals)),
                "primary-subject": primary_subject,
                "ambiguous-primary-subjects": ambiguous,
                "signals": tuple(signals),
            }
        )


def render_candidate_analysis_json(analysis: GovernanceCandidateAnalysis) -> str:
    payload = analysis.model_dump(mode="json", by_alias=True, exclude_none=True)
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def render_candidate_analysis_csv(analysis: GovernanceCandidateAnalysis) -> str:
    stream = io.StringIO()
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(
        (
            "document_key",
            "control_id",
            "title",
            "decision",
            "source_clause_ids",
            "matching_clause_ids",
            "matching_primary_subjects",
            "undetermined_clause_ids",
            "reasons",
        )
    )
    for item in analysis.candidates:
        writer.writerow(
            (
                item.document_key,
                item.control_id,
                item.title,
                item.decision.value,
                ";".join(item.source_clause_ids),
                ";".join(item.matching_clause_ids),
                ";".join(item.matching_primary_subjects),
                ";".join(item.undetermined_clause_ids),
                _candidate_reasons(item),
            )
        )
    return stream.getvalue()


def write_candidate_analysis(
    analysis: GovernanceCandidateAnalysis,
    target: Path,
    *,
    replace_existing: bool = True,
) -> tuple[Path, Path]:
    json_target = target
    csv_target = target.with_suffix(".csv")
    if not replace_existing:
        for path in (json_target, csv_target):
            if path.exists():
                raise FileExistsError(
                    f"Governance candidate analysis target already exists: {path}"
                )
    json_target.parent.mkdir(parents=True, exist_ok=True)
    json_target.write_text(render_candidate_analysis_json(analysis), encoding="utf-8")
    csv_target.write_text(render_candidate_analysis_csv(analysis), encoding="utf-8")
    return json_target, csv_target


def _dimension_signal(
    dimension: str,
    expected: tuple[str, ...],
    observed: tuple[str, ...],
) -> GovernanceCandidateSignal:
    if not observed:
        return _signal(
            dimension,
            GovernanceCandidateDecision.UNDETERMINED,
            "clause has no qualified values for requested semantic dimension",
            expected,
            observed,
        )
    if set(expected) & set(observed):
        return _signal(
            dimension,
            GovernanceCandidateDecision.SELECTED,
            "clause matches requested semantic dimension",
            expected,
            observed,
        )
    return _signal(
        dimension,
        GovernanceCandidateDecision.EXCLUDED,
        "clause conflicts with requested semantic dimension",
        expected,
        observed,
    )


def _signal(
    dimension: str,
    outcome: GovernanceCandidateDecision,
    reason: str,
    expected: tuple[object, ...] | list[object],
    observed: tuple[object, ...] | list[object],
) -> GovernanceCandidateSignal:
    return GovernanceCandidateSignal(
        dimension=dimension,
        outcome=outcome,
        reason=reason,
        expected=tuple(str(item) for item in expected if item is not None),
        observed=tuple(str(item) for item in observed),
    )


def _clause_decision(
    signals: tuple[GovernanceCandidateSignal, ...],
) -> GovernanceCandidateDecision:
    outcomes = {signal.outcome for signal in signals}
    if GovernanceCandidateDecision.EXCLUDED in outcomes:
        return GovernanceCandidateDecision.EXCLUDED
    if GovernanceCandidateDecision.UNDETERMINED in outcomes:
        return GovernanceCandidateDecision.UNDETERMINED
    return GovernanceCandidateDecision.SELECTED


def _control_decision(
    standard_signal: GovernanceCandidateSignal,
    clause_results: tuple[GovernanceClauseSelectionResult, ...],
) -> GovernanceCandidateDecision:
    if standard_signal.outcome is GovernanceCandidateDecision.EXCLUDED:
        return GovernanceCandidateDecision.EXCLUDED
    outcomes = {item.decision for item in clause_results}
    if GovernanceCandidateDecision.SELECTED in outcomes:
        return GovernanceCandidateDecision.SELECTED
    if GovernanceCandidateDecision.UNDETERMINED in outcomes:
        return GovernanceCandidateDecision.UNDETERMINED
    return GovernanceCandidateDecision.EXCLUDED


def _clause_aggregate_signal(
    decision: GovernanceCandidateDecision,
    clause_results: tuple[GovernanceClauseSelectionResult, ...],
) -> GovernanceCandidateSignal:
    selected = tuple(
        item.clause_id
        for item in clause_results
        if item.decision is GovernanceCandidateDecision.SELECTED
    )
    undetermined = tuple(
        item.clause_id
        for item in clause_results
        if item.decision is GovernanceCandidateDecision.UNDETERMINED
    )
    if decision is GovernanceCandidateDecision.SELECTED:
        reason = "at least one source clause matches all active semantic dimensions"
        observed = selected
    elif decision is GovernanceCandidateDecision.UNDETERMINED:
        reason = "no clause matches completely and at least one clause lacks required evidence"
        observed = undetermined
    else:
        reason = "no source clause matches all active semantic dimensions"
        observed = tuple(item.clause_id for item in clause_results)
    return _signal("clauses", decision, reason, (), observed)


def _candidate_reasons(candidate: GovernancePolicyCandidate) -> str:
    reasons = [f"{signal.dimension}: {signal.reason}" for signal in candidate.signals]
    for result in candidate.clause_results:
        if result.decision is candidate.decision or (
            candidate.decision is GovernanceCandidateDecision.UNDETERMINED
            and result.decision is GovernanceCandidateDecision.UNDETERMINED
        ):
            reasons.extend(
                f"{result.clause_id}/{signal.dimension}: {signal.reason}"
                for signal in result.signals
                if signal.outcome is not GovernanceCandidateDecision.SELECTED
            )
    return " | ".join(reasons)
