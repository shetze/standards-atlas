"""Transport-neutral resolution of current EngineeringDocument source surfaces.

The resolver is intentionally separate from the AP01 ``FrozenSourceResolver``. AP01 resolves
only byte-bound review snapshots; this module resolves explicitly supplied current documents and
never performs network access or implicit edition lookup.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Iterable, Iterator
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from standards_atlas.domain.model import (
    Clause,
    ClauseType,
    ContentBlock,
    EngineeringDocument,
    EvidenceSourceKind,
    FormulaBlock,
    GenerationMethod,
    NoteBlock,
    TableBlock,
    canonical_content_hash,
)

SOURCE_SURFACE_CONTRACT = "source-surface-resolution-v1"
SOURCE_REVISION_CONTRACT = "engineering-document-source-surfaces-v1"
BODY_RENDERING_ID = "engineering-document-clause-body-v1"
HEADING_RENDERING_ID = "engineering-document-clause-heading-v1"
TABLE_RENDERING_ID = "engineering-document-table-handle-v1"
_SYNTHETIC_HEADING_GENERATORS = frozenset(
    {
        "document-selection-synthetic-display-label",
        "atlasdata-structural-display-label",
    }
)
_ATLASDATA_STRUCTURAL_DISPLAY_LABELS: dict[ClauseType, frozenset[str]] = {
    ClauseType.TOC: frozenset({"TOC", "HEADING"}),
    ClauseType.CLAUSE: frozenset({"CLAUSE", "HEADING"}),
    ClauseType.REQUIREMENT: frozenset({"REQUIREMENT"}),
    ClauseType.OBJECTIVE: frozenset({"OBJECTIVE"}),
    ClauseType.TABLE: frozenset({"TABLE"}),
    ClauseType.MISC: frozenset({"MISC"}),
    ClauseType.SCOPE: frozenset({"SCOPE"}),
    ClauseType.TERM: frozenset({"TERM"}),
}


class SourceMediaKind(StrEnum):
    """Existing non-clause-surface media handles addressable by the resolver."""

    TABLE = "table"
    FORMULA = "formula"


class SourceSurfaceAvailability(StrEnum):
    """Technical source-resolution state, independent from semantic evidence quality."""

    AVAILABLE = "available"
    MISSING = "missing"
    NOT_LOADED = "not_loaded"
    CONFLICTING = "conflicting"
    NOT_AUTHORIZED = "not_authorized"
    NON_TEXTUAL = "non_textual"


class SourceSurfaceOrigin(StrEnum):
    """Recorded origin of the canonical value, not a semantic confidence label."""

    SOURCE_EXTRACTION = "source_extraction"
    DETERMINISTIC_PROJECTION = "deterministic_projection"
    CONFIRMED_SOURCE_ASSIGNMENT = "confirmed_source_assignment"
    SYNTHETIC_DISPLAY_LABEL = "synthetic_display_label"
    UNRESOLVED = "unresolved"


class SourceAccessPolicy(BaseModel):
    """Small transport-neutral access boundary around source resolution.

    An empty document allowlist means that all explicitly bound documents may be addressed. Text
    exposure applies to body, heading and textual formula surfaces. Source locators are never
    returned by this contract.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    allowed_document_keys: tuple[str, ...] = ()
    expose_text: bool = True

    @model_validator(mode="after")
    def document_keys_are_unique(self) -> SourceAccessPolicy:
        if len(self.allowed_document_keys) != len(set(self.allowed_document_keys)):
            raise ValueError("source access document keys must be unique")
        return self

    def allows_document(self, document_key: str) -> bool:
        return not self.allowed_document_keys or document_key in self.allowed_document_keys


class SourceSurfaceRef(BaseModel):
    """Caller-facing identity of one requested canonical source surface or media handle."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    document_key: str = Field(min_length=1)
    clause_id: str = Field(min_length=1)
    source_kind: EvidenceSourceKind | None = None
    media_kind: SourceMediaKind | None = None
    block_id: str | None = None
    document_revision: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")

    @model_validator(mode="after")
    def block_identity_matches_kind(self) -> SourceSurfaceRef:
        is_text_surface = self.source_kind is not None
        is_media = self.media_kind is not None
        if is_text_surface == is_media:
            raise ValueError("source refs require exactly one text surface or media kind")
        if is_media and not self.block_id:
            raise ValueError("table/formula source refs require block_id")
        if is_text_surface and self.block_id is not None:
            raise ValueError("body/heading source refs must not define block_id")
        return self


class SourceDocumentBinding(BaseModel):
    """Exact loaded document/edition binding returned by a successful selection."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    document_key: str = Field(min_length=1)
    year: int | None = None
    version: str | None = None
    source_revision: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    artifact_revision: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")


