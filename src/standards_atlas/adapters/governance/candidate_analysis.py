"""Clause-local policy-candidate analysis for governance selection profiles."""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from pathlib import Path

from standards_atlas.adapters.gemara import GemaraControlMapper
from standards_atlas.adapters.gemara.control_traceability import build_control_traceability
from standards_atlas.adapters.governance.subject_group_resources import (
    ResourceGovernanceSubjectGroupProfileRepository,
)
from standards_atlas.application.governance import (
    GovernanceSubjectGroupProfileReader,
    ResolvedGovernanceSubjectSelection,
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
from standards_atlas.domain.model.subject_normalization import normalize_subject_label


@dataclass(frozen=True)
class _ControlSelectionCandidate:
    document_key: str
    control_id: str
    title: str
    source_clause_ids: tuple[str, ...]
    assessment_requirement_ids: tuple[str, ...]
    clauses: tuple[Clause, ...]


class GovernanceCandidateAnalyzer:
    """Evaluate generated controls using clause-local orthogonal selector semantics."""

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
        resolved_subjects = resolve_governance_subject_selection(
            profile,
            self._subject_groups,
        )
        candidates: list[GovernancePolicyCandidate] = []
        for document in sorted(documents, key=lambda item: item.key.value):
            candidates.extend(self._document_candidates(profile, document, resolved_subjects))

        ordered = tuple(sorted(candidates, key=lambda item: (item.document_key, item.control_id)))
        return GovernanceCandidateAnalysis(
            **{
                "profile-id": profile.id,
                "profile-version": profile.version,
                "documents": tuple(sorted(document.key.value for document in documents)),
                "subject-selection": _subject_selection_resolution(resolved_subjects),
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
        resolved_subjects: ResolvedGovernanceSubjectSelection,
    ) -> list[GovernancePolicyCandidate]:
        return [
            self._evaluate_control(profile, document, candidate, resolved_subjects)
            for candidate in self._project_controls(document)
        ]

    @staticmethod
    def _project_controls(
        document: PublicationDocument,
    ) -> tuple[_ControlSelectionCandidate, ...]:
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

        candidates: list[_ControlSelectionCandidate] = []
        for control in catalog.controls or ():
            trace_entries = entries_by_control.get(control.id, [])
            source_clause_ids = tuple(sorted({entry.clause_id for entry in trace_entries}))
            source_clauses = tuple(clauses[item] for item in source_clause_ids if item in clauses)
            candidates.append(
                _ControlSelectionCandidate(
                    document_key=document.key.value,
                    control_id=control.id,
                    title=control.title,
                    source_clause_ids=source_clause_ids,
                    assessment_requirement_ids=tuple(
                        requirement.id for requirement in control.assessment_requirements
                    ),
                    clauses=source_clauses,
                )
            )
        return tuple(candidates)

    def _evaluate_control(
        self,
        profile: GovernanceSelectionProfile,
        document: PublicationDocument,
        candidate: _ControlSelectionCandidate,
        resolved_subjects: ResolvedGovernanceSubjectSelection,
    ) -> GovernancePolicyCandidate:
        standard_signal = _standard_signal(profile, document, candidate.clauses)
        clause_results = tuple(
            self._evaluate_clause(profile, clause, resolved_subjects)
            for clause in candidate.clauses
        )
        semantic_decision = _control_clause_decision(clause_results)
        aggregate_signal = _aggregate_clause_signal(
            semantic_decision,
            clause_results,
        )

        decision = (
            GovernanceCandidateDecision.EXCLUDED
            if standard_signal.outcome is GovernanceCandidateDecision.EXCLUDED
            else semantic_decision
        )
        return GovernancePolicyCandidate(
            document_key=candidate.document_key,
            control_id=candidate.control_id,
            title=candidate.title,
            source_clause_ids=candidate.source_clause_ids,
            assessment_requirement_ids=candidate.assessment_requirement_ids,
            decision=decision,
            signals=(standard_signal, aggregate_signal),
            matching_clause_ids=tuple(
                item.clause_id
                for item in clause_results
                if item.decision is GovernanceCandidateDecision.SELECTED
            ),
            undetermined_clause_ids=tuple(
                item.clause_id
                for item in clause_results
                if item.decision is GovernanceCandidateDecision.UNDETERMINED
            ),
            clause_results=clause_results,
        )

    @staticmethod
    def _evaluate_clause(
        profile: GovernanceSelectionProfile,
        clause: Clause,
        resolved_subjects: ResolvedGovernanceSubjectSelection,
    ) -> GovernanceClauseSelectionResult:
        semantic = profile.selection
        signals: list[GovernanceCandidateSignal] = []
        dimensions = (
            (
                "process-functions",
                tuple(item.value for item in semantic.process_functions),
                tuple(item.value for item in clause.semantic_classification.process_functions),
            ),
            (
                "knowledge-kinds",
                tuple(item.value for item in semantic.knowledge_kinds),
                tuple(item.value for item in clause.semantic_classification.knowledge_kinds),
            ),
            (
                "statement-functions",
                tuple(item.value for item in semantic.statement_functions),
                tuple(item.value for item in clause.semantic_classification.statement_functions),
            ),
        )
        for label, expected, observed in dimensions:
            if expected:
                signals.append(
                    _dimension_signal(
                        label,
                        expected,
                        tuple(sorted(set(observed))),
                    )
                )

        effective_subjects = resolved_subjects.effective_subjects
        primary_subject = (
            clause.primary_subject.normalized_label if clause.primary_subject is not None else None
        )
        ambiguous_subjects = tuple(
            sorted(
                {
                    normalize_subject_label(item)
                    for item in clause.subject_context.ambiguous_candidates
                    if normalize_subject_label(item)
                }
            )
        )
        if effective_subjects:
            if primary_subject is None:
                reason = (
                    "clause primary subject is ambiguous"
                    if ambiguous_subjects
                    else "clause has no qualified primary subject"
                )
                signals.append(
                    _signal(
                        "primary-subject",
                        "undetermined",
                        reason,
                        effective_subjects,
                        ambiguous_subjects,
                    )
                )
            elif primary_subject in set(effective_subjects):
                signals.append(
                    _signal(
                        "primary-subject",
                        "selected",
                        "clause primary subject matches requested subject selection",
                        effective_subjects,
                        (primary_subject,),
                    )
                )
            else:
                signals.append(
                    _signal(
                        "primary-subject",
                        "excluded",
                        "clause primary subject conflicts with requested subject selection",
                        effective_subjects,
                        (primary_subject,),
                    )
                )

        if not signals:
            signals.append(
                _signal(
                    "semantic-selection",
                    "selected",
                    "profile does not restrict semantic candidate dimensions",
                    (),
                    (),
                )
            )

        return GovernanceClauseSelectionResult(
            clause_id=clause.id.value,
            decision=_clause_decision(tuple(signals)),
            primary_subject=primary_subject,
            ambiguous_subjects=ambiguous_subjects,
            signals=tuple(signals),
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
        matching_results = tuple(
            result
            for result in item.clause_results
            if result.decision is GovernanceCandidateDecision.SELECTED
        )
        writer.writerow(
            (
                item.document_key,
                item.control_id,
                item.title,
                item.decision.value,
                ";".join(item.source_clause_ids),
                ";".join(item.matching_clause_ids),
                ";".join(
                    sorted(
                        {
                            result.primary_subject
                            for result in matching_results
                            if result.primary_subject is not None
                        }
                    )
                ),
                ";".join(item.undetermined_clause_ids),
                " | ".join(f"{signal.dimension}: {signal.reason}" for signal in item.signals),
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
    json_target.write_text(
        render_candidate_analysis_json(analysis),
        encoding="utf-8",
    )
    csv_target.write_text(
        render_candidate_analysis_csv(analysis),
        encoding="utf-8",
    )
    return json_target, csv_target


def _subject_selection_resolution(
    resolved: ResolvedGovernanceSubjectSelection,
) -> GovernanceSubjectSelectionResolution:
    return GovernanceSubjectSelectionResolution(
        profile_id=resolved.profile.id if resolved.profile is not None else None,
        profile_version=(resolved.profile.version if resolved.profile is not None else None),
        requested_groups=resolved.requested_groups,
        explicit_subjects=resolved.explicit_subjects,
        effective_subjects=resolved.effective_subjects,
    )


def _standard_signal(
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
            "excluded",
            "candidate matches excluded standard",
            profile.standards.exclude,
            excluded,
        )
    if profile.standards.include:
        included = tuple(sorted(keys & set(profile.standards.include)))
        if included:
            return _signal(
                "standards",
                "selected",
                "candidate is inside included standard boundary",
                profile.standards.include,
                included,
            )
        return _signal(
            "standards",
            "excluded",
            "candidate is outside included standard boundary",
            profile.standards.include,
            tuple(sorted(keys)),
        )
    return _signal(
        "standards",
        "selected",
        "profile does not restrict standards",
        (),
        tuple(sorted(keys)),
    )


def _dimension_signal(
    dimension: str,
    expected: tuple[str, ...],
    observed: tuple[str, ...],
) -> GovernanceCandidateSignal:
    if not observed:
        return _signal(
            dimension,
            "undetermined",
            "clause has no qualified values for requested semantic dimension",
            expected,
            observed,
        )
    if set(expected) & set(observed):
        return _signal(
            dimension,
            "selected",
            "clause matches requested semantic dimension",
            expected,
            observed,
        )
    return _signal(
        dimension,
        "excluded",
        "clause conflicts with requested semantic dimension",
        expected,
        observed,
    )


def _aggregate_clause_signal(
    decision: GovernanceCandidateDecision,
    results: tuple[GovernanceClauseSelectionResult, ...],
) -> GovernanceCandidateSignal:
    selected = tuple(
        item.clause_id for item in results if item.decision is GovernanceCandidateDecision.SELECTED
    )
    undetermined = tuple(
        item.clause_id
        for item in results
        if item.decision is GovernanceCandidateDecision.UNDETERMINED
    )
    if decision is GovernanceCandidateDecision.SELECTED:
        reason = "at least one source clause satisfies all active selection dimensions"
        observed = selected
    elif decision is GovernanceCandidateDecision.UNDETERMINED:
        reason = (
            "no source clause is a confirmed match and at least one could match "
            "if missing qualified evidence were available"
        )
        observed = undetermined
    else:
        reason = "all source clauses explicitly conflict with at least one active dimension"
        observed = tuple(item.clause_id for item in results)
    return _signal(
        "clause-selection",
        decision.value,
        reason,
        (),
        observed,
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


def _control_clause_decision(
    results: tuple[GovernanceClauseSelectionResult, ...],
) -> GovernanceCandidateDecision:
    outcomes = {item.decision for item in results}
    if GovernanceCandidateDecision.SELECTED in outcomes:
        return GovernanceCandidateDecision.SELECTED
    if GovernanceCandidateDecision.UNDETERMINED in outcomes:
        return GovernanceCandidateDecision.UNDETERMINED
    return GovernanceCandidateDecision.EXCLUDED


def _signal(
    dimension: str,
    outcome: str,
    reason: str,
    expected: tuple[object, ...] | list[object],
    observed: tuple[object, ...] | list[object],
) -> GovernanceCandidateSignal:
    return GovernanceCandidateSignal(
        dimension=dimension,
        outcome=GovernanceCandidateDecision(outcome),
        reason=reason,
        expected=tuple(str(item) for item in expected if item is not None),
        observed=tuple(str(item) for item in observed),
    )
