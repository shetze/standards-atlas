"""Replayable source-bound Workbench evidence, independent of HTTP or reviewer identity.

An absent journal is reported as not recorded, never as proof of an unexposed Holdout.
All functions taking a live root are called under the package's review lock by writers.
"""

from __future__ import annotations

import re
from pathlib import Path

from standards_atlas.application.schema import require_supported_schema
from standards_atlas.application.semantic_qualification.partial_proposals import _json_bytes

from .model import WorkbenchEvidence, WorkbenchState
from .sources import fingerprint
from .validation import seal


def verify_workbench_state(journal: WorkbenchState, package, review_state) -> None:
    require_supported_schema("review-workbench-state", journal.schema_version)
    if (
        journal.package_sha256 != package.package_sha256
        or fingerprint(journal, "workbench_sha256") != journal.workbench_sha256
    ):
        raise ValueError("workbench journal/package fingerprint mismatch")
    sources = {s.example_id: s for s in package.population}
    cases = {c.example_id: c for c in package.cases}
    proposals = {p.proposal_sha256: p for p in review_state.proposals}
    if any(not name.strip() or case not in cases for name, case in journal.bookmarks.items()):
        raise ValueError("invalid workbench bookmark")
    for exposure in journal.exposures:
        case = cases.get(exposure.example_id)
        if (
            case is None
            or case.split != "holdout"
            or exposure.source_sha256 != sources[exposure.example_id].source_sha256
            or exposure.rules_sha256 != package.rules_sha256
            or exposure.review_revision > review_state.revision
            or len(set(exposure.proposal_sha256s)) != len(exposure.proposal_sha256s)
        ):
            raise ValueError("invalid Holdout exposure source/revision binding")
        for digest in exposure.proposal_sha256s:
            proposal = proposals.get(digest)
            if (
                proposal is None
                or proposal.example_id != exposure.example_id
                or proposal.producer_kind != "model"
                or proposal.revision > exposure.review_revision
            ):
                raise ValueError("invalid Holdout exposure proposal binding")


def verify_workbench_evidence(evidence: WorkbenchEvidence, package, review_state) -> None:
    require_supported_schema("partial-review-workbench-evidence", evidence.schema_version)
    if fingerprint(evidence, "audit_sha256") != evidence.audit_sha256:
        raise ValueError("Workbench evidence fingerprint mismatch")
    snapshots = (*evidence.history, evidence.state)
    if [s.revision for s in snapshots] != list(range(evidence.state.revision + 1)):
        raise ValueError("Workbench history must be complete and contiguous")
    for snapshot in snapshots:
        verify_workbench_state(snapshot, package, review_state)
    first = snapshots[0]
    if first.bookmarks or first.exposures:
        raise ValueError("initial Workbench state cannot contain unrecorded events")
    for previous, current in zip(snapshots, snapshots[1:], strict=False):
        if (
            current.exposures[: len(previous.exposures)] != previous.exposures
            or not previous.bookmarks.keys() <= current.bookmarks.keys()
        ):
            raise ValueError("Workbench history cannot discard prior exposure or reviewers")
        if len(current.exposures) > len(previous.exposures) + 1:
            raise ValueError("Workbench revision contains more than one reveal")
    if not evidence.journal_present and (evidence.history or evidence.state.revision):
        raise ValueError("absent Workbench journal cannot have recorded history")


def workbench_from_files(files: dict[str, bytes], package, state) -> WorkbenchEvidence:
    """Read the same closed journal inventory from a live snapshot or a verified archive."""
    names = {name for name in files if name.startswith("workbench/")}
    present = "workbench/state.json" in names
    if names and not present:
        raise ValueError("Workbench history exists without its current journal")
    history = []
    for name in sorted(names - {"workbench/state.json"}):
        match = re.fullmatch(r"workbench/history/([0-9a-f]{64})\.json", name)
        if match is None:
            raise ValueError(f"unexpected Workbench evidence file: {name}")
        item = WorkbenchState.model_validate_json(files[name])
        if item.workbench_sha256 != match[1]:
            raise ValueError("Workbench history filename differs from its fingerprint")
        history.append(item)
    current = (
        WorkbenchState.model_validate_json(files["workbench/state.json"])
        if present
        else seal(WorkbenchState, {"package_sha256": package.package_sha256}, "workbench_sha256")
    )
    evidence = seal(
        WorkbenchEvidence,
        {
            "journal_present": present,
            "state": current.model_dump(mode="json"),
            "history": [
                s.model_dump(mode="json") for s in sorted(history, key=lambda s: s.revision)
            ],
        },
        "audit_sha256",
    )
    verify_workbench_evidence(evidence, package, state)
    return evidence


def capture_workbench(root: Path, package, state) -> WorkbenchEvidence:
    from .candidates import safe_read

    folder = root / "workbench"
    if folder.is_symlink():
        raise ValueError("unsafe workbench journal symlink")
    files = {}
    for path in sorted(folder.rglob("*")):
        if path.is_symlink() or (not path.is_dir() and not path.is_file()):
            raise ValueError("unsafe Workbench evidence member")
        if path.is_file():
            files[path.relative_to(root).as_posix()] = safe_read(path)
    return workbench_from_files(files, package, state)


def rebound_workbench(evidence: WorkbenchEvidence, package, state) -> dict[str, bytes]:
    """Preserve every prior reveal and navigation revision when a selection is materialized."""
    files = {}
    if not evidence.journal_present:
        return files
    for previous in (*evidence.history, evidence.state):
        current = seal(
            WorkbenchState,
            {**previous.model_dump(mode="json"), "package_sha256": package.package_sha256},
            "workbench_sha256",
        )
        name = (
            "workbench/state.json"
            if previous is evidence.state
            else f"workbench/history/{current.workbench_sha256}.json"
        )
        files[name] = _json_bytes(current.model_dump(mode="json"))
    workbench_from_files(files, package, state)
    return files


def workbench_summary(evidence: WorkbenchEvidence | None) -> dict:
    if evidence is None:
        return {"status": "legacy-not-captured", "independence_proven": False}
    return {
        "status": "recorded" if evidence.journal_present else "not-recorded",
        "audit_sha256": evidence.audit_sha256,
        "revision": evidence.state.revision,
        "reveal_count": len(evidence.state.exposures),
        "revealed_holdout_cases": sorted({e.example_id for e in evidence.state.exposures}),
        "independence_proven": False,
    }
