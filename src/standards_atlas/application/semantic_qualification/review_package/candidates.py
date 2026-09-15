"""Deterministic candidate index over frozen sources and explicit historical inputs."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

import yaml

from standards_atlas.application.schema import require_supported_schema

from .history import HistoryReader
from .model import predicate_data
from .preparation_model import CandidateEntry, CandidateIndex
from .service import load_review
from .sources import clause_type, duplicate_key, fingerprint, verify_current_sources
from .storage import _json_bytes, new_directory
from .validation import confirmed_decisions, seal


def _value_key(value):
    import json

    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def predicate_passes(actual, predicate) -> bool:
    return actual is predicate.equals


def index_path(root: Path, digest: str) -> Path:
    _digest(digest)
    return root / "preparation" / "indexes" / digest / "index.json"


def _digest(value: str) -> None:
    if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("invalid preparation artifact fingerprint")


def safe_read(path: Path) -> bytes:
    if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
        raise ValueError("unsafe preparation artifact symlink")
    return path.read_bytes()


def _priority(source, history, profile, confirmed, stratum_size):
    values = defaultdict(set)
    reported = defaultdict(list)
    references = defaultdict(list)
    unresolved, conflicts = set(), set()
    failure_artifacts = set()
    for signal in history:
        if signal.status == "failed":
            failure_artifacts.add(signal.artifact_sha256)
            continue
        if signal.status == "not_evaluated":
            continue
        if signal.attribute not in profile.attributes:
            continue
        if signal.status == "published" and signal.predicate is not None:
            references[signal.attribute].append(signal.predicate)
            continue
        if signal.status in {"unresolved", "conflict"}:
            # No votes is missing evidence, not model disagreement. It remains visible below.
            if signal.model_values or signal.artifact_kind == "consensus":
                unresolved.add(signal.attribute)
        if signal.status == "conflict":
            conflicts.add(signal.attribute)
        for value in signal.model_values.values():
            values[signal.attribute].add(_value_key(value))
            reported[signal.attribute].append(value)
        if signal.predicate is not None and signal.status == "accepted":
            data = predicate_data(signal.predicate)
            if "equals" in data:
                values[signal.attribute].add(_value_key(data["equals"]))
                reported[signal.attribute].append(data["equals"])
    disagreements = {key for key, distinct in values.items() if len(distinct) > 1}
    reference_mismatch = {
        key
        for key, predicates in references.items()
        if any(
            not predicate_passes(value, predicate)
            for value in reported[key]
            for predicate in predicates
        )
    }
    reference_conflict = {
        key
        for key, predicates in references.items()
        if len({_value_key(predicate_data(p)) for p in predicates}) > 1
    }
    reasons, score = [], 0
    if conflicts:
        reasons.append("reported-semantic-conflict")
        score = max(score, 90)
    if reference_mismatch or reference_conflict:
        reasons.append("historical-reference-conflict")
        score = max(score, 90)
    if disagreements:
        reasons.append("reported-value-disagreement")
        score = max(score, 80)
    if unresolved:
        reasons.append("reported-semantic-unresolved")
        score = max(score, 60)
    if set(profile.attributes) - set(confirmed) - set(references):
        reasons.append("reference-coverage-gap")
        score = max(score, 25)
    if stratum_size <= 2:
        reasons.append("rare-document-structure-stratum")
        score += 10
    if source.structure.origin == "legacy-context":
        reasons.append("unattributed-structure-context")
        score += 5
    if not history:
        reasons.append("no-historical-observation")
    if not reasons:
        reasons.append("simple-control")
    return dict(
        priority=min(score, 100),
        reasons=tuple(reasons),
        historical_reference_attributes=tuple(sorted(references)),
        disagreement_attributes=tuple(sorted(disagreements | reference_mismatch)),
        unresolved_attributes=tuple(sorted(unresolved | conflicts)),
        technical_failure_count=len(failure_artifacts),
    )


def build_candidate_index(
    root: Path,
    *,
    histories: tuple[Path, ...] = (),
    references: tuple[Path, ...] = (),
    additional_development_budget: int = 20,
) -> dict:
    """No model startup, source mutation, new labels or change to holdout membership."""
    package, state = load_review(root)
    verify_current_sources(package)
    reader = HistoryReader(package)
    # Use the package's hash-bound inputs, not a possibly edited live campaign manifest.
    # This also retains additional Development suites supplied during Slice-1 preparation.
    for name in sorted(package.input_files):
        path = Path(name)
        if path.suffix.lower() not in {".json", ".yaml", ".yml"}:
            continue
        raw = path.read_bytes()
        try:
            data = json.loads(raw) if path.suffix.lower() == ".json" else yaml.safe_load(raw)
        except (ValueError, yaml.YAMLError):
            continue  # e.g. project instructions: bound source data, not a reference suite
        if isinstance(data, dict) and (
            data.get("kind") == "review-reference-suite"
            or (data.get("schema_version") == "3.0" and "cases" in data)
        ):
            reader.consume(raw, location=path)
    # Explicit input ordering + content deduplication make repeated indexing reproducible.
    for path in sorted(set((*references, *histories)), key=str):
        reader.read(path)
    decisions = confirmed_decisions(state)
    confirmed = defaultdict(set)
    for example_id, attribute in decisions:
        confirmed[example_id].add(attribute)
    members = {case.example_id: case.split for case in package.cases}
    heldout_content = {
        duplicate_key(source)
        for source in package.population
        if members.get(source.example_id) == "holdout"
    }
    strata = Counter((source.document_key, clause_type(source)) for source in package.population)
    entries = []
    for source in package.population:
        membership = members.get(source.example_id) or (
            "holdout-duplicate" if duplicate_key(source) in heldout_content else "candidate"
        )
        history = tuple(
            sorted(
                reader.signals[source.example_id],
                key=lambda h: (
                    h.artifact_sha256,
                    h.attribute,
                    h.status,
                    _json_bytes(h.model_dump(mode="json")),
                ),
            )
        )
        # Holdout and equivalents have a source-only ranking, never a candidate-results ranking.
        hidden = membership in {"holdout", "holdout-duplicate"}
        priority = _priority(
            source,
            () if hidden else history,
            package.profile,
            () if hidden else confirmed[source.example_id],
            strata[source.document_key, clause_type(source)],
        )
        if hidden:
            priority.update(priority=0, reasons=("reserved-holdout-source-only",))
        entries.append(
            CandidateEntry(
                example_id=source.example_id,
                source_sha256=source.source_sha256,
                document_key=source.document_key,
                clause_type=clause_type(source),
                membership=membership,
                text_length=len(source.text),
                confirmed_attributes=tuple(sorted(confirmed[source.example_id])),
                history=history,
                **priority,
            )
        )
    index = seal(
        CandidateIndex,
        dict(
            package_sha256=package.package_sha256,
            state_sha256=state.state_sha256,
            population_sha256=package.population_sha256,
            rules_sha256=package.rules_sha256,
            additional_development_budget=additional_development_budget,
            entries=[e.model_dump(mode="json") for e in entries],
            artifacts=[a.model_dump(mode="json") for a in reader.artifacts],
            diagnostics=sorted(set(reader.diagnostics)),
        ),
        "index_sha256",
    )
    verify_index(package, index)
    path = index_path(root, index.index_sha256)
    new_directory(
        path.parent, {path.name: _json_bytes(index.model_dump(mode="json"))}, idempotent=True
    )
    return {
        "index_sha256": index.index_sha256,
        "package_sha256": package.package_sha256,
        "state_sha256": state.state_sha256,
        "entries": len(entries),
        "memberships": dict(Counter(e.membership for e in entries)),
        "artifacts": len(index.artifacts),
        "diagnostics": list(index.diagnostics),
        "additional_development_budget": additional_development_budget,
        "path": str(path),
    }


def verify_index(package, index):
    require_supported_schema("review-candidates", index.schema_version)
    if (
        fingerprint(index, "index_sha256") != index.index_sha256
        or index.package_sha256 != package.package_sha256
        or index.population_sha256 != package.population_sha256
        or index.rules_sha256 != package.rules_sha256
    ):
        raise ValueError("candidate index fingerprint/package mismatch")
    sources = {source.example_id: source for source in package.population}
    if len(index.entries) != len(sources) or {e.example_id for e in index.entries} != set(sources):
        raise ValueError("candidate index must cover the entire frozen population exactly once")
    members = {c.example_id: c.split for c in package.cases}
    heldout = {duplicate_key(sources[i]) for i, split in members.items() if split == "holdout"}
    for entry in index.entries:
        source = sources[entry.example_id]
        membership = members.get(entry.example_id) or (
            "holdout-duplicate" if duplicate_key(source) in heldout else "candidate"
        )
        if (
            entry.source_sha256 != source.source_sha256
            or entry.membership != membership
            or entry.document_key != source.document_key
            or entry.clause_type != clause_type(source)
            or entry.text_length != len(source.text)
        ):
            raise ValueError("candidate entry differs from its bound source/membership")


def load_candidate_index(root: Path, digest: str):
    package, state = load_review(root)
    index = CandidateIndex.model_validate_json(safe_read(index_path(root, digest)))
    verify_index(package, index)
    if index.index_sha256 != digest:
        raise ValueError("candidate index filename/fingerprint mismatch")
    return package, state, index


def candidate_page(
    root: Path,
    digest: str,
    *,
    limit: int = 20,
    offset: int = 0,
    membership: str | None = None,
    document_key: str | None = None,
    clause_type_filter: str | None = None,
    reason: str | None = None,
    query: str | None = None,
) -> dict:
    if type(limit) is not int or not 1 <= limit <= 1000 or type(offset) is not int or offset < 0:
        raise ValueError("invalid candidate page bounds")
    if membership not in {None, "development", "candidate"}:
        raise ValueError("candidate selection cannot inspect reserved holdout")
    package, state, index = load_candidate_index(root, digest)
    sources = {s.example_id: s for s in package.population}
    terms = (query or "").casefold().split()
    entries = [
        e
        for e in index.entries
        if (
            e.membership in {"development", "candidate"}
            and (membership is None or e.membership == membership)
            and (document_key is None or e.document_key == document_key)
            and (clause_type_filter is None or e.clause_type == clause_type_filter)
            and (reason is None or reason in e.reasons)
            and all(
                term
                in (sources[e.example_id].text + " " + sources[e.example_id].reference).casefold()
                for term in terms
            )
        )
    ]
    entries.sort(key=lambda e: (-e.priority, e.example_id))
    return {
        "index_sha256": digest,
        "package_sha256": package.package_sha256,
        "state_sha256": state.state_sha256,
        "index_state_sha256": index.state_sha256,
        "state_changed_since_index": state.state_sha256 != index.state_sha256,
        "additional_development_budget": index.additional_development_budget,
        "ranking_policy": index.ranking_policy,
        "total": len(entries),
        "offset": offset,
        "next_offset": offset + limit if offset + limit < len(entries) else None,
        "entries": [e.model_dump(mode="json") for e in entries[offset : offset + limit]],
    }
