"""Shared application API for CLI now and distinct MCP/Web adapters in later slices."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from standards_atlas.application.semantic_qualification.partial_proposals import _json_bytes

from .model import (
    EvidenceQuote,
    ReviewDecision,
    ReviewPackage,
    ReviewProposal,
    ReviewState,
    SemanticPredicate,
    predicate_data,
    validate_predicate,
)
from .sources import resolve_evidence
from .storage import review_lock, write_state
from .validation import active_decisions, review_report, seal, verify_package, verify_state


def load_review(root: Path) -> tuple[ReviewPackage, ReviewState]:
    if root.is_symlink():
        raise ValueError("unsafe review package symlink")
    for name in ("review-package.json", "review-state.json"):
        if (root / name).is_symlink():
            raise ValueError("unsafe review artifact symlink")
    package = ReviewPackage.model_validate_json((root / "review-package.json").read_bytes())
    state = ReviewState.model_validate_json((root / "review-state.json").read_bytes())
    verify_package(package)
    verify_state(package, state)
    return package, state


def empty_state(package: ReviewPackage) -> ReviewState:
    return seal(ReviewState, {"package_sha256": package.package_sha256}, "state_sha256")


def add_proposal(
    package: ReviewPackage,
    state: ReviewState,
    *,
    example_id: str,
    attribute: str,
    predicate: SemanticPredicate,
    producer: str,
    producer_kind: str,
    rationale: str,
    provenance: str,
    model: str | None = None,
    evidence: tuple[EvidenceQuote, ...] = (),
    created_at: datetime | None = None,
) -> ReviewState:
    """Pure transition; no authority to add, replace or confirm human decisions."""
    verify_state(package, state)
    source = next((s for s in package.population if s.example_id == example_id), None)
    if source is None:
        raise ValueError("proposal source is absent from frozen population")
    validate_predicate(attribute, predicate, package.output_schema)
    proposal = seal(
        ReviewProposal,
        {
            "revision": state.revision + 1,
            "example_id": example_id,
            "attribute": attribute,
            "predicate": predicate_data(predicate),
            "producer": producer,
            "producer_kind": producer_kind,
            "model": model,
            "rationale": rationale,
            "provenance": provenance,
            "created_at": created_at or datetime.now(UTC),
            "evidence": [resolve_evidence(source, quote).model_dump() for quote in evidence],
        },
        "proposal_sha256",
    )
    result = seal(
        ReviewState,
        {
            **state.model_dump(mode="json"),
            "revision": proposal.revision,
            "proposals": [
                *(p.model_dump(mode="json") for p in state.proposals),
                proposal.model_dump(mode="json"),
            ],
        },
        "state_sha256",
    )
    verify_state(package, result)
    return result


def record_proposal(root: Path, *, expected_revision: int, **kwargs) -> ReviewState:
    with review_lock(root / ".review.lock"):
        package, state = load_review(root)
        if state.revision != expected_revision:
            raise ValueError("stale review revision; reload before submitting")
        result = add_proposal(package, state, **kwargs)
        write_state(root, state, result)
        return result


def record_decision(
    root: Path,
    *,
    expected_revision: int,
    example_id: str,
    attribute: str,
    status: str,
    reviewer: str,
    proposal_sha256: str | None = None,
    predicate: SemanticPredicate | None = None,
    comment: str = "",
) -> ReviewState:
    """Human-only adapter operation. Actor identity is declared, not authenticated by this API."""
    with review_lock(root / ".review.lock"):
        package, state = load_review(root)
        if state.revision != expected_revision:
            raise ValueError("stale review revision; reload before deciding")
        proposal = next((p for p in state.proposals if p.proposal_sha256 == proposal_sha256), None)
        if status == "confirmed":
            if proposal is None or predicate is not None:
                raise ValueError("confirm requires a stored proposal, not a replacement predicate")
            predicate = proposal.predicate
        prior = active_decisions(state).get((example_id, attribute))
        decision = seal(
            ReviewDecision,
            {
                "revision": state.revision + 1,
                "example_id": example_id,
                "attribute": attribute,
                "status": status,
                "predicate": predicate_data(predicate) if predicate else None,
                "proposal_sha256": proposal_sha256,
                "supersedes": prior.decision_sha256 if prior else None,
                "reviewer": reviewer,
                "reviewed_at": datetime.now(UTC),
                "comment": comment,
            },
            "decision_sha256",
        )
        result = seal(
            ReviewState,
            {
                **state.model_dump(mode="json"),
                "revision": decision.revision,
                "decisions": [
                    *(d.model_dump(mode="json") for d in state.decisions),
                    decision.model_dump(mode="json"),
                ],
            },
            "state_sha256",
        )
        verify_state(package, result)
        # Contradictions can remain visible during partial review, but block publication.
        write_state(root, state, result)
        return result


def describe_review(root: Path, *, example_id: str | None = None) -> dict:
    package, state = load_review(root)
    report = review_report(package, state)
    if example_id is not None:
        case = next((c for c in package.cases if c.example_id == example_id), None)
        if case is None:
            raise ValueError("case is not in this review package")
        source = next(s for s in package.population if s.example_id == example_id)
        report["case"] = case.model_dump(mode="json")
        report["source"] = source.model_dump(mode="json")
        report["proposals"] = [
            p.model_dump(mode="json") for p in state.proposals if p.example_id == example_id
        ]
        report["reviews"] = [
            d.model_dump(mode="json")
            for (i, _), d in active_decisions(state).items()
            if i == example_id
        ]
    else:
        report["cases"] = [c.model_dump(mode="json") for c in package.cases]
    return json.loads(_json_bytes(report))
