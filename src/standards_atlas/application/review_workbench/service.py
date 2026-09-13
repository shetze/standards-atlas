"""Shared paginated review use cases over frozen Slice-1/2 packages.

No model invocation, suite publication, candidate re-selection or qualification
execution lives here. Browser-specific trust checks belong in the HTTP adapter.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from pydantic import TypeAdapter

from standards_atlas.application.semantic_qualification.review_package.candidates import safe_read
from standards_atlas.application.semantic_qualification.review_package.model import (
    HumanDecisionInput,
)
from standards_atlas.application.semantic_qualification.review_package.selection import review_queue
from standards_atlas.application.semantic_qualification.review_package.service import (
    load_review,
    record_decisions,
)
from standards_atlas.application.semantic_qualification.review_package.sources import clause_type
from standards_atlas.application.semantic_qualification.review_package.validation import (
    active_decisions,
    cross_attribute_errors,
    review_report,
)

from . import journal
from .model import Reviewer
from .presentation import source_presentation


class ReviewWorkbenchService:
    """A registry of immediate package children, not arbitrary client-supplied paths."""

    def __init__(self, workspace: Path, *, max_artifact_bytes: int = 64 * 1024 * 1024):
        self.workspace = Path(workspace).absolute()
        self.max_artifact_bytes = max_artifact_bytes
        self._safe_path(self.workspace)
        if not self.workspace.is_dir():
            raise ValueError("review workspace must be an existing directory")
        if max_artifact_bytes < 1:
            raise ValueError("max_artifact_bytes must be positive")

    @staticmethod
    def _safe_path(path: Path) -> None:
        if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
            raise ValueError("review workspace/package paths must not contain symlinks")

    def _root(self, handle: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", handle):
            raise ValueError("invalid review package handle; paths are not accepted")
        root = self.workspace / handle
        self._safe_path(root)
        if not root.is_dir():
            raise KeyError("review package is unavailable")
        return root

    def _load(self, handle: str):
        root = self._root(handle)
        for name in ("review-package.json", "review-state.json", "workbench/state.json"):
            path = root / name
            self._safe_path(path)
            if path.exists() and path.stat().st_size > self.max_artifact_bytes:
                raise ValueError(
                    "review artifact exceeds local size limit; source is not truncated"
                )
        package, state = load_review(root)
        return root, package, state

    def list_packages(self) -> dict:
        self._safe_path(self.workspace)
        items, unavailable = [], []
        for root in sorted(self.workspace.iterdir()):
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", root.name):
                continue
            if not (root / "review-package.json").exists():
                continue
            try:
                _, package, state = self._load(root.name)
                items.append(
                    {
                        "handle": root.name,
                        "id": package.id,
                        "package_sha256": package.package_sha256,
                        "version": package.version,
                        "cases": len(package.cases),
                        "revision": state.revision,
                    }
                )
            except (OSError, KeyError, ValueError):
                unavailable.append({"handle": root.name, "error": "Package unavailable or invalid"})
        return {"items": items, "unavailable": unavailable}

    def get_package(self, handle: str, *, reviewer: str) -> dict:
        reviewer = TypeAdapter(Reviewer).validate_python(reviewer)
        root, package, state = self._load(handle)
        audit = journal.load_journal(root, package, state)
        return {
            "handle": handle,
            "id": package.id,
            "version": package.version,
            "package_sha256": package.package_sha256,
            "state_sha256": state.state_sha256,
            "revision": state.revision,
            "profile": package.profile.model_dump(mode="json"),
            "rules": package.rules,
            "rules_sha256": package.rules_sha256,
            "output_schema": package.output_schema,
            "report": review_report(package, state),
            "resume_example_id": audit.bookmarks.get(reviewer),
            "queue_order": list(review_queue(root, package)),
            "capabilities": {
                "human_decisions": True,
                "suite_publication": False,
                "model_invocation": False,
                "selection_changes": False,
            },
        }

    @staticmethod
    def _case_status(case, active):
        accepted, deferred = {}, False
        for attribute in case.attributes:
            decision = active.get((case.example_id, attribute))
            if decision and decision.status in {"confirmed", "corrected"}:
                accepted[attribute] = decision.predicate
            deferred |= bool(decision and decision.status == "deferred")
        conflicts = cross_attribute_errors(accepted)
        complete = len(accepted) == len(case.attributes)
        return {
            "complete": complete,
            "confirmed_count": len(accepted),
            "attribute_count": len(case.attributes),
            "deferred": deferred,
            "conflicts": conflicts,
        }

    def list_cases(
        self,
        handle: str,
        *,
        split: str = "all",
        status: str = "all",
        query: str = "",
        document_key: str = "",
        attribute: str = "",
        limit: int = 10,
        offset: int = 0,
        anchor: str = "",
    ) -> dict:
        if type(limit) is not int or not 1 <= limit <= 50 or type(offset) is not int or offset < 0:
            raise ValueError("review page requires limit 1..50 and a nonnegative offset")
        if split not in {"all", "development", "holdout"}:
            raise ValueError("unknown review split")
        if status not in {"all", "open", "complete", "deferred", "conflict"}:
            raise ValueError("unknown review status filter")
        if len(query) > 500:
            raise ValueError("review search is too long")
        root, package, state = self._load(handle)
        if attribute and attribute not in package.profile.attributes:
            raise ValueError("unknown review attribute filter")
        sources = {s.example_id: s for s in package.population}
        cases = {c.example_id: c for c in package.cases}
        active = active_decisions(state)
        order = review_queue(root, package)
        rows = []
        for position, example_id in enumerate(order):
            case, source = cases[example_id], sources[example_id]
            progress = self._case_status(case, active)
            if split != "all" and case.split != split:
                continue
            if document_key and source.document_key != document_key:
                continue
            haystack = f"{source.reference}\n{source.example_id}\n{source.clause_id}\n{source.text}"
            if query.casefold() not in haystack.casefold():
                continue
            current = active.get((example_id, attribute)) if attribute else None
            complete = (
                bool(current and current.status in {"confirmed", "corrected"})
                if attribute
                else progress["complete"]
            )
            if status == "open" and complete:
                continue
            if status == "complete" and not complete:
                continue
            if status == "deferred" and not (
                current and current.status == "deferred" if attribute else progress["deferred"]
            ):
                continue
            if status == "conflict" and not progress["conflicts"]:
                continue
            rows.append(
                {
                    "example_id": example_id,
                    "reference": source.reference,
                    "document_key": source.document_key,
                    "split": case.split,
                    "clause_type": clause_type(source),
                    "position": position,
                    **progress,
                }
            )
        if anchor:
            position = next((i for i, row in enumerate(rows) if row["example_id"] == anchor), None)
            if position is not None:
                offset = (position // limit) * limit
        return {
            "package_sha256": package.package_sha256,
            "revision": state.revision,
            "total": len(rows),
            "selected_total": len(order),
            "offset": offset,
            "next_offset": offset + limit if offset + limit < len(rows) else None,
            "items": rows[offset : offset + limit],
            "documents": sorted({sources[i].document_key for i in order}),
        }

    @staticmethod
    def _priority(root, package, case) -> dict:
        # Holdout ranking rationales can contain prior candidate answers: never expose them.
        if case.split == "holdout":
            return {"rationale": "Independent Holdout; candidate ranking details withheld."}
        path = root / "review-queue.json"
        expected = package.input_files.get(str(path.resolve()))
        if expected:
            raw = safe_read(path)
            if hashlib.sha256(raw).hexdigest() != expected:
                raise ValueError("review queue fingerprint mismatch")
            return next(
                row for row in json.loads(raw)["rows"] if row["example_id"] == case.example_id
            )
        return {"rationale": "; ".join(case.selection_reasons), "priority": None}

    def get_case(self, handle: str, example_id: str, *, reviewer: str) -> dict:
        reviewer = TypeAdapter(Reviewer).validate_python(reviewer)
        root, package, state = self._load(handle)
        case = next((c for c in package.cases if c.example_id == example_id), None)
        if case is None:
            raise KeyError("case is outside the selected review package")
        source = next(s for s in package.population if s.example_id == example_id)
        audit = journal.load_journal(root, package, state)
        exposures = [
            e for e in audit.exposures if e.example_id == example_id and e.reviewer == reviewer
        ]
        exposed = {digest for e in exposures for digest in e.proposal_sha256s}
        holdout = case.split == "holdout"
        all_proposals = [p for p in state.proposals if p.example_id == example_id]
        visible = [
            p
            for p in all_proposals
            if not holdout or (p.producer_kind == "model" and p.proposal_sha256 in exposed)
        ]
        active = active_decisions(state)
        current = [d for (i, _), d in active.items() if i == example_id]
        order = review_queue(root, package)
        position = order.index(example_id)
        payload = {
            "package_sha256": package.package_sha256,
            "state_sha256": state.state_sha256,
            "revision": state.revision,
            "rules_sha256": package.rules_sha256,
            "source": source.model_dump(mode="json"),
            "source_complete": True,
            "case": {
                **case.model_dump(mode="json"),
                "selection_reasons": [] if holdout else list(case.selection_reasons),
            },
            "proposals": [p.model_dump(mode="json") for p in visible],
            "human_reviews": [d.model_dump(mode="json") for d in current],
            "review_history": [
                d.model_dump(mode="json") for d in state.decisions if d.example_id == example_id
            ],
            "source_rendering": source_presentation(source, visible),
            "schemas": {a: package.output_schema["properties"][a] for a in case.attributes},
            "progress": self._case_status(case, active),
            "priority": self._priority(root, package, case),
            "position": position,
            "selected_total": len(order),
            "previous_example_id": order[position - 1] if position else None,
            "next_example_id": order[position + 1] if position + 1 < len(order) else None,
            "holdout": {
                "blind": holdout and not exposures,
                "historical_proposals_withheld": holdout,
                "unrevealed_model_count": sum(
                    p.producer_kind == "model" and p.proposal_sha256 not in exposed
                    for p in all_proposals
                )
                if holdout
                else 0,
                "assessments": [e.model_dump(mode="json") for e in exposures],
            },
        }
        # The adapter signs this exact view; values are not accepted from arbitrary clients.
        payload["view"] = {
            "handle": handle,
            "package_sha256": package.package_sha256,
            "state_sha256": state.state_sha256,
            "revision": state.revision,
            "rules_sha256": package.rules_sha256,
            "source_sha256": source.source_sha256,
            "example_id": example_id,
            "reviewer": reviewer,
            "attributes": list(case.attributes),
            "proposal_sha256s": [p.proposal_sha256 for p in visible],
        }
        return payload

    def decide(self, handle: str, *, view: dict, decisions: tuple[HumanDecisionInput, ...]) -> dict:
        if view["handle"] != handle:
            raise ValueError("displayed review belongs to another package handle")
        root, package, state = self._load(handle)
        if package.package_sha256 != view["package_sha256"]:
            raise ValueError("displayed review belongs to another package")
        if state.revision != view["revision"] or state.state_sha256 != view["state_sha256"]:
            raise ValueError("stale review revision; reload before deciding")
        for item in decisions:
            if item.example_id != view["example_id"] or item.attribute not in view["attributes"]:
                raise ValueError("decision is outside the displayed case/attributes")
            if item.proposal_sha256 and item.proposal_sha256 not in view["proposal_sha256s"]:
                raise ValueError("proposal was not visible in this review view")
        updated = record_decisions(
            root,
            expected_revision=view["revision"],
            reviewer=view["reviewer"],
            decisions=decisions,
            expected_package_sha256=view["package_sha256"],
        )
        return {
            "revision": updated.revision,
            "state_sha256": updated.state_sha256,
            "decisions_saved": len(decisions),
            "suite_publication": False,
        }

    def reveal(self, handle: str, *, view: dict, assessment: str) -> None:
        if view["handle"] != handle:
            raise ValueError("displayed review belongs to another package handle")
        journal.reveal(self._root(handle), view=view, assessment=assessment)

    def bookmark(self, handle: str, **kwargs) -> None:
        journal.bookmark(self._root(handle), **kwargs)
