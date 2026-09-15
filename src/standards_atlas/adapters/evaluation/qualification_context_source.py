"""Read and verify qualification archives without mutating their artifacts."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

import yaml

from standards_atlas.application.evaluation.models import EvaluationDataset, EvaluationExample
from standards_atlas.application.model.context_adoption import (
    ClauseContextCandidate,
    ContextAdoptionBatch,
)
from standards_atlas.application.schema import require_current_schema
from standards_atlas.application.semantic_qualification.annotations import (
    EvaluationCorpusManifest,
    normalized_content_hash,
)
from standards_atlas.application.semantic_qualification.applicability_detail_enrichment import (
    ApplicabilityDetailSelection,
    build_applicability_detail_selection,
)
from standards_atlas.application.semantic_qualification.applicability_policy_runner import (
    ApplicabilityPolicyRunReport,
)
from standards_atlas.application.semantic_qualification.consensus import (
    ConsensusReport,
)
from standards_atlas.application.semantic_qualification.qualification_artifact_validation import (
    validate_qualification_artifact,
)
from standards_atlas.application.semantic_qualification.qualification_coverage import (
    QualificationCoverage,
)
from standards_atlas.application.semantic_qualification.run_selection import (
    QualificationRunSelection,
)
from standards_atlas.domain.model.applicability import ClauseApplicability
from standards_atlas.domain.model.enrichment_patch import ClauseEnrichmentPatch
from standards_atlas.domain.model.knowledge_state import (
    DecisionSupport,
    GeneratedAttribute,
    GenerationMethod,
)
from standards_atlas.shared.hashing import sha256_bytes, sha256_json

CONTEXT_ADOPTION_DIMENSIONS = ("applicability",)


class _Archive:
    """Bounded member reads; never extract untrusted paths into the filesystem."""

    def __init__(self, path: Path) -> None:
        self.path = path.resolve()
        self.zip = ZipFile(path) if path.is_file() else None
        self.cache: dict[str, bytes] = {}
        self.verified: set[str] = set()
        if self.zip:
            names = [item.filename for item in self.zip.infolist() if not item.is_dir()]
            if len(names) != len(set(names)):
                self.zip.close()
                raise ValueError("duplicate members in qualification archive")
        else:
            names = [
                item.relative_to(path).as_posix() for item in path.rglob("*") if item.is_file()
            ]
        self.names = set(names)
        try:
            self.manifest = json.loads(self.raw("archive-manifest.json"))
            entries = self.manifest.get("files", [])
            self.entries = {item["path"]: item for item in entries}
            if len(entries) != len(self.entries):
                raise ValueError("duplicate entries in archive manifest")
            self.id = self.manifest["archive_id"]
            # Stable for a ZIP and its extracted, manifest-verified form.
            self.digest = sha256_bytes(self.raw("archive-manifest.json"))
        except Exception:
            self.close()
            raise

    def close(self) -> None:
        if self.zip:
            self.zip.close()

    def raw(self, name: str) -> bytes:
        if name in self.cache:
            return self.cache[name]
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or "\\" in name:
            raise ValueError("unsafe qualification archive member")
        if name not in self.names:
            raise ValueError(f"required qualification artifact is missing: {name}")
        if self.zip:
            if self.zip.getinfo(name).file_size > 128 * 1024 * 1024:
                raise ValueError("qualification member exceeds read size limit")
            data = self.zip.read(name)
        else:
            source = (self.path / name).resolve()
            if not source.is_relative_to(self.path) or source.stat().st_size > 128 * 1024 * 1024:
                raise ValueError("unsafe or oversized qualification member")
            data = source.read_bytes()
        self.cache[name] = data
        return data

    def read(self, name: str) -> bytes:
        data = self.raw(name)
        if name in self.verified:
            return data
        entry = self.entries.get(name)
        if (
            entry is None
            or sha256_bytes(data) != entry["sha256"]
            or len(data) != entry["size_bytes"]
        ):
            raise ValueError(f"qualification artifact checksum mismatch: {name}")
        validate_qualification_artifact(name, data)
        self.verified.add(name)
        return data

    def sha256(self, name: str) -> str:
        self.read(name)
        return self.entries[name]["sha256"]

    def unique(self, filename: str) -> str:
        names = [name for name in self.names if PurePosixPath(name).name == filename]
        if len(names) != 1:
            raise ValueError(f"expected exactly one {filename}; found {len(names)}")
        return names[0]


def load_qualification_context(
    run: Path, *, dimensions: tuple[str, ...] = CONTEXT_ADOPTION_DIMENSIONS
) -> ContextAdoptionBatch:
    """Load a complete archived policy run into an explicit adoption contract.

    This reader deliberately has no fallback from policy results to a raw
    Presence gate. A ZIP or an extracted *archive* is accepted, not a mutable
    qualification work directory with an unspecified final report.
    """
    if not dimensions or set(dimensions) - set(CONTEXT_ADOPTION_DIMENSIONS):
        raise ValueError("unknown or empty adoption dimension selection")
    archive = _Archive(run)
    try:
        return _load(archive, dimensions)
    finally:
        archive.close()


def _load(archive: _Archive, dimensions: tuple[str, ...]) -> ContextAdoptionBatch:
    selection_name = archive.unique("qualification-selection.json")
    prefix = str(PurePosixPath(selection_name).parent)
    selection = QualificationRunSelection.model_validate_json(archive.read(selection_name))
    dataset_payload = json.loads(archive.read(f"{prefix}/{selection.dataset_snapshot}"))
    dataset = EvaluationDataset(
        task=dataset_payload["task"],
        version=dataset_payload["version"],
        examples=tuple(
            EvaluationExample(
                id=item["id"],
                input=item["input"],
                expected=item["expected"],
                tags=tuple(item.get("tags", ())),
            )
            for item in dataset_payload["examples"]
        ),
    )
    corpus = EvaluationCorpusManifest.model_validate(
        yaml.safe_load(archive.read(f"{prefix}/{selection.corpus_snapshot}"))
    )
    if sha256_json(asdict(dataset)) != selection.dataset_sha256:
        raise ValueError("qualification dataset fingerprint differs from selection")
    if sha256_json(corpus.model_dump(mode="json")) != selection.corpus_sha256:
        raise ValueError("qualification corpus fingerprint differs from selection")
    if (dataset.task, dataset.version) != (selection.task, selection.dataset_version):
        raise ValueError("qualification dataset identity differs from selection")
    examples_by_id = {item.id: item for item in dataset.examples}
    if len(examples_by_id) != len(dataset.examples):
        raise ValueError("duplicate example ids in qualification dataset")
    corpus_by_coordinate = {
        (item.clause.document_key, item.clause.clause_id): item.clause.content_hash
        for item in corpus.clauses
    }
    dataset_coordinates = [
        (item.input["context"]["document_key"], item.input["context"]["clause_id"])
        for item in dataset.examples
    ]
    if len(corpus_by_coordinate) != len(corpus.clauses):
        raise ValueError("duplicate clause coordinates in qualification corpus")
    if len(set(dataset_coordinates)) != len(dataset_coordinates) or set(dataset_coordinates) != set(
        corpus_by_coordinate
    ):
        raise ValueError("qualification corpus and dataset coordinates differ")
    if (len(dataset.examples), len(corpus.clauses), len(selection.clauses)) != (
        selection.dataset_clause_count,
        selection.corpus_clause_count,
        selection.selected_clause_count,
    ):
        raise ValueError("qualification selection counts differ from snapshots")
    if corpus.corpus_id != selection.corpus_id or corpus.task != selection.task:
        raise ValueError("qualification corpus identity differs from selection")
    examples = tuple(examples_by_id[item.example_id] for item in selection.clauses)
    examples_by_coordinate = {}
    for selected, example in zip(selection.clauses, examples, strict=True):
        context = example.input["context"]
        if (context.get("document_key"), context.get("clause_id")) != (
            selected.document_key,
            selected.clause_id,
        ):
            raise ValueError("qualification example coordinates differ from selection")
        content = example.input["content"]
        if normalized_content_hash(content["text"]) != content["hash"]:
            raise ValueError("qualification example content fingerprint mismatch")
        coordinate = (selected.document_key, selected.clause_id)
        if coordinate in examples_by_coordinate:
            raise ValueError("duplicate clause coordinates in qualification selection")
        if content["hash"] != corpus_by_coordinate[coordinate]:
            raise ValueError("qualification corpus content fingerprint mismatch")
        examples_by_coordinate[coordinate] = example

    consensus_name = archive.unique("final-consensus-report.json")
    consensus = ConsensusReport.model_validate_json(archive.read(consensus_name))
    coverage = QualificationCoverage.model_validate_json(
        archive.read(f"{prefix}/qualification-coverage.json")
    )
    # Reuse the existing selection contract, including coverage and canonical hashes.
    persisted_detail = ApplicabilityDetailSelection.model_validate_json(
        archive.read(archive.unique("applicability-policy-selection.json"))
    )
    detail_selection = build_applicability_detail_selection(
        run_selection=selection,
        examples=examples,
        consensus=consensus,
        coverage=coverage,
        task_version=persisted_detail.task_version,
    )
    if detail_selection.fingerprint != persisted_detail.fingerprint:
        raise ValueError("persisted policy selection differs from qualified inputs")
    policy_name = archive.unique("applicability-policy-run.json")
    policy = ApplicabilityPolicyRunReport.model_validate_json(archive.read(policy_name))
    if (policy.source_matrix_id, policy.source_corpus_id) != (
        consensus.matrix_id,
        consensus.corpus_id,
    ):
        raise ValueError("applicability policy belongs to a different matrix/corpus")
    if policy.source_consensus_sha256 != detail_selection.source_consensus_sha256:
        raise ValueError("applicability policy belongs to a different final consensus")
    if policy.source_selection_sha256 != detail_selection.fingerprint:
        raise ValueError("applicability policy belongs to a different selection")
    cases = {(case.document_key, case.clause_id): case for case in policy.cases}
    coordinates = {(case.document_key, case.clause_id) for case in consensus.clauses}
    if len(coordinates) != len(consensus.clauses):
        raise ValueError("duplicate clause coordinates in final consensus")
    if set(cases) != coordinates or len(cases) != len(policy.cases):
        raise ValueError("applicability policy coordinates differ from consensus")
    for clause in consensus.clauses:
        case = cases[(clause.document_key, clause.clause_id)]
        if case.gate_present != clause.applicability_present or case.reference != clause.reference:
            raise ValueError("applicability policy input differs from consensus clause")

    candidates = []
    for clause in consensus.clauses:
        coordinate = (clause.document_key, clause.clause_id)
        example = examples_by_coordinate[coordinate]
        case = cases[coordinate]
        attributes = []
        support = DecisionSupport(
            rule=f"{policy.policy_id}:{policy.policy_version}",
            source_artifact=f"{archive.id}/{policy_name}",
            source_sha256=archive.sha256(policy_name),
            stage=(
                "primary"
                if case.primary_present is True
                else "rescue+confirmation"
                if case.final_present is True
                else "final-policy"
            ),
            model_ids=tuple(sorted({stage.model_id for stage in policy.stages})),
        )
        known = case.final_present is not None
        attributes.append(
            GeneratedAttribute(
                path="enrichments.applicability",
                generator="canonical-context-adoption-v1",
                method=GenerationMethod.IMPORTED,
                availability="known" if known else "unknown",
                decision=support,
            )
        )
        applicability = ClauseApplicability(present=bool(case.final_present)) if known else None
        candidates.append(
            ClauseContextCandidate(
                document_key=clause.document_key,
                clause_id=clause.clause_id,
                reference=example.input["context"]["reference"],
                content_hash=example.input["content"]["hash"],
                heading=example.input["context"].get("heading"),
                patch=ClauseEnrichmentPatch(applicability=applicability),
                attributes=tuple(attributes),
                not_evaluated=(),
            )
        )
    require_current_schema("context-adoption-batch", 1)
    return ContextAdoptionBatch(
        schema_version=1,
        source_id=archive.id,
        source_sha256=archive.digest,
        selected_clause_count=selection.selected_clause_count,
        unqualified_clause_count=coverage.unqualified_clause_count,
        candidates=tuple(candidates),
    )
