"""Deterministic policy-candidate analysis for governance selection profiles."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

from standards_atlas.adapters.gemara import GemaraControlMapper
from standards_atlas.adapters.gemara.control_traceability import build_control_traceability
from standards_atlas.application.model import PublicationDocument
from standards_atlas.domain.model import (
    GovernanceCandidateAnalysis,
    GovernanceCandidateDecision,
    GovernanceCandidateSignal,
    GovernancePolicyCandidate,
    GovernanceSelectionProfile,
)


class GovernanceCandidateAnalyzer:
    """Evaluate generated Gemara controls against deterministic profile selectors."""

    def analyze(
        self,
        profile: GovernanceSelectionProfile,
        documents: tuple[PublicationDocument, ...],
    ) -> GovernanceCandidateAnalysis:
        if profile.selection.primary_subjects or profile.selection.primary_subject_groups:
            raise ValueError(
                "primary-subject selection requires clause-local candidate analysis v2"
            )
        candidates: list[GovernancePolicyCandidate] = []
        for document in sorted(documents, key=lambda item: item.key.value):
            candidates.extend(self._document_candidates(profile, document))

        ordered = tuple(sorted(candidates, key=lambda item: (item.document_key, item.control_id)))
        return GovernanceCandidateAnalysis(
            **{
                "profile-id": profile.id,
                "profile-version": profile.version,
                "documents": tuple(sorted(document.key.value for document in documents)),
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
            signals = self._signals(profile, document, source_clauses)
            decision = _decision(signals)
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
                    signals=signals,
                )
            )
        return result

    def _signals(
        self,
        profile: GovernanceSelectionProfile,
        document: PublicationDocument,
        clauses: tuple[object, ...],
    ) -> tuple[GovernanceCandidateSignal, ...]:
        signals: list[GovernanceCandidateSignal] = []
        keys = {document.key.value}
        for clause in clauses:
            ref = clause.reference
            keys.add(ref.standard)
            if ref.part:
                keys.add(f"{ref.standard}-{ref.part}")

        excluded = sorted(keys & set(profile.standards.exclude))
        if excluded:
            signals.append(
                _signal(
                    "standards",
                    "excluded",
                    "candidate matches excluded standard",
                    profile.standards.exclude,
                    excluded,
                )
            )
        elif profile.standards.include:
            included = sorted(keys & set(profile.standards.include))
            if included:
                signals.append(
                    _signal(
                        "standards",
                        "selected",
                        "candidate is inside included standard boundary",
                        profile.standards.include,
                        included,
                    )
                )
            else:
                signals.append(
                    _signal(
                        "standards",
                        "excluded",
                        "candidate is outside included standard boundary",
                        profile.standards.include,
                        tuple(sorted(keys)),
                    )
                )
        else:
            signals.append(
                _signal(
                    "standards",
                    "selected",
                    "profile does not restrict standards",
                    (),
                    tuple(sorted(keys)),
                )
            )

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
                sorted(
                    {
                        item.value
                        for clause in clauses
                        for item in getattr(clause.semantic_classification, attr)
                    }
                )
            )
            if not observed:
                signals.append(
                    _signal(
                        label,
                        "undetermined",
                        "candidate has no qualified values for requested semantic dimension",
                        expected,
                        observed,
                    )
                )
            elif set(expected) & set(observed):
                signals.append(
                    _signal(
                        label,
                        "selected",
                        "candidate matches requested semantic dimension",
                        expected,
                        observed,
                    )
                )
            else:
                signals.append(
                    _signal(
                        label,
                        "excluded",
                        "candidate conflicts with requested semantic dimension",
                        expected,
                        observed,
                    )
                )

        return tuple(signals)


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
    json_target.write_text(render_candidate_analysis_json(analysis), encoding="utf-8")
    csv_target.write_text(render_candidate_analysis_csv(analysis), encoding="utf-8")
    return json_target, csv_target


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


def _decision(signals: tuple[GovernanceCandidateSignal, ...]) -> GovernanceCandidateDecision:
    outcomes = {signal.outcome for signal in signals}
    if GovernanceCandidateDecision.EXCLUDED in outcomes:
        return GovernanceCandidateDecision.EXCLUDED
    if GovernanceCandidateDecision.UNDETERMINED in outcomes:
        return GovernanceCandidateDecision.UNDETERMINED
    return GovernanceCandidateDecision.SELECTED
