"""Crash-safe, package-bound navigation and Holdout exposure ledger.

This ledger neither creates human labels nor proves reviewer identity/absence of
prior exposure outside this UI. It is deliberately separate from review-state.json.
"""

from datetime import UTC, datetime
from pathlib import Path

from standards_atlas.application.semantic_qualification.partial_proposals import (
    _atomic_json,
    _json_bytes,
    _preserve_bytes,
)
from standards_atlas.application.semantic_qualification.review_package.candidates import safe_read
from standards_atlas.application.semantic_qualification.review_package.service import load_review
from standards_atlas.application.semantic_qualification.review_package.storage import (
    _sync_directory,
    review_lock,
)
from standards_atlas.application.semantic_qualification.review_package.validation import seal
from standards_atlas.application.semantic_qualification.review_package.workbench import (
    verify_workbench_state,
)

from .model import HoldoutExposure, WorkbenchState


def load_journal(root: Path, package, review_state) -> WorkbenchState:
    path = root / "workbench" / "state.json"
    if path.is_symlink() or path.parent.is_symlink():
        raise ValueError("unsafe workbench journal symlink")
    if not path.exists():
        if (path.parent / "history").exists():
            raise ValueError("Workbench history exists without its current journal")
        return seal(WorkbenchState, {"package_sha256": package.package_sha256}, "workbench_sha256")
    journal = WorkbenchState.model_validate_json(safe_read(path))
    verify_workbench_state(journal, package, review_state)
    return journal


def _save(root: Path, previous: WorkbenchState, **changes) -> WorkbenchState:
    data = {**previous.model_dump(mode="json"), **changes, "revision": previous.revision + 1}
    result = seal(WorkbenchState, data, "workbench_sha256")
    folder = root / "workbench"
    history = folder / "history"
    if folder.is_symlink() or history.is_symlink() or (folder / "state.json").is_symlink():
        raise ValueError("unsafe workbench storage symlink")
    folder.mkdir(exist_ok=True)
    _preserve_bytes(
        history / f"{previous.workbench_sha256}.json",
        _json_bytes(previous.model_dump(mode="json")),
    )
    _sync_directory(history)
    _atomic_json(folder / "state.json", result.model_dump(mode="json"))
    _sync_directory(folder)
    _sync_directory(root)
    return result


def bookmark(root: Path, *, package_sha256: str, reviewer: str, example_id: str) -> None:
    with review_lock(root / ".review.lock"):
        package, state = load_review(root)
        if package.package_sha256 != package_sha256:
            raise ValueError("bookmark belongs to a different review package")
        if example_id not in {c.example_id for c in package.cases}:
            raise ValueError("bookmark is outside the review selection")
        journal = load_journal(root, package, state)
        if journal.bookmarks.get(reviewer) != example_id:
            _save(root, journal, bookmarks={**journal.bookmarks, reviewer: example_id})


def reveal(root: Path, *, view: dict, assessment: str) -> None:
    with review_lock(root / ".review.lock"):
        package, state = load_review(root)
        if package.package_sha256 != view["package_sha256"]:
            raise ValueError("view belongs to a different review package")
        if state.revision != view["revision"] or state.state_sha256 != view["state_sha256"]:
            raise ValueError("stale review revision; reload before revealing recommendations")
        case = next((c for c in package.cases if c.example_id == view["example_id"]), None)
        if case is None or case.split != "holdout":
            raise ValueError("blind reveal is only valid for a selected Holdout case")
        source = next(s for s in package.population if s.example_id == case.example_id)
        exposure = HoldoutExposure(
            example_id=case.example_id,
            reviewer=view["reviewer"],
            assessment=assessment,
            source_sha256=source.source_sha256,
            rules_sha256=package.rules_sha256,
            review_revision=state.revision,
            proposal_sha256s=tuple(
                p.proposal_sha256
                for p in state.proposals
                if p.example_id == case.example_id and p.producer_kind in {"model", "engineering"}
            ),
            revealed_at=datetime.now(UTC),
        )
        journal = load_journal(root, package, state)
        # Repeated identical reveal after a lost response needs no duplicate audit entry.
        matching = [
            e
            for e in journal.exposures
            if e.example_id == case.example_id and e.reviewer == view["reviewer"]
        ]
        if matching and matching[-1].model_dump(exclude={"revealed_at"}) == exposure.model_dump(
            exclude={"revealed_at"}
        ):
            return
        _save(
            root,
            journal,
            exposures=[
                *(e.model_dump(mode="json") for e in journal.exposures),
                exposure.model_dump(mode="json"),
            ],
        )