class SourceSurfaceIdentity(BaseModel):
    """Resolved clause/surface identity independent from result ownership or context role."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    document: SourceDocumentBinding
    clause_id: str = Field(min_length=1)
    clause_reference: str = Field(min_length=1)
    source_kind: EvidenceSourceKind | None = None
    media_kind: SourceMediaKind | None = None
    block_id: str | None = None


class SourceMediaHandle(BaseModel):
    """Existing structured/visual media identity without copying protected source payload."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    block_id: str = Field(min_length=1)
    media_kind: SourceMediaKind
    document_table_id: str | None = None
    table_reference: str | None = None
    formula_representation: str | None = None
    formula_extraction_status: str | None = None
    media_content_hash: str | None = None


class SourceSurfaceResolution(BaseModel):
    """One deterministic source resolution result.

    ``text`` is the exact returned canonical surface/excerpt. ``surface_sha256`` binds the whole
    canonical textual surface, while ``content_sha256`` binds the returned excerpt. Offsets are
    zero-based, half-open Python character offsets into the named whole surface.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    contract_id: Literal["source-surface-resolution-v1"] = SOURCE_SURFACE_CONTRACT
    requested: SourceSurfaceRef
    availability: SourceSurfaceAvailability
    identity: SourceSurfaceIdentity | None = None
    origin: SourceSurfaceOrigin = SourceSurfaceOrigin.UNRESOLVED
    origin_reference: str | None = None
    source_backed: bool = False
    rendering_id: str | None = None
    surface_sha256: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    content_sha256: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    start_offset: int | None = Field(default=None, ge=0)
    end_offset: int | None = Field(default=None, ge=0)
    text: str | None = None
    media: SourceMediaHandle | None = None
    reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def unavailable_results_do_not_leak_text(self) -> SourceSurfaceResolution:
        if self.availability is SourceSurfaceAvailability.NOT_AUTHORIZED:
            if any(
                value is not None
                for value in (
                    self.text,
                    self.surface_sha256,
                    self.content_sha256,
                    self.start_offset,
                    self.end_offset,
                )
            ):
                raise ValueError("unauthorized source resolution must not expose textual metadata")
        if (self.start_offset is None) != (self.end_offset is None):
            raise ValueError("resolved source offsets must be supplied together")
        return self


class _BoundDocument(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    document: EngineeringDocument
    binding: SourceDocumentBinding


class SourceSurfaceResolver:
    """Resolve current source surfaces from an explicitly supplied document set."""

    def __init__(
        self,
        documents: Iterable[EngineeringDocument],
        *,
        access_policy: SourceAccessPolicy | None = None,
    ) -> None:
        grouped: dict[str, list[_BoundDocument]] = defaultdict(list)
        for document in documents:
            binding = source_document_binding(document)
            grouped[document.key.value].append(_BoundDocument(document=document, binding=binding))
        self._documents = {key: tuple(values) for key, values in grouped.items()}
        self._access = access_policy or SourceAccessPolicy()

    def list_surface_refs(
        self,
        *,
        document_key: str,
        clause_id: str,
        document_revision: str | None = None,
    ) -> tuple[SourceSurfaceRef, ...]:
        """List identities only for surfaces known in one explicitly bound clause.

        This does not return protected text. Missing/conflicting/unauthorized documents yield an
        empty list; callers can use :meth:`resolve` for the exact status.
        """

        if not self._access.allows_document(document_key):
            return ()
        selected, _ = self._select_document(document_key, document_revision)
        if selected is None:
            return ()
        clause = _single_clause(selected.document, clause_id)
        if clause is None:
            return ()
        refs = [
            SourceSurfaceRef(
                document_key=document_key,
                document_revision=selected.binding.source_revision,
                clause_id=clause_id,
                source_kind=EvidenceSourceKind.BODY,
            )
        ]
        if clause_has_heading_source_surface(clause):
            refs.append(
                SourceSurfaceRef(
                    document_key=document_key,
                    document_revision=selected.binding.source_revision,
                    clause_id=clause_id,
                    source_kind=EvidenceSourceKind.HEADING,
                )
            )
        for block in _iter_content_blocks(clause.content):
            if isinstance(block, TableBlock):
                media_kind = SourceMediaKind.TABLE
            elif isinstance(block, FormulaBlock):
                media_kind = SourceMediaKind.FORMULA
            else:
                continue
            refs.append(
                SourceSurfaceRef(
                    document_key=document_key,
                    document_revision=selected.binding.source_revision,
                    clause_id=clause_id,
                    media_kind=media_kind,
                    block_id=block.id,
                )
            )
        return tuple(refs)

    def resolve(
        self,
        source_ref: SourceSurfaceRef,
        *,
        start_offset: int | None = None,
        end_offset: int | None = None,
    ) -> SourceSurfaceResolution:
        """Resolve one source ref and optional exact excerpt without widening its identity."""

        _validate_requested_offsets(start_offset, end_offset)
        if not self._access.allows_document(source_ref.document_key):
            return _unavailable(
                source_ref,
                SourceSurfaceAvailability.NOT_AUTHORIZED,
                "requested document is outside the configured source access boundary",
            )

        selected, selection_status = self._select_document(
            source_ref.document_key,
            source_ref.document_revision,
        )
        if selected is None:
            return _unavailable(source_ref, selection_status[0], selection_status[1])

        clause = _single_clause(selected.document, source_ref.clause_id)
        if clause is None:
            return _unavailable(
                source_ref,
                SourceSurfaceAvailability.MISSING,
                "requested clause is not present in the bound document revision",
            )
        identity = SourceSurfaceIdentity(
            document=selected.binding,
            clause_id=clause.id.value,
            clause_reference=clause.reference.as_text(),
            source_kind=source_ref.source_kind,
            media_kind=source_ref.media_kind,
            block_id=source_ref.block_id,
        )

        if source_ref.source_kind is EvidenceSourceKind.BODY:
            if not clause.content or clause.plain_text == "":
                return _missing_surface(source_ref, identity, "clause body surface is absent")
            origin, reference = _attribute_origin(clause, "baseline.content")
            if origin is SourceSurfaceOrigin.UNRESOLVED and _content_is_source_backed(
                clause.content
            ):
                origin = SourceSurfaceOrigin.SOURCE_EXTRACTION
                reference = "content-block-source-evidence"
            return self._text_resolution(
                source_ref,
                identity,
                clause.plain_text,
                rendering_id=BODY_RENDERING_ID,
                origin=origin,
                origin_reference=reference,
                start_offset=start_offset,
                end_offset=end_offset,
            )

        if source_ref.source_kind is EvidenceSourceKind.HEADING:
            if clause.heading is None or clause.heading == "":
                return _missing_surface(source_ref, identity, "clause heading surface is absent")
            origin, reference = heading_surface_origin(clause)
            if origin is SourceSurfaceOrigin.SYNTHETIC_DISPLAY_LABEL:
                return _missing_surface(
                    source_ref,
                    identity,
                    (
                        "clause heading value is a synthetic structural/display label, "
                        "not a source surface"
                    ),
                )
            return self._text_resolution(
                source_ref,
                identity,
                clause.heading,
                rendering_id=HEADING_RENDERING_ID,
                origin=origin,
                origin_reference=reference,
                start_offset=start_offset,
                end_offset=end_offset,
            )

        block = _content_block_by_id(clause.content, source_ref.block_id or "")
        if source_ref.media_kind is SourceMediaKind.TABLE:
            if not isinstance(block, TableBlock):
                return _missing_surface(source_ref, identity, "table source handle is absent")
            table = next(
                (
                    item
                    for item in selected.document.tables
                    if item.table_block_id == block.id and item.parent_clause_id == clause.id
                ),
                None,
            )
            origin, reference = _media_origin(block, clause)
            return SourceSurfaceResolution(
                requested=source_ref,
                availability=SourceSurfaceAvailability.NON_TEXTUAL,
                identity=identity,
                origin=origin,
                origin_reference=reference,
                source_backed=_is_source_backed(origin),
                rendering_id=TABLE_RENDERING_ID,
                media=SourceMediaHandle(
                    block_id=block.id,
                    media_kind=SourceMediaKind.TABLE,
                    document_table_id=table.id.value if table is not None else None,
                    table_reference=table.reference if table is not None else None,
                ),
                reason=(
                    "structured table handle exists; Series A does not define a canonical flat "
                    "text evidence surface for table cells"
                ),
            )

        if not isinstance(block, FormulaBlock):
            return _missing_surface(source_ref, identity, "formula source handle is absent")
        origin, reference = _media_origin(block, clause)
        media = SourceMediaHandle(
            block_id=block.id,
            media_kind=SourceMediaKind.FORMULA,
            formula_representation=block.representation,
            formula_extraction_status=block.extraction_status,
            media_content_hash=block.content_hash,
        )
        if block.extraction_status == "visual_only" or not block.expression:
            return SourceSurfaceResolution(
                requested=source_ref,
                availability=SourceSurfaceAvailability.NON_TEXTUAL,
                identity=identity,
                origin=origin,
                origin_reference=reference,
                source_backed=_is_source_backed(origin),
                rendering_id=f"engineering-document-formula-{block.representation}-v1",
                media=media,
                reason="formula handle exists but no canonical textual transcription is available",
            )
        if not self._access.expose_text:
            return _unauthorized_text(
                source_ref,
                identity,
                origin,
                reference,
                media=media.model_copy(update={"media_content_hash": None}),
            )
        return _resolved_text(
            source_ref,
            identity,
            block.expression,
            rendering_id=f"engineering-document-formula-{block.representation}-v1",
            origin=origin,
            origin_reference=reference,
            start_offset=start_offset,
            end_offset=end_offset,
            media=media,
        )

    def _select_document(
        self,
        document_key: str,
        expected_revision: str | None,
    ) -> tuple[
        _BoundDocument | None,
        tuple[SourceSurfaceAvailability, str],
    ]:
        candidates = self._documents.get(document_key, ())
        if not candidates:
            return None, (
                SourceSurfaceAvailability.NOT_LOADED,
                "requested document is not present in the explicitly bound source set",
            )
        by_revision = {candidate.binding.source_revision: candidate for candidate in candidates}
        if expected_revision is not None:
            selected = by_revision.get(expected_revision)
            if selected is None:
                return None, (
                    SourceSurfaceAvailability.CONFLICTING,
                    "loaded document key does not match the requested source revision",
                )
            return selected, (SourceSurfaceAvailability.AVAILABLE, "document revision selected")
        if len(by_revision) != 1:
            return None, (
                SourceSurfaceAvailability.CONFLICTING,
                "multiple loaded source revisions require an explicit document revision",
            )
        return next(iter(by_revision.values())), (
            SourceSurfaceAvailability.AVAILABLE,
            "document revision selected",
        )

    def _text_resolution(
        self,
        source_ref: SourceSurfaceRef,
        identity: SourceSurfaceIdentity,
        text: str,
        *,
        rendering_id: str,
        origin: SourceSurfaceOrigin,
        origin_reference: str | None,
        start_offset: int | None,
        end_offset: int | None,
    ) -> SourceSurfaceResolution:
        if not self._access.expose_text:
            return _unauthorized_text(
                source_ref,
                identity,
                origin,
                origin_reference,
            )
        return _resolved_text(
            source_ref,
            identity,
            text,
            rendering_id=rendering_id,
            origin=origin,
            origin_reference=origin_reference,
            start_offset=start_offset,
            end_offset=end_offset,
        )


def source_document_binding(document: EngineeringDocument) -> SourceDocumentBinding:
    """Return edition metadata and a source-only deterministic revision for one document."""

    payload = {
        "contract": SOURCE_REVISION_CONTRACT,
        "document_key": document.key.value,
        "document_type": document.document_type.value,
        "year": document.year,
        "version": document.version,
        "clauses": [
            {
                "id": clause.id.value,
                "reference": clause.reference.model_dump(mode="json"),
                "clause_type": clause.clause_type.value,
                "baseline": clause.baseline.model_dump(mode="json"),
                "provenance": _source_provenance_payload(clause),
            }
            for clause in document.clauses
        ],
        "tables": [table.model_dump(mode="json") for table in document.tables],
        "table_index": [entry.model_dump(mode="json") for entry in document.table_index],
    }
    artifact_revision = (
        f"sha256:{document.lineage.artifact.content_hash}" if document.lineage is not None else None
    )
    return SourceDocumentBinding(
        document_key=document.key.value,
        year=document.year,
        version=document.version,
        source_revision=f"sha256:{canonical_content_hash(payload)}",
        artifact_revision=artifact_revision,
    )


def _source_provenance_payload(clause: Clause) -> dict[str, object]:
    provenance = clause.provenance

    def source_path(path: str) -> bool:
        return path == "clause_type" or path.startswith("baseline.")

    return {
        "generated_attributes": [
            item.model_dump(mode="json")
            for item in provenance.generated_attributes
            if source_path(item.path)
        ],
        "confirmed_attributes": [
            item.model_dump(mode="json")
            for item in provenance.confirmed_attributes
            if source_path(item.path)
        ],
        "unattributed_attributes": [
            path for path in provenance.unattributed_attributes if source_path(path)
        ],
    }


def heading_surface_origin(clause: Clause) -> tuple[SourceSurfaceOrigin, str | None]:
    """Classify the heading value without promoting structural display labels to source text.

    Older EngineeringDocuments may contain AtlasData TOC display labels such as ``REQUIREMENT``
    or ``OBJECTIVE`` without attribute provenance.  ``source_token`` identifies those clauses as
    AtlasData-backed structure.  Non-placeholder AtlasData titles remain a confirmed source
    assignment (for example a term heading such as ``hazard log``); known structural placeholders
    are explicitly synthetic and therefore have no heading source surface.
    """

    if clause.heading is None or clause.heading == "":
        return SourceSurfaceOrigin.UNRESOLVED, None
    origin, reference = _attribute_origin(clause, "baseline.heading")
    if origin is not SourceSurfaceOrigin.UNRESOLVED:
        return origin, reference
    if clause.source_token is None:
        return origin, reference
    if _is_atlasdata_structural_display_label(clause):
        return SourceSurfaceOrigin.SYNTHETIC_DISPLAY_LABEL, "atlasdata-structural-display-label"
    return SourceSurfaceOrigin.CONFIRMED_SOURCE_ASSIGNMENT, "atlasdata-structure-title"


def clause_has_heading_source_surface(clause: Clause) -> bool:
    """Return whether ``clause.heading`` denotes an addressable heading source surface."""

    if clause.heading is None or clause.heading == "":
        return False
    origin, _ = heading_surface_origin(clause)
    return origin is not SourceSurfaceOrigin.SYNTHETIC_DISPLAY_LABEL


def _is_atlasdata_structural_display_label(clause: Clause) -> bool:
    if clause.heading is None:
        return False
    labels = _ATLASDATA_STRUCTURAL_DISPLAY_LABELS.get(clause.clause_type, frozenset())
    return clause.heading.strip() in labels


def _attribute_origin(clause: Clause, path: str) -> tuple[SourceSurfaceOrigin, str | None]:
    confirmed = [
        item
        for item in clause.provenance.confirmed_attributes
        if path == item.path or path.startswith(item.path + ".")
    ]
    if confirmed:
        source = max(confirmed, key=lambda item: len(item.path))
        return SourceSurfaceOrigin.CONFIRMED_SOURCE_ASSIGNMENT, source.authority

    generated = [
        item
        for item in clause.provenance.generated_attributes
        if path == item.path or path.startswith(item.path + ".")
    ]
    if generated:
        source = max(generated, key=lambda item: len(item.path))
        if source.availability != "known":
            return SourceSurfaceOrigin.UNRESOLVED, source.generator
        if source.method is GenerationMethod.SOURCE_EXTRACTION:
            return SourceSurfaceOrigin.SOURCE_EXTRACTION, source.generator
        if source.method is GenerationMethod.DETERMINISTIC:
            if source.generator in _SYNTHETIC_HEADING_GENERATORS:
                return SourceSurfaceOrigin.SYNTHETIC_DISPLAY_LABEL, source.generator
            return SourceSurfaceOrigin.DETERMINISTIC_PROJECTION, source.generator
        return SourceSurfaceOrigin.UNRESOLVED, source.generator

    return SourceSurfaceOrigin.UNRESOLVED, None


def _content_is_source_backed(content: tuple[ContentBlock, ...]) -> bool:
    blocks = tuple(_iter_content_blocks(content))
    return bool(blocks) and all(block.source_evidence for block in blocks)


def _media_origin(
    block: TableBlock | FormulaBlock,
    clause: Clause,
) -> tuple[SourceSurfaceOrigin, str | None]:
    if block.source_evidence:
        return SourceSurfaceOrigin.SOURCE_EXTRACTION, "content-block-source-evidence"
    return _attribute_origin(clause, "baseline.content")


def _is_source_backed(origin: SourceSurfaceOrigin) -> bool:
    return origin in {
        SourceSurfaceOrigin.SOURCE_EXTRACTION,
        SourceSurfaceOrigin.CONFIRMED_SOURCE_ASSIGNMENT,
    }


def _single_clause(document: EngineeringDocument, clause_id: str) -> Clause | None:
    matches = [clause for clause in document.clauses if clause.id.value == clause_id]
    return matches[0] if len(matches) == 1 else None


def _iter_content_blocks(content: tuple[ContentBlock, ...]) -> Iterator[ContentBlock]:
    for block in content:
        yield block
        if isinstance(block, NoteBlock):
            yield from _iter_content_blocks(block.content)


def _content_block_by_id(content: tuple[ContentBlock, ...], block_id: str) -> ContentBlock | None:
    matches = [block for block in _iter_content_blocks(content) if block.id == block_id]
    return matches[0] if len(matches) == 1 else None


def _validate_requested_offsets(start_offset: int | None, end_offset: int | None) -> None:
    if (start_offset is None) != (end_offset is None):
        raise ValueError("source excerpt offsets must be supplied together")
    if start_offset is not None and (
        start_offset < 0 or end_offset is None or end_offset <= start_offset
    ):
        raise ValueError("source excerpt offsets must form a non-empty half-open range")


def _resolved_text(
    source_ref: SourceSurfaceRef,
    identity: SourceSurfaceIdentity,
    source_text: str,
    *,
    rendering_id: str,
    origin: SourceSurfaceOrigin,
    origin_reference: str | None,
    start_offset: int | None,
    end_offset: int | None,
    media: SourceMediaHandle | None = None,
) -> SourceSurfaceResolution:
    if start_offset is None:
        start, end = 0, len(source_text)
    else:
        assert end_offset is not None
        start, end = start_offset, end_offset
    if end > len(source_text):
        raise ValueError("source excerpt offsets exceed the canonical surface")
    text = source_text[start:end]
    return SourceSurfaceResolution(
        requested=source_ref,
        availability=SourceSurfaceAvailability.AVAILABLE,
        identity=identity,
        origin=origin,
        origin_reference=origin_reference,
        source_backed=_is_source_backed(origin),
        rendering_id=rendering_id,
        surface_sha256=_sha256(source_text),
        content_sha256=_sha256(text),
        start_offset=start,
        end_offset=end,
        text=text,
        media=media,
        reason="requested canonical source surface is available",
    )


def _sha256(value: str) -> str:
    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


def _unavailable(
    source_ref: SourceSurfaceRef,
    availability: SourceSurfaceAvailability,
    reason: str,
) -> SourceSurfaceResolution:
    return SourceSurfaceResolution(
        requested=source_ref,
        availability=availability,
        reason=reason,
    )


def _missing_surface(
    source_ref: SourceSurfaceRef,
    identity: SourceSurfaceIdentity,
    reason: str,
) -> SourceSurfaceResolution:
    return SourceSurfaceResolution(
        requested=source_ref,
        availability=SourceSurfaceAvailability.MISSING,
        identity=identity,
        reason=reason,
    )


def _unauthorized_text(
    source_ref: SourceSurfaceRef,
    identity: SourceSurfaceIdentity,
    origin: SourceSurfaceOrigin,
    origin_reference: str | None,
    *,
    media: SourceMediaHandle | None = None,
) -> SourceSurfaceResolution:
    return SourceSurfaceResolution(
        requested=source_ref,
        availability=SourceSurfaceAvailability.NOT_AUTHORIZED,
        identity=identity,
        origin=origin,
        origin_reference=origin_reference,
        source_backed=_is_source_backed(origin),
        media=media,
        reason="source text is outside the configured exposure boundary",
    )
