"""Atomic, idempotent model-only annotation submission over the Slice-1 contract."""

from __future__ import annotations

from pathlib import Path

from standards_atlas.application.model.source_structure import structure_fingerprint

from .preparation_model import AnnotationBatch
from .service import add_proposal, load_review
from .storage import review_lock, write_state


def record_model_recommendations(
    root: Path, *, package_sha256: str, expected_revision: int, batch: AnnotationBatch
) -> dict:
    if type(expected_revision) is not int or expected_revision < 0:
        raise ValueError("expected review revision must be a nonnegative integer")
    with review_lock(root / ".review.lock"):
        package, state = load_review(root)
        if package.package_sha256 != package_sha256:
            raise ValueError("recommendations belong to a different review package")
        signature = structure_fingerprint(
            {
                "package_sha256": package_sha256,
                "expected_revision": expected_revision,
                "batch": batch.model_dump(mode="json"),
            }
        )
        prefix = f"mcp-review-batch:{batch.request_id}:"
        provenance = prefix + signature
        prior = [p for p in state.proposals if p.provenance.startswith(prefix)]
        if prior:
            if any(p.provenance != provenance for p in prior) or len(prior) != len(
                batch.recommendations
            ):
                raise ValueError("request_id already used for different recommendations")
            return _receipt(state, prior, reused=True)
        if state.revision != expected_revision:
            raise ValueError("stale review revision; reload before submitting recommendations")
        selected = {case.example_id: case for case in package.cases}
        sources = {source.example_id: source for source in package.population}
        result = state
        for item in batch.recommendations:
            if item.example_id not in selected:
                raise ValueError("recommendation is outside the materialized review selection")
            if sources[item.example_id].source_sha256 != item.source_sha256:
                raise ValueError("recommendation source/context fingerprint mismatch")
            result = add_proposal(
                package,
                result,
                example_id=item.example_id,
                attribute=item.attribute,
                predicate=item.predicate,
                producer=batch.actor,
                producer_kind="model",
                model=batch.model,
                rationale=item.rationale,
                provenance=provenance,
                evidence=item.evidence,
            )
        # A later invalid predicate/evidence quote never leaves a partially committed batch.
        write_state(root, state, result)
        return _receipt(result, result.proposals[len(state.proposals) :], reused=False)


def _receipt(state, proposals, *, reused):
    return {
        "revision": state.revision,
        "state_sha256": state.state_sha256,
        "proposal_sha256s": [p.proposal_sha256 for p in proposals],
        "idempotent_replay": reused,
        "human_decisions_added": 0,
    }
