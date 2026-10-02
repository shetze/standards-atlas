"""Resolve evidence IDs retained by formal projections back to canonical sources."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from standards_atlas.application.context import (
    SourceAccessPolicy,
    SourceSurfaceAvailability,
    SourceSurfaceRef,
    SourceSurfaceResolution,
    SourceSurfaceResolver,
)
from standards_atlas.domain.model import (
    ArtifactReference,
    EngineeringDocument,
    EvidenceAnchor,
    FormalAssertion,
    FormalSemanticProjection,
)


class FormalEvidenceResolutionStatus(StrEnum):
    """Resolution state for one evidence ID retained by a formal assertion."""

    RESOLVED = "resolved"
    NOT_AUTHORIZED = "not_authorized"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class FormalEvidenceResolution:
    """One text-safe route from a formal evidence ID to its canonical owner/source."""

    evidence_id: str
    status: FormalEvidenceResolutionStatus
    kind: str | None
    anchor: EvidenceAnchor | None = None
    artifact: ArtifactReference | None = None
    source: SourceSurfaceResolution | None = None
    reason: str = ""


class FormalProjectionEvidenceResolver:
    """Resolve existing projection evidence without adding a graph/adoption data model."""

    def __init__(
        self,
        document: EngineeringDocument,
        projection: FormalSemanticProjection,
        *,
        access_policy: SourceAccessPolicy | None = None,
    ) -> None:
        if projection.source_document_key != document.key.value:
            raise ValueError("formal projection and canonical document keys differ")
        self._document = document
        self._projection = projection
        self._surface_resolver = SourceSurfaceResolver(
            (document,), access_policy=access_policy or SourceAccessPolicy()
        )
        self._anchors = {item.id: item for item in document.knowledge.evidence_anchors}
        lineage = document.lineage
        self._artifacts = (
            {item.id: item for item in (lineage.artifact, *lineage.derived_from)}
            if lineage is not None
            else {}
        )
        self._assertions = {item.id.iri: item for item in projection.assertions}

    def resolve_assertion_evidence(
        self, assertion: FormalAssertion | str
    ) -> tuple[FormalEvidenceResolution, ...]:
        """Resolve every evidence ID on one exact projected assertion."""

        item = (
            assertion if isinstance(assertion, FormalAssertion) else self._assertions.get(assertion)
        )
        if item is None:
            raise KeyError(f"formal assertion is not present in projection: {assertion!r}")
        return tuple(self.resolve_evidence_id(evidence_id) for evidence_id in item.evidence_ids)

    def resolve_evidence_id(self, evidence_id: str) -> FormalEvidenceResolution:
        anchor = self._anchors.get(evidence_id)
        if anchor is not None:
            source = self._surface_resolver.resolve(
                SourceSurfaceRef(
                    document_key=self._document.key.value,
                    clause_id=anchor.source_clause_id.value,
                    source_kind=anchor.source_kind,
                ),
                start_offset=anchor.start_offset,
                end_offset=anchor.end_offset,
            )
            if source.availability is SourceSurfaceAvailability.NOT_AUTHORIZED:
                return FormalEvidenceResolution(
                    evidence_id=evidence_id,
                    status=FormalEvidenceResolutionStatus.NOT_AUTHORIZED,
                    kind="knowledge_anchor",
                    anchor=anchor,
                    source=source,
                    reason="canonical evidence source is outside the configured text access policy",
                )
            if source.availability is not SourceSurfaceAvailability.AVAILABLE:
                return FormalEvidenceResolution(
                    evidence_id=evidence_id,
                    status=FormalEvidenceResolutionStatus.UNAVAILABLE,
                    kind="knowledge_anchor",
                    anchor=anchor,
                    source=source,
                    reason="canonical evidence source is not currently resolvable",
                )
            expected_hash = f"sha256:{anchor.content_hash}"
            if source.content_sha256 != expected_hash:
                return FormalEvidenceResolution(
                    evidence_id=evidence_id,
                    status=FormalEvidenceResolutionStatus.UNAVAILABLE,
                    kind="knowledge_anchor",
                    anchor=anchor,
                    source=source,
                    reason="canonical evidence source no longer matches the persisted anchor hash",
                )
            return FormalEvidenceResolution(
                evidence_id=evidence_id,
                status=FormalEvidenceResolutionStatus.RESOLVED,
                kind="knowledge_anchor",
                anchor=anchor,
                source=source,
                reason="formal evidence ID resolves to its canonical knowledge evidence anchor",
            )

        artifact = self._artifacts.get(evidence_id)
        if artifact is not None:
            return FormalEvidenceResolution(
                evidence_id=evidence_id,
                status=FormalEvidenceResolutionStatus.RESOLVED,
                kind="artifact_lineage",
                artifact=artifact,
                reason="formal evidence ID resolves to canonical document artifact lineage",
            )

        return FormalEvidenceResolution(
            evidence_id=evidence_id,
            status=FormalEvidenceResolutionStatus.UNKNOWN,
            kind=None,
            reason="formal evidence ID is not present in canonical knowledge or artifact lineage",
        )
