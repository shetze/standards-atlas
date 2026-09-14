"""Persist agent selection proposals and materialize a new package locally.

The original package is immutable. Known Development, held-out membership and all
existing review events survive materialization. No selection operation approves labels.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from standards_atlas.application.schema import require_supported_schema
from standards_atlas.application.semantic_qualification.partial_comparison import (
    _output_is_separate,
)
from standards_atlas.application.semantic_qualification.partial_proposals import _json_bytes

from .candidates import _digest, index_path, load_candidate_index, safe_read
from .model import ReviewPackage, ReviewState
from .preparation_model import SelectionProposal, SelectionRequest
from .sources import duplicate_key, fingerprint, verify_current_sources
from .storage import new_directory, review_lock
from .validation import review_report, seal, verify_package, verify_state
from .workbench import capture_workbench, rebound_workbench


def selection_path(root: Path, digest: str) -> Path:
    _digest(digest)
    return root / "preparation" / "selections" / digest / "selection.json"


def make_selection(package, state, index, request: SelectionRequest) -> SelectionProposal:
    if index.state_sha256 != state.state_sha256:
        raise ValueError("candidate index is stale; rebuild against the current review state")
    entries = {entry.example_id: entry for entry in index.entries}
    extra = set(request.additional_development_ids)
    if len(extra) > index.additional_development_budget:
        raise ValueError("additional Development selection exceeds the frozen review budget")
    if any(i not in entries or entries[i].membership != "candidate" for i in extra):
        raise ValueError("additional Development must be eligible, unselected non-holdout sources")
    sources = {source.example_id: source for source in package.population}
    existing_keys = {duplicate_key(sources[i]) for i in package.known_development_ids}
    extra_keys = [duplicate_key(sources[i]) for i in sorted(extra)]
    if len(set(extra_keys)) != len(extra_keys) or existing_keys & set(extra_keys):
        raise ValueError("additional Development duplicates existing/selected source content")
    selected = {case.example_id for case in package.cases} | extra
    for item in request.priorities:
        if (
            item.example_id not in selected
            or entries[item.example_id].source_sha256 != item.source_sha256
        ):
            raise ValueError("priority must bind one of the selected frozen source cases")
    priorities = {item.example_id: item.priority for item in request.priorities}
    order = sorted(selected, key=lambda i: (-priorities.get(i, entries[i].priority), i))
    return seal(
        SelectionProposal,
        {
            "package_sha256": package.package_sha256,
            "state_sha256": state.state_sha256,
            "index_sha256": index.index_sha256,
            "request": request.model_dump(mode="json"),
            "review_order": order,
            "holdout_ids": sorted(c.example_id for c in package.cases if c.split == "holdout"),
        },
        "selection_sha256",
    )


def submit_selection(
    root: Path, *, index_sha256: str, expected_state_sha256: str, request: SelectionRequest
) -> dict:
    with review_lock(root / ".review.lock"):
        package, state, index = load_candidate_index(root, index_sha256)
        if state.state_sha256 != expected_state_sha256:
            raise ValueError("stale review state; reload before proposing a selection")
        selection = make_selection(package, state, index, request)
        path = selection_path(root, selection.selection_sha256)
        new_directory(
            path.parent,
            {path.name: _json_bytes(selection.model_dump(mode="json"))},
            idempotent=True,
        )
    return {
        "selection_sha256": selection.selection_sha256,
        "index_sha256": index_sha256,
        "package_sha256": package.package_sha256,
        "state_sha256": state.state_sha256,
        "additional_development_count": len(request.additional_development_ids),
        "review_order": list(selection.review_order),
        "status": "proposed-not-materialized",
        "human_decisions_added": 0,
    }


def load_selection(root: Path, digest: str):
    selection = SelectionProposal.model_validate_json(safe_read(selection_path(root, digest)))
    require_supported_schema("partial-review-selection-proposal", selection.schema_version)
    if selection.selection_sha256 != digest or fingerprint(selection, "selection_sha256") != digest:
        raise ValueError("selection filename/fingerprint mismatch")
    package, state, index = load_candidate_index(root, selection.index_sha256)
    if selection != make_selection(package, state, index, selection.request):
        raise ValueError("selection differs from the bound package/index/current review state")
    return package, state, index, selection


def apply_selection(
    root: Path, *, selection_sha256: str, output: Path, review_id: str, version: str = "1.0.0"
) -> dict:
    """Local packaging operation, intentionally not an MCP tool. No manual hash work."""
    _output_is_separate(output.resolve(), (root,))
    with review_lock(root / ".review.lock"):
        package, state, index, selection = load_selection(root, selection_sha256)
        verify_current_sources(package)
        workbench = capture_workbench(root, package, state)
        additions = set(selection.request.additional_development_ids)
        known = set(package.known_development_ids) | additions
        holdout = set(selection.holdout_ids)
        # Freeze all old Holdout members as existing; no reseeding or replacement is possible.
        priorities = {p.example_id: p for p in selection.request.priorities}
        queue = {
            "selection_sha256": selection_sha256,
            "rows": [
                {
                    "example_id": i,
                    "priority": priorities[i].priority
                    if i in priorities
                    else next(e.priority for e in index.entries if e.example_id == i),
                    "rationale": priorities[i].rationale
                    if i in priorities
                    else "; ".join(next(e.reasons for e in index.entries if e.example_id == i)),
                }
                for i in selection.review_order
            ],
        }
        lineage = {
            "kind": "partial-review-preparation-lineage",
            "parent_package_sha256": package.package_sha256,
            "parent_state_sha256": state.state_sha256,
            "selection_sha256": selection_sha256,
            "index_sha256": index.index_sha256,
            "human_decisions_added": 0,
        }
        files = {
            "preparation-lineage.json": _json_bytes(lineage),
            "preparation-selection.json": _json_bytes(selection.model_dump(mode="json")),
            "preparation-index.json": safe_read(index_path(root, index.index_sha256)),
            "preparation-parent-state.json": _json_bytes(state.model_dump(mode="json")),
            "preparation-parent-package.json": _json_bytes(package.model_dump(mode="json")),
            "review-queue.json": _json_bytes(queue),
        }
        if workbench.journal_present:
            files["preparation-parent-workbench.json"] = _json_bytes(
                workbench.model_dump(mode="json")
            )
        data = package.model_dump(mode="json")
        old = {case.example_id: case for case in package.cases}
        data.update(
            id=review_id,
            version=version,
            known_development_ids=sorted(known),
            excluded_holdout_ids=sorted(set(package.excluded_holdout_ids) | additions),
            existing_holdout_ids=sorted(holdout),
            cases=[
                old[i].model_dump(mode="json")
                if i in old
                else {
                    "example_id": i,
                    "split": "development",
                    "attributes": package.profile.attributes,
                    "selection_reasons": ["agent-proposed-development", selection_sha256],
                }
                for i in selection.review_order
            ],
            input_files={
                **package.input_files,
                **{
                    str((output / name).resolve()): hashlib.sha256(raw).hexdigest()
                    for name, raw in files.items()
                },
            },
        )
        derived = seal(ReviewPackage, data, "package_sha256")
        rebound = seal(
            ReviewState,
            {
                **state.model_dump(mode="json"),
                "package_sha256": derived.package_sha256,
            },
            "state_sha256",
        )
        verify_package(derived)
        verify_state(derived, rebound)
        files.update(
            {
                "review-package.json": _json_bytes(derived.model_dump(mode="json")),
                "review-state.json": _json_bytes(rebound.model_dump(mode="json")),
                "README.md": (
                    b"# Selected review package\n\n"
                    b"Development was extended; original Holdout and review events are preserved.\n"
                    b"review-queue.json is a bound presentation order, not a source of labels.\n"
                    b"Use MCP only for suggestions; use the human adapter for decisions.\n"
                ),
            }
        )
        files.update(rebound_workbench(workbench, derived, rebound))
        new_directory(output, files, idempotent=True)
    return {
        **review_report(derived, rebound),
        "output": str(output),
        "selection_sha256": selection_sha256,
        "human_decisions_added": 0,
    }


def review_queue(root: Path, package) -> tuple[str, ...]:
    path = root / "review-queue.json"
    expected = package.input_files.get(str(path.resolve()))
    if expected is None:
        return tuple(case.example_id for case in package.cases)
    import json

    raw = safe_read(path)
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError("review queue fingerprint mismatch")
    order = tuple(row["example_id"] for row in json.loads(raw)["rows"])
    if len(order) != len(package.cases) or set(order) != {c.example_id for c in package.cases}:
        raise ValueError("review queue must retain every selected case exactly once")
    return order
