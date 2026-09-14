"""Read bounded, source-bound historical reports without executing inference.

A checksum binds the report bytes, not the correctness of its conclusions. Historical
acceptance is not fresh HITL confirmation. Aggregate-only evaluation JSON is insufficient.
"""

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
from standards_atlas.application.semantic_qualification.mixed_evidence import MixedConsensusReport
from standards_atlas.application.semantic_qualification.partial_observations import (
    PartialObservation,
)
from standards_atlas.application.semantic_qualification.qualification_campaign_model import (
    SemanticReferenceSuite,
)

from .model import SemanticPredicate, predicate_data, validate_predicate
from .preparation_model import HistoricalSignal, HistoryArtifact

MAX_ARTIFACT_BYTES = 64 * 1024 * 1024
REPORT_NAMES = {
    "mixed-consensus-report.json",
    "mixed-stage-report.json",
    "mixed-before-focus-report.json",
    "consensus-report.json",
    "partial-observation.json",
}


class HistoryReader:
    def __init__(self, package):
        self.package = package
        self.by_coordinate = {(s.document_key, s.clause_id): s for s in package.population}
        self.by_id = {s.example_id: s for s in package.population}
        self.signals = defaultdict(list)
        self.artifacts = []
        self.diagnostics = []
        self.seen = set()

    def _bind(self, *, document_key, clause_id, content_hash=None, text=None, example_id=None):
        source = self.by_coordinate.get((document_key, clause_id))
        if source is None:
            self.diagnostics.append(f"outside-population:{document_key}:{clause_id}")
            return None
        if (
            (example_id is not None and example_id != source.example_id)
            or (content_hash is None and text is None)
            or (content_hash is not None and content_hash != source.content_hash)
            or (text is not None and text.rstrip("\r\n") != source.text.rstrip("\r\n"))
        ):
            self.diagnostics.append(f"unbound-or-changed-source:{source.example_id}")
            return None
        return source

    def _add(
        self,
        source,
        digest,
        kind,
        attribute,
        status,
        *,
        value=None,
        has_value=False,
        model_values=None,
        stage=None,
        reference_id=None,
    ):
        # Profile-independent known task attributes can inform selection, but not add tasks.
        if attribute not in self.package.output_schema.get("properties", {}):
            return
        predicate = SemanticPredicate(equals=value) if has_value else None
        try:
            if predicate is not None:
                validate_predicate(attribute, predicate, self.package.output_schema)
            for observed in (model_values or {}).values():
                validate_predicate(
                    attribute, SemanticPredicate(equals=observed), self.package.output_schema
                )
        except ValueError:
            self.diagnostics.append(
                f"incompatible-historical-value:{source.example_id}:{attribute}"
            )
            return
        self.signals[source.example_id].append(
            HistoricalSignal(
                artifact_sha256=digest,
                artifact_kind=kind,
                attribute=attribute,
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
        data = yaml.safe_load(raw) if location.suffix in {".yaml", ".yml"} else json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("historical input must be a report mapping")
        try:
            kind = data.get("kind")
            if kind == "partial-semantic-reference":
                self._suite(data, digest)
                detected = "semantic-suite"
            elif kind == "mixed-consensus-report":
                self._mixed(data, digest)
                detected = "mixed"
            elif "matrix_id" in data and "clauses" in data:
                self._consensus(data, digest)
                detected = "consensus"
            elif "plan" in data and "states" in data and "outcome" in data:
                self._observation(data, digest)
                detected = "observation"
            elif data.get("schema_version") == "3.0" and "cases" in data:
                self._golden(data, digest)
                detected = "golden"
            else:
                raise ValueError(
                    "unsupported history: need Golden 3.0, semantic suite, mixed/consensus report "
                    "or partial observation; aggregate evaluation JSON has no bound clause evidence"
                )
        except ValueError as exc:
            identity = f"{location}!{member}" if member else str(location)
            raise ValueError(f"invalid review history {identity}: {exc}") from exc
        self.artifacts.append(
            HistoryArtifact(
                location=str(location.resolve()),
                member=member,
                sha256=digest,
                kind=detected,
            )
        )
        self.seen.add(digest)

    def _golden(self, data, digest):
        corpus = ApplicabilityGoldenCorpus.model_validate(data)
        for case in corpus.cases:
            known = self.by_coordinate.get((case.document_key, case.clause_id))
            if known is not None:
                self._reference_holdout_guard(known)
            source = self._bind(
                document_key=case.document_key, clause_id=case.clause_id, text=case.text
            )
            if source is None:
                continue
            # Even previously inspected draft/rejected references are not independent holdout.
            self._reference_holdout_guard(source)
            if case.status != "rejected":
                self._add(
                    source,
                    digest,
                    "golden",
                    "applicability_present",
                    case.status,
                    value=case.expected.present if case.expected else None,
                    has_value=case.expected is not None,
                    reference_id=f"{corpus.corpus_id}@{corpus.corpus_version}",
                )

    def _reference_holdout_guard(self, source):
        from .sources import duplicate_key

        holdout = {c.example_id for c in self.package.cases if c.split == "holdout"}
        blocked = {duplicate_key(s) for s in self.package.population if s.example_id in holdout}
        if duplicate_key(source) in blocked:
            raise ValueError(
                "new historical reference overlaps frozen holdout; rebuild the package with "
                "all known exclusions instead of silently replacing holdout membership"
            )

    def _suite(self, data, digest):
        suite = SemanticReferenceSuite.model_validate(data)
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
            # Already declared holdout references may be indexed but are never exposed as hints.
            holdout = {c.example_id for c in self.package.cases if c.split == "holdout"}
            if suite.split != "holdout" or source.example_id not in holdout:
                self._reference_holdout_guard(source)
            for attribute, original in case.attributes.items():
                predicate = SemanticPredicate.model_validate(predicate_data(original))
                validate_predicate(attribute, predicate, self.package.output_schema)
                self.signals[source.example_id].append(
                    HistoricalSignal(
                        artifact_sha256=digest,
                        artifact_kind="semantic-suite",
                        attribute=attribute,
                        status="published" if suite.status == "published" else "proposed",
                        predicate=predicate,
                        reference_id=f"{suite.id}@{suite.version}",
                    )
                )

    def _mixed(self, data, digest):
        report = MixedConsensusReport.model_validate(data)
        for case in report.clauses:
            source = self._bind(
                document_key=case.document_key,
                clause_id=case.clause_id,
                content_hash=case.content_hash,
                example_id=case.example_id,
            )
            if source is None:
                continue
            for item in case.decisions:
                self._add(
                    source,
                    digest,
                    "mixed",
                    item.attribute,
                    item.status,
                    value=item.value,
                    has_value=item.status == "accepted",
                    model_values=item.model_values,
                    stage=item.stage or report.stage_id,
                )

    def _consensus(self, data, digest):
        # Validate the current report contract, but inspect raw keys to avoid default-valued votes.
        report = ConsensusReport.model_validate(data)
        coordinates = [(c.document_key, c.clause_id) for c in report.clauses]
        if report.clause_count != len(coordinates) or len(set(coordinates)) != len(coordinates):
            raise ValueError("consensus count or clause identities are inconsistent")
        fields = {
            "primary_function": "statement_function_category",
            "primary_knowledge_kind": "knowledge_primary_category",
            "applicability_present": "applicability_category",
            "role_semantics_present": "role_semantics_category",
            "primary_process_function": "process_primary_category",
        }
        for case in data["clauses"]:
            source = self._bind(
                document_key=case["document_key"],
                clause_id=case["clause_id"],
                text=case.get("clause_text"),
            )
            if source is None:
                continue
            votes = case.get("votes", [])
            if len({vote["model_id"] for vote in votes}) != len(votes):
                raise ValueError("consensus has duplicate model votes")
            for attribute, category_field in fields.items():
                if attribute not in case or category_field not in case:
                    continue
                if attribute == "primary_process_function" and not case.get(
                    "process_primary_evaluated", False
                ):
                    continue
                category = case[category_field]
                values = self._explicit_vote_values(votes, attribute)
                status = self._observation_status(category, values)
                self._add(
                    source,
                    digest,
                    "consensus",
                    attribute,
                    status,
                    value=case[attribute],
                    has_value=status == "observed",
                    model_values=values,
                )
            if case.get("process_set_evaluated") and "proposed_process_functions" in case:
                values = self._explicit_vote_values(votes, "process_functions")
                status = self._observation_status(case.get("process_set_category"), values)
                self._add(
                    source,
                    digest,
                    "consensus",
                    "process_functions",
                    status,
                    value=case["proposed_process_functions"],
                    has_value=status == "observed",
                    model_values=values,
                )

    @staticmethod
    def _explicit_vote_values(votes, attribute):
        values = {}
        for vote in votes:
            if attribute not in vote:
                continue  # A model default is not an explicit observation.
            if attribute == "applicability_present" and not vote.get(
                "applicability_presence_eligible", True
            ):
                continue
            if attribute == "primary_process_function" and not vote.get(
                "process_primary_evaluated", False
            ):
                continue
            if attribute == "process_functions" and vote[attribute] is None:
                continue
            values[vote["model_id"]] = vote[attribute]
        return values

    @staticmethod
    def _observation_status(category, values):
        if category in {None, "insufficient_evidence"} and not values:
            return "not_evaluated"
        if category in {None, "disputed", "insufficient_evidence"}:
            return "unresolved"
        return "observed"

    def _observation(self, data, digest):
        observation = PartialObservation.model_validate(data)
        clause = observation.plan.clause
        source = self._bind(
            document_key=clause.document_key,
            clause_id=clause.clause_id,
            content_hash=clause.content_hash,
        )
        if source is None:
            return
        for item in observation.states:
            if item.status == "not_requested":
                continue
            evaluated = item.status == "evaluated"
            value = observation.values.get(item.attribute)
            self._add(
                source,
                digest,
                "observation",
                item.attribute,
                "observed" if evaluated else "failed",
                value=value,
                has_value=evaluated,
                model_values={f"{observation.provider}:{observation.model}": value}
                if evaluated
                else {},
            )

    def read(self, path: Path):
        if path.is_file() and path.suffix.lower() != ".zip":
            if path.stat().st_size > MAX_ARTIFACT_BYTES:
                raise ValueError("historical report exceeds review preparation size limit")
            self.consume(path.read_bytes(), location=path)
            return
        source = CascadeReplaySource(path)
        try:
            members = sorted(n for n in source.names if Path(n).name in REPORT_NAMES)
            if not members:
                raise ValueError(
                    "history archive/directory contains no supported per-clause report"
                )
            if any(Path(n).name.endswith(".lock") for n in source.names):
                raise ValueError("historical run has an active writer; use a completed snapshot")
            for member in members:
                size = (
                    source.archive.getinfo(member).file_size
                    if source.archive
                    else (path / member).stat().st_size
                )
                if size > MAX_ARTIFACT_BYTES:
                    raise ValueError("historical report exceeds review preparation size limit")
                self.consume(source.read(member), location=path, member=member)
        finally:
            source.close()
