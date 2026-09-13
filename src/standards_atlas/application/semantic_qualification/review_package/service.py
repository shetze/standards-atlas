"""Shared application API for CLI now and distinct MCP/Web adapters in later slices."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from standards_atlas.application.semantic_qualification.partial_proposals import _json_bytes

from .model import (
    EvidenceQuote,
    HumanDecisionInput,
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
    """Single-decision compatibility entry point for the local human CLI."""
    return record_decisions(
        root,
        expected_revision=expected_revision,
        reviewer=reviewer,
        decisions=(
            HumanDecisionInput(
                example_id=example_id,
                attribute=attribute,
                status=status,
                proposal_sha256=proposal_sha256,
                predicate=predicate,
                comment=comment,
            ),
        ),
    )


def record_decisions(
    root: Path,
    *,
    expected_revision: int,
    reviewer: str,
    decisions: tuple[HumanDecisionInput, ...],
    expected_package_sha256: str | None = None,
) -> ReviewState:
    """Atomically commit explicit human decisions; invalid batches leave no partial reviews.

    Reviewer identity is declared, not authenticated. Web view/CSRF/attestation guards
    are enforced by its separate adapter. No model or MCP tool calls this operation.
    """
    if type(expected_revision) is not int or expected_revision < 0:
        raise ValueError("expected review revision must be a nonnegative integer")
    keys = [(item.example_id, item.attribute) for item in decisions]
    if not keys or len(keys) != len(set(keys)):
        raise ValueError("human decision batch must be nonempty and unique per attribute")
    with review_lock(root / ".review.lock"):
        package, state = load_review(root)
        if expected_package_sha256 and package.package_sha256 != expected_package_sha256:
            raise ValueError("human decisions belong to a different review package")
        if state.revision != expected_revision:
            raise ValueError("stale review revision; reload before deciding")
        result = state
        for item in decisions:
            result = _add_human_decision(package, result, item, reviewer)
        # All entries must validate before the single atomic write and history snapshot.
        write_state(root, state, result)
        return result


def _add_human_decision(package, state, item: HumanDecisionInput, reviewer: str) -> ReviewState:
    proposal = next((p for p in state.proposals if p.proposal_sha256 == item.proposal_sha256), None)
    predicate = item.predicate
    if item.status == "confirmed":
        if proposal is None or predicate is not None:
            raise ValueError("confirm requires a stored proposal, not a replacement predicate")
        predicate = proposal.predicate
    prior = active_decisions(state).get((item.example_id, item.attribute))
    decision = seal(
        ReviewDecision,
        {
            **item.model_dump(mode="json"),
            "revision": state.revision + 1,
            "predicate": predicate_data(predicate) if predicate else None,
            "supersedes": prior.decision_sha256 if prior else None,
            "reviewer": reviewer,
            "reviewed_at": datetime.now(UTC),
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
    # Cross-attribute conflicts stay visible during review but block publication.
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
