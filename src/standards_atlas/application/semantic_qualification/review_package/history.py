"""Read bounded applicability-presence history without executing inference."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path

import yaml

from standards_atlas.application.semantic_qualification.applicability_corpus import (
    ApplicabilityGoldenCorpus,
)
from standards_atlas.application.semantic_qualification.cascade_replay_source import (
    CascadeReplaySource,
)
from standards_atlas.application.semantic_qualification.consensus import ConsensusReport

from .model import ReviewPredicate, ReviewReferenceSuite, validate_predicate
from .preparation_model import HistoricalSignal, HistoryArtifact

MAX_ARTIFACT_BYTES = 64 * 1024 * 1024
REPORT_NAMES = {"consensus-report.json"}


class HistoryReader:
    def __init__(self, package):
        self.package = package
        self.by_coordinate = {(s.document_key, s.clause_id): s for s in package.population}
        self.by_id = {s.example_id: s for s in package.population}
        self.signals = defaultdict(list)
        self.artifacts = []
        self.diagnostics = []
        self.seen = set()

    def _bind(self, *, document_key, clause_id, text=None, content_hash=None, example_id=None):
        source = self.by_coordinate.get((document_key, clause_id))
        if source is None:
            self.diagnostics.append(f"outside-population:{document_key}:{clause_id}")
            return None
        if example_id is not None and example_id != source.example_id:
            self.diagnostics.append(f"unbound-or-changed-source:{source.example_id}")
            return None
        if text is not None and text.rstrip("\r\n") != source.text.rstrip("\r\n"):
            self.diagnostics.append(f"unbound-or-changed-source:{source.example_id}")
            return None
        if content_hash is not None and content_hash != source.content_hash:
            self.diagnostics.append(f"unbound-or-changed-source:{source.example_id}")
            return None
        if text is None and content_hash is None:
            self.diagnostics.append(f"unbound-or-changed-source:{source.example_id}")
            return None
        return source

    def _add(
        self,
        source,
        digest,
        kind,
        status,
        *,
        value=None,
        has_value=False,
        model_values=None,
        stage=None,
        reference_id=None,
    ):
        predicate = ReviewPredicate(equals=value) if has_value else None
        if predicate is not None:
            validate_predicate("applicability_present", predicate, self.package.output_schema)
        for observed in (model_values or {}).values():
            validate_predicate(
                "applicability_present",
                ReviewPredicate(equals=observed),
                self.package.output_schema,
            )
        self.signals[source.example_id].append(
            HistoricalSignal(
                artifact_sha256=digest,
                artifact_kind=kind,
                status=status,
                predicate=predicate,
                model_values=model_values or {},
                stage=stage,
                reference_id=reference_id,
            )
        )

    def consume(self, raw: bytes, *, location: Path, member: str | None = None):
        if len(raw) > MAX_ARTIFACT_BYTES:
            raise ValueError("historical report exceeds review preparation size limit")
        digest = hashlib.sha256(raw).hexdigest()
        if digest in self.seen:
            return
        data = (
            yaml.safe_load(raw) if location.suffix.lower() in {".yaml", ".yml"} else json.loads(raw)
        )
        if not isinstance(data, dict):
            raise ValueError("historical input must be a report mapping")
        kind = data.get("kind")
        if kind == "review-reference-suite":
            self._suite(data, digest)
            detected = "review-suite"
        elif "matrix_id" in data and "clauses" in data:
            self._consensus(data, digest)
            detected = "consensus"
        elif data.get("schema_version") == "3.0" and "cases" in data:
            self._golden(data, digest)
            detected = "golden"
        else:
            raise ValueError(
                "unsupported history: need applicability Golden 3.0, "
                "review reference suite, or current consensus report"
            )
        self.artifacts.append(
            HistoryArtifact(
                location=str(location.resolve()), member=member, sha256=digest, kind=detected
            )
        )
        self.seen.add(digest)

    def _reference_holdout_guard(self, source):
        from .sources import duplicate_key

        holdout = {c.example_id for c in self.package.cases if c.split == "holdout"}
        blocked = {duplicate_key(s) for s in self.package.population if s.example_id in holdout}
        if duplicate_key(source) in blocked:
            raise ValueError("historical reference overlaps frozen holdout; rebuild the package")

    def _golden(self, data, digest):
        corpus = ApplicabilityGoldenCorpus.model_validate(data)
        for case in corpus.cases:
            source = self._bind(
                document_key=case.document_key, clause_id=case.clause_id, text=case.text
            )
            if source is None:
                continue
            self._reference_holdout_guard(source)
            if case.status != "rejected":
                self._add(
                    source,
                    digest,
                    "golden",
                    case.status,
                    value=case.expected.present if case.expected else None,
                    has_value=case.expected is not None,
                    reference_id=f"{corpus.corpus_id}@{corpus.corpus_version}",
                )

    def _suite(self, data, digest):
        suite = ReviewReferenceSuite.model_validate(data)
        for case in suite.cases:
            item = self.by_id.get(case.example_id)
            source = self._bind(
                document_key=case.document_key,
                clause_id=item.clause_id if item else "",
                content_hash=case.content_hash,
                example_id=case.example_id,
            )
            if source is None:
                continue
            if suite.split != "holdout":
                self._reference_holdout_guard(source)
            predicate = case.attributes["applicability_present"]
            self.signals[source.example_id].append(
                HistoricalSignal(
                    artifact_sha256=digest,
                    artifact_kind="review-suite",
                    status="published" if suite.status == "published" else "proposed",
                    predicate=predicate,
                    reference_id=f"{suite.id}@{suite.version}",
                )
            )

    def _consensus(self, data, digest):
        report = ConsensusReport.model_validate(data)
        if report.clause_count != len(report.clauses):
            raise ValueError("consensus clause count is inconsistent")
        for case in report.clauses:
            source = self._bind(
                document_key=case.document_key, clause_id=case.clause_id, text=case.clause_text
            )
            if source is None:
                continue
            values = {
                v.model_id: v.applicability_present
                for v in case.votes
                if v.applicability_presence_eligible
            }
            status = "unresolved" if case.requires_review else "accepted"
            self._add(
                source,
                digest,
                "consensus",
                status,
                value=case.applicability_present,
                has_value=not case.requires_review,
                model_values=values,
            )

    def read(self, path: Path):
        if path.is_file() and path.suffix.lower() != ".zip":
            self.consume(path.read_bytes(), location=path)
            return
        source = CascadeReplaySource(path)
        try:
            members = sorted(n for n in source.names if Path(n).name in REPORT_NAMES)
            if not members:
                raise ValueError("history contains no current consensus report")
            for member in members:
                self.consume(source.read(member), location=path, member=member)
        finally:
            source.close()
