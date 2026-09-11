"""Explicit AtlasData roundtrips using existing import, repository and merge paths."""

from __future__ import annotations

import re
from collections import Counter
from copy import deepcopy
from pathlib import Path

import yaml

from standards_atlas.application.catalog.atlasdata_binding import AtlasDataBinding
from standards_atlas.application.ports import EngineeringDocumentRepository
from standards_atlas.application.schema import require_supported_schema
from standards_atlas.application.services.document_selection_service import select_document_part
from standards_atlas.domain.model import DocumentKey, EngineeringDocument
from standards_atlas.domain.model.clause import Clause
from standards_atlas.domain.model.enrichment_patch import (
    ClauseEnrichmentPatch,
    SemanticEnrichmentPatch,
    merge_persisted_enrichments,
)
from standards_atlas.domain.model.knowledge_state import KnowledgeStateProvenance
from standards_atlas.domain.model.semantic_classification import SemanticClassification

from .domain_mapper import extract_clause_identity
from .import_pipeline import AtlasDataImportPipeline
from .knowledge_contract import (
    ALL_PATHS,
    DIMENSION_PATHS,
    UNPUBLISHED_APPLICABILITY_PATHS,
    UNPUBLISHED_ROLE_PATHS,
    AtlasDataKnowledge,
    AtlasDataKnowledgeReport,
    ClauseKnowledge,
    PublishedAttribute,
    TransferChange,
)
from .knowledge_evidence import KnowledgeEvidenceStore, atomic_write, canonical_bytes, digest
from .knowledge_projection import (
    check_public_attribute,
    hydrate_attribute,
    project_attribute,
    public_value,
)


class _UniqueLoader(getattr(yaml, "CSafeLoader", yaml.SafeLoader)):
    pass


def _unique_mapping(loader: _UniqueLoader, node: yaml.MappingNode) -> dict:
    loader.flatten_mapping(node)
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if not isinstance(key, str):
            raise ValueError("AtlasData enrichment YAML mapping keys must be strings")
        if key in result:
            raise ValueError(f"duplicate key in AtlasData enrichment YAML: {key}")
        result[key] = loader.construct_object(value_node)
    return result


_UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_mapping)

_SHA256_REFERENCE = re.compile(r"sha256:([0-9a-f]{64})\Z")


def _sha256_reference(value: str) -> str:
    match = _SHA256_REFERENCE.fullmatch(value)
    if match is not None:
        return value
    if re.fullmatch(r"[0-9a-f]{64}", value):
        return f"sha256:{value}"
    raise ValueError(f"invalid SHA-256 fingerprint: {value!r}")


def _sha256_digest(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("SHA-256 fingerprint must be a string")
    match = _SHA256_REFERENCE.fullmatch(value)
    if match is None:
        raise ValueError(f"invalid SHA-256 fingerprint reference: {value!r}")
    return match.group(1)


def _wire_to_model_payload(payload: dict) -> dict:
    """Expand compact schema-1.2 fingerprints into the internal transport model."""

    result = deepcopy(payload)
    if "structure_sha256" in result:
        raise ValueError("schema 1.2 stores structure fingerprints under fingerprints")
    fingerprints = result.pop("fingerprints", None)
    if not isinstance(fingerprints, dict) or set(fingerprints) != {"structure"}:
        raise ValueError("AtlasData enrichments require fingerprints.structure")
    result["structure_sha256"] = _sha256_digest(fingerprints["structure"])

    clauses = result.get("clauses", ())
    if not isinstance(clauses, list):
        raise ValueError("AtlasData enrichment clauses must be a list")
    for clause in clauses:
        if not isinstance(clause, dict):
            raise ValueError("AtlasData enrichment clause must be a mapping")
        for legacy in ("heading_sha256", "atlasdata_heading_sha256", "content_sha256"):
            if legacy in clause:
                raise ValueError(f"schema 1.2 stores {legacy} under fingerprints")
        clause_fingerprints = clause.pop("fingerprints", None)
        if not isinstance(clause_fingerprints, dict):
            raise ValueError("AtlasData enrichment clause requires fingerprints")
        allowed = {"heading", "atlasdata_heading", "content", "attributes"}
        unknown = set(clause_fingerprints) - allowed
        if unknown:
            raise ValueError(f"unknown clause fingerprint fields: {sorted(unknown)}")
        clause["heading_sha256"] = _sha256_digest(clause_fingerprints.get("heading"))
        clause["atlasdata_heading_sha256"] = _sha256_digest(
            clause_fingerprints.get("atlasdata_heading")
        )
        if "content" in clause_fingerprints:
            clause["content_sha256"] = _sha256_digest(clause_fingerprints["content"])

        attribute_fingerprints = clause_fingerprints.get("attributes", {})
        if not isinstance(attribute_fingerprints, dict):
            raise ValueError("fingerprints.attributes must be a mapping")
        attributes = clause.get("attributes", ())
        if not isinstance(attributes, list):
            raise ValueError("AtlasData enrichment attributes must be a list")
        paths = {item.get("path") for item in attributes if isinstance(item, dict)}
        dangling = set(attribute_fingerprints) - paths
        if dangling:
            raise ValueError(f"fingerprints reference unknown attributes: {sorted(dangling)}")
        for attribute in attributes:
            if not isinstance(attribute, dict):
                raise ValueError("AtlasData enrichment attribute must be a mapping")
            path = attribute.get("path")
            fps = attribute_fingerprints.get(path, {})
            if not isinstance(fps, dict):
                raise ValueError(f"attribute fingerprints must be a mapping: {path}")
            allowed_attribute_fps = {
                "evidence",
                "decision_source",
                "private_value",
                "private_provenance",
            }
            unknown = set(fps) - allowed_attribute_fps
            if unknown:
                raise ValueError(
                    f"unknown attribute fingerprint fields for {path}: {sorted(unknown)}"
                )

            if "private_value_sha256" in attribute or "private_provenance_sha256" in attribute:
                raise ValueError("schema 1.2 stores private fingerprints under fingerprints")
            if "private_value" in fps:
                attribute["private_value_sha256"] = _sha256_digest(fps["private_value"])
            if "private_provenance" in fps:
                attribute["private_provenance_sha256"] = _sha256_digest(fps["private_provenance"])

            availability = attribute.get("availability", "known")
            generated = attribute.get("generated")
            if generated is not None:
                if not isinstance(generated, dict):
                    raise ValueError(f"generated provenance must be a mapping: {path}")
                legacy = {"path", "availability", "evidence"} & set(generated)
                if legacy:
                    raise ValueError(
                        "schema 1.2 derives generated "
                        f"{sorted(legacy)} from the attribute/fingerprints"
                    )
                generated["path"] = path
                generated["availability"] = availability
                evidence = fps.get("evidence", [])
                if not isinstance(evidence, list):
                    raise ValueError(f"evidence fingerprints must be a list: {path}")
                generated["evidence"] = tuple(
                    f"sha256:{_sha256_digest(value)}" for value in evidence
                )
                decision = generated.get("decision")
                if decision is not None:
                    if not isinstance(decision, dict):
                        raise ValueError(f"decision provenance must be a mapping: {path}")
                    if "source_sha256" in decision:
                        raise ValueError(
                            "schema 1.2 stores decision source fingerprints under fingerprints"
                        )
                    if "decision_source" not in fps:
                        raise ValueError(f"decision requires decision_source fingerprint: {path}")
                    decision["source_sha256"] = _sha256_digest(fps["decision_source"])
                elif "decision_source" in fps:
                    raise ValueError(f"decision_source fingerprint without decision: {path}")
            elif "evidence" in fps or "decision_source" in fps:
                raise ValueError(f"generated fingerprints without generated provenance: {path}")

            confirmed = attribute.get("confirmed")
            if confirmed is not None:
                if not isinstance(confirmed, dict):
                    raise ValueError(f"confirmed provenance must be a mapping: {path}")
                if "path" in confirmed:
                    raise ValueError("schema 1.2 derives confirmed path from the attribute")
                confirmed["path"] = path
    return result


def _model_to_wire_payload(manifest: AtlasDataKnowledge) -> dict:
    """Serialize schema 1.2 with one readable fingerprint block per scope."""

    payload = manifest.model_dump(mode="json")
    clauses = payload.pop("clauses")
    payload["fingerprints"] = {
        "structure": _sha256_reference(payload.pop("structure_sha256")),
    }
    payload["clauses"] = clauses
    for clause in clauses:
        clause_fingerprints: dict[str, object] = {
            "heading": _sha256_reference(clause.pop("heading_sha256")),
            "atlasdata_heading": _sha256_reference(clause.pop("atlasdata_heading_sha256")),
        }
        content = clause.pop("content_sha256")
        if content is not None:
            clause_fingerprints["content"] = _sha256_reference(content)
        attribute_fingerprints: dict[str, dict[str, object]] = {}
        for attribute in clause["attributes"]:
            path = attribute["path"]
            fps: dict[str, object] = {}
            private_value = attribute.pop("private_value_sha256")
            private_provenance = attribute.pop("private_provenance_sha256")
            if private_value is not None:
                fps["private_value"] = _sha256_reference(private_value)
            if private_provenance is not None:
                fps["private_provenance"] = _sha256_reference(private_provenance)

            generated = attribute.get("generated")
            if generated is not None:
                generated.pop("path")
                generated.pop("availability")
                evidence = generated.pop("evidence")
                if evidence:
                    fps["evidence"] = [_sha256_reference(value) for value in evidence]
                decision = generated.get("decision")
                if decision is not None:
                    fps["decision_source"] = _sha256_reference(decision.pop("source_sha256"))
                if generated.get("decision") is None:
                    generated.pop("decision", None)

            confirmed = attribute.get("confirmed")
            if confirmed is not None:
                confirmed.pop("path")
            if attribute.get("generated") is None:
                attribute.pop("generated", None)
            if attribute.get("confirmed") is None:
                attribute.pop("confirmed", None)
            if attribute.get("availability") == "known":
                attribute.pop("availability")
            if fps:
                attribute_fingerprints[path] = fps
        if attribute_fingerprints:
            clause_fingerprints["attributes"] = attribute_fingerprints
        clause["fingerprints"] = clause_fingerprints
    return payload


def read_knowledge(path: Path) -> AtlasDataKnowledge:
    payload = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueLoader)
    if not isinstance(payload, dict):
        raise ValueError("AtlasData enrichments must be a versioned mapping")
    require_supported_schema("atlasdata-enrichments", payload.get("schema_version"))
    result = AtlasDataKnowledge.model_validate(_wire_to_model_payload(payload))
    for clause in result.clauses:
        for attribute in clause.attributes:
            check_public_attribute(attribute)
        _validate_semantics(clause.attributes)
    return result


def _omit_unpublished_details(
    manifest: AtlasDataKnowledge,
) -> tuple[AtlasDataKnowledge, list[TransferChange]]:
    """Remove deferred public fields, not canonical values or private evidence.

    Apply to the whole selected companion, even on a dimension/clause-limited
    export, so retained old records cannot leak fields outside publication policy.
    Attribute fingerprints are serialized from the remaining records only.
    """
    unpublished_paths = UNPUBLISHED_APPLICABILITY_PATHS | UNPUBLISHED_ROLE_PATHS
    clauses = []
    changes = []
    for clause in manifest.clauses:
        attributes = []
        for item in clause.attributes:
            if item.path not in unpublished_paths:
                attributes.append(item)
                continue
            dimension = "applicability" if item.path in UNPUBLISHED_APPLICABILITY_PATHS else "role"
            changes.append(
                TransferChange(
                    document_key=manifest.document_key,
                    clause_id=clause.clause_id,
                    path=item.path,
                    status="omitted",
                    before=item.value,
                    reason=(
                        f"{dimension} detail publication is deferred; "
                        f"only {dimension} presence is published; "
                        "canonical values and private evidence are unchanged"
                    ),
                )
            )
        if attributes:
            clauses.append(clause.model_copy(update={"attributes": tuple(attributes)}))
        # A companion record without any published attributes is not meaningful.
        # Other clauses and all their remaining attributes retain their order.
    return manifest.model_copy(update={"clauses": tuple(clauses)}), changes


def knowledge_bytes(manifest: AtlasDataKnowledge) -> bytes:
    # Revalidate model_copy updates as well as normally constructed objects.
    manifest = AtlasDataKnowledge.model_validate(manifest.model_dump(mode="json"))
    manifest, _ = _omit_unpublished_details(manifest)
    for clause in manifest.clauses:
        _validate_semantics(clause.attributes)
        for attribute in clause.attributes:
            check_public_attribute(attribute)
    return yaml.dump(
        _model_to_wire_payload(manifest),
        Dumper=getattr(yaml, "CSafeDumper", yaml.SafeDumper),
        sort_keys=False,
        allow_unicode=True,
        width=100,
    ).encode("utf-8")


def _validate_semantics(attributes: tuple[PublishedAttribute, ...]) -> None:
    fields = {
        item.path.rsplit(".", 1)[-1]: item.value
        for item in attributes
        if item.path.startswith("enrichments.semantic.")
        and item.path != "enrichments.semantic.role_relations"
        and item.availability == "known"
    }
    SemanticClassification.model_validate(fields)


def structure_digest(document: EngineeringDocument) -> str:
    return digest(
        canonical_bytes(
            [
                {
                    "id": clause.id.value,
                    "reference": clause.reference.model_dump(mode="json"),
                    "heading": clause.heading,
                    "clause_type": clause.clause_type.value,
                    "parent_id": clause.parent_id.value if clause.parent_id else None,
                }
                for clause in document.clauses
            ]
        )
    )


def _heading_digest(heading: str | None) -> str:
    return digest((heading or "").encode())


def _head(binding: AtlasDataBinding, skeleton: EngineeringDocument) -> AtlasDataKnowledge:
    return AtlasDataKnowledge(
        document_key=binding.document_key,
        family_key=binding.family_key,
        atlasdata_file=binding.source.name,
        selection_part=binding.selection_part,
        publication_year=binding.publication_year,
        structure_sha256=structure_digest(skeleton),
    )


def _check_header(manifest: AtlasDataKnowledge, expected: AtlasDataKnowledge) -> None:
    if manifest.model_dump(exclude={"clauses"}) != expected.model_dump(exclude={"clauses"}):
        raise ValueError(f"AtlasData identity/edition/structure mismatch: {manifest.document_key}")


def _clauses(document: EngineeringDocument) -> dict[str, Clause]:
    result = {clause.id.value: clause for clause in document.clauses}
    references = {clause.reference.as_text() for clause in document.clauses}
    if len(result) != len(document.clauses) or len(references) != len(result):
        raise ValueError(f"duplicate target clause identity: {document.key.value}")
    return result


def _check_clause(
    record: ClauseKnowledge,
    clause: Clause | None,
    *,
    key: str,
    structural: bool = False,
) -> bool:
    if clause is None:
        raise ValueError(f"missing AtlasData clause: {key}/{record.clause_id}")
    expected_headings = {record.atlasdata_heading_sha256} if structural else {record.heading_sha256}
    if not structural and not clause.plain_text:
        # A fresh structural import has the reviewed AtlasData heading, not necessarily
        # the independently normalized local source heading used for enrichment.
        expected_headings.add(record.atlasdata_heading_sha256)
    if (
        clause.reference != record.reference
        or _heading_digest(clause.heading) not in expected_headings
    ):
        raise ValueError(f"AtlasData clause reference/heading mismatch: {key}/{record.clause_id}")
    if record.content_sha256 is not None and clause.plain_text:
        if digest(clause.plain_text.encode()) != record.content_sha256:
            raise ValueError(f"AtlasData clause content mismatch: {key}/{record.clause_id}")
        return True
    return False


def _check_atlasdata_md5(
    record: ClauseKnowledge,
    atlasdata_md5s: dict[str, str],
    *,
    key: str,
) -> None:
    expected = atlasdata_md5s.get(record.clause_id)
    if expected is None or record.atlasdata_md5 != expected:
        raise ValueError(f"AtlasData record MD5 mismatch: {key}/{record.clause_id}")


def _same_value(left: PublishedAttribute, right: PublishedAttribute) -> bool:
    return (left.availability, left.value, left.private_value_sha256) == (
        right.availability,
        right.value,
        right.private_value_sha256,
    )


def _merge_record(
    old: ClauseKnowledge | None,
    incoming: ClauseKnowledge,
    *,
    key: str,
) -> tuple[ClauseKnowledge, list[TransferChange]]:
    before = {item.path: item for item in old.attributes} if old else {}
    after = dict(before)
    changes = []
    updates = {item.path: item for item in incoming.attributes}
    if old is not None:
        if (old.atlasdata_md5, old.reference, old.atlasdata_heading_sha256) != (
            incoming.atlasdata_md5,
            incoming.reference,
            incoming.atlasdata_heading_sha256,
        ):
            raise ValueError(f"changed clause identity in AtlasData sidecar: {key}/{old.clause_id}")
        if old.heading_sha256 != incoming.heading_sha256:
            if (
                incoming.content_sha256 is None
                and incoming.heading_sha256 == incoming.atlasdata_heading_sha256
            ):
                incoming = incoming.model_copy(
                    update={"heading": old.heading, "heading_sha256": old.heading_sha256}
                )
            else:
                raise ValueError(f"stale AtlasData enrichment heading: {key}/{old.clause_id}")
        if (
            old.content_sha256
            and incoming.content_sha256
            and old.content_sha256 != incoming.content_sha256
        ):
            raise ValueError(f"stale AtlasData enrichment content: {key}/{old.clause_id}")
    for group in DIMENSION_PATHS.values():
        addressed = [path for path in group if path in updates]
        conflicts = []
        for path in addressed:
            previous, proposal = before.get(path), updates[path]
            if previous is None or proposal.availability == "unknown":
                continue
            if previous.origin in ("confirmed", "unattributed") and not _same_value(
                previous, proposal
            ):
                if previous.origin == proposal.origin == "confirmed":
                    raise ValueError(
                        "conflicting authoritative AtlasData values: "
                        f"{key}/{incoming.clause_id}/{path}"
                    )
                conflicts.append(path)
        for path in addressed:
            previous, proposal = before.get(path), updates[path]
            reason = None
            if conflicts:
                status, reason = "protected", ", ".join(conflicts)
            elif (
                previous is not None
                and previous.availability == "known"
                and proposal.availability == "unknown"
            ):
                status, reason = "unchanged", "unknown input cannot erase known knowledge"
            elif previous is not None and previous.origin in ("confirmed", "unattributed"):
                status, reason = "unchanged", "existing authority/protection retained"
            else:
                # Public-only reimports retain detached evidence references on re-export.
                if previous and previous.model_dump(
                    exclude={"private_provenance_sha256"}
                ) == proposal.model_dump(exclude={"private_provenance_sha256"}):
                    proposal = previous
                after[path] = proposal
                status = "unchanged" if previous == proposal else "updated"
            changes.append(
                TransferChange(
                    document_key=key,
                    clause_id=incoming.clause_id,
                    path=path,
                    status=status,
                    before=previous.value if previous else None,
                    after=after[path].value if path in after else None,
                    reason=reason,
                )
            )
    record = incoming.model_copy(
        update={
            "content_sha256": incoming.content_sha256 or (old.content_sha256 if old else None),
            "attributes": tuple(after[path] for path in sorted(after)),
        }
    )
    _validate_semantics(record.attributes)
    return record, changes


class AtlasDataKnowledgeService:
    """Explicit per-physical-document transfer; every preflight precedes writes.

    The adapter orchestrates the AtlasData codec and the existing repository port.
    No automatic workflow writes, no models, no synthetic canonical family state.
    """

    def __init__(
        self,
        *,
        documents: EngineeringDocumentRepository,
        bindings: dict[str, AtlasDataBinding],
        evidence_root: Path,
    ) -> None:
        self.documents = documents
        self.bindings = bindings
        self.evidence_root = evidence_root.resolve()
        self.pipeline = AtlasDataImportPipeline()

    def _select(self, document_keys: tuple[str, ...], *, exporting: bool) -> tuple[str, ...]:
        if len(document_keys) != len(set(document_keys)):
            raise ValueError("duplicate selected document keys")
        if set(document_keys) - self.bindings.keys():
            raise ValueError(
                "selected keys must identify manifest-declared physical AtlasData documents"
            )
        keys = document_keys or tuple(
            key
            for key, binding in self.bindings.items()
            if (
                self.documents.exists(DocumentKey(value=key))
                if exporting
                else binding.enrichments_path.exists()
            )
        )
        if not keys:
            raise ValueError("no physical documents/enrichment files selected")
        for key in keys:
            public_root = self.bindings[key].source.parent.resolve()
            if self.evidence_root.is_relative_to(public_root):
                raise ValueError(
                    "private evidence root must be outside the public AtlasData directory"
                )
        return tuple(sorted(keys))

    def _skeleton(
        self,
        binding: AtlasDataBinding,
        sources: dict[Path, EngineeringDocument] | None = None,
    ) -> EngineeringDocument:
        # Share only operation-local immutable family inputs. Never cache across transfers.
        if binding.selection_part is not None and sources is not None:
            if binding.source not in sources:
                sources[binding.source] = self.pipeline.import_file(binding.source)
            return select_document_part(
                sources[binding.source],
                binding.document_key,
                binding.selection_part,
                binding.title,
            )
        return self.pipeline.import_physical(
            binding.source,
            document_key=binding.document_key,
            part=binding.selection_part,
            title=binding.title,
        )

    def _atlasdata_md5s(
        self,
        binding: AtlasDataBinding,
        skeleton: EngineeringDocument,
    ) -> dict[str, str]:
        atlas_data = self.pipeline.parse_file(binding.source)
        by_identity: dict[tuple[str | None, str], str] = {}
        for record in atlas_data.initialization_records:
            if record.kind != "TOC":
                continue
            identity = extract_clause_identity(record.reference, atlas_data.metadata.name)
            if identity is None:
                continue
            previous = by_identity.get(identity)
            if previous is not None and previous != record.hash_value:
                raise ValueError(f"duplicate AtlasData TOC identity with different MD5: {identity}")
            by_identity[identity] = record.hash_value
        result: dict[str, str] = {}
        for clause in skeleton.clauses:
            identity = (clause.reference.part, clause.reference.clause)
            value = by_identity.get(identity)
            if value is None:
                raise ValueError(
                    f"missing AtlasData TOC MD5: {binding.document_key}/{clause.id.value}"
                )
            result[clause.id.value] = value
        return result

    def export(
        self,
        *,
        document_keys: tuple[str, ...] = (),
        dimensions: tuple[str, ...] = (),
        clause_ids: tuple[str, ...] = (),
        write: bool = False,
    ) -> AtlasDataKnowledgeReport:
        keys = self._select(document_keys, exporting=True)
        if clause_ids and len(keys) != 1:
            raise ValueError("clause selection requires exactly one physical document")
        if set(dimensions) - DIMENSION_PATHS.keys():
            raise ValueError("unsupported AtlasData enrichment dimension")
        paths = (
            tuple(path for name in dimensions for path in DIMENSION_PATHS[name])
            if dimensions
            else ALL_PATHS
        )
        unpublished_paths = UNPUBLISHED_APPLICABILITY_PATHS | UNPUBLISHED_ROLE_PATHS
        paths = tuple(path for path in paths if path not in unpublished_paths)
        store = KnowledgeEvidenceStore(self.evidence_root)
        pending: dict[Path, bytes] = {}
        changes = []
        verified = unverified = 0
        sources: dict[Path, EngineeringDocument] = {}
        for key in keys:
            binding = self.bindings[key]
            skeleton = self._skeleton(binding, sources)
            atlasdata_md5s = self._atlasdata_md5s(binding, skeleton)
            expected = _head(binding, skeleton)
            destination = binding.enrichments_path
            if destination.is_symlink():
                raise ValueError(f"enrichment destination must not be a symlink: {destination}")
            existing = read_knowledge(destination) if destination.exists() else expected
            _check_header(existing, expected)
            source = self.documents.load(DocumentKey(value=key))
            if source.key.value != key:
                raise ValueError("canonical repository returned the wrong document")
            canonical_clauses, structural_clauses = _clauses(source), _clauses(skeleton)
            if set(clause_ids) - canonical_clauses.keys():
                raise ValueError("selected clauses do not exist in the physical document")
            # Validate every old identity before removing any deferred public fields.
            for old in existing.clauses:
                _check_clause(old, structural_clauses.get(old.clause_id), key=key, structural=True)
                _check_atlasdata_md5(old, atlasdata_md5s, key=key)
            existing, omitted = _omit_unpublished_details(existing)
            changes.extend(omitted)
            records = {item.clause_id: item for item in existing.clauses}
            # Other unselected clauses and dimensions keep their existing state.
            for clause in source.clauses:
                clause_id = clause.id.value
                if clause_ids and clause_id not in clause_ids:
                    continue
                attributes = tuple(
                    item
                    for path in sorted(set(paths))
                    if (item := project_attribute(clause, path, store, document=source)) is not None
                )
                if not attributes:
                    continue
                structural_clause = structural_clauses.get(clause_id)
                if structural_clause is None:
                    raise ValueError(f"missing AtlasData clause: {key}/{clause_id}")
                record = ClauseKnowledge(
                    clause_id=clause_id,
                    atlasdata_md5=atlasdata_md5s[clause_id],
                    reference=clause.reference,
                    heading=clause.heading,
                    heading_sha256=_heading_digest(clause.heading),
                    atlasdata_heading_sha256=_heading_digest(structural_clause.heading),
                    content_sha256=(
                        digest(clause.plain_text.encode()) if clause.plain_text else None
                    ),
                    attributes=attributes,
                )
                _check_clause(record, structural_clause, key=key, structural=True)
                verified += bool(clause.plain_text)
                unverified += not bool(clause.plain_text)
                merged, delta = _merge_record(records.get(clause_id), record, key=key)
                records[clause_id] = merged
                changes.extend(delta)
            manifest = expected.model_copy(
                update={
                    "clauses": tuple(
                        records[clause.id.value]
                        for clause in skeleton.clauses
                        if clause.id.value in records
                    ),
                }
            )
            # Detect conflicting authoritative tags and companion values before publication.
            self._restore(skeleton, manifest, store, strict_evidence=False)
            data = knowledge_bytes(manifest)
            if not destination.exists() or destination.read_bytes() != data:
                pending[destination] = data
        store.validate_pending()
        if write:
            store.commit()  # Private references are durable before public files refer to them.
            for path, data in pending.items():
                atomic_write(path, data)
        return self._report("export", keys, pending, changes, write, verified, unverified)

    def import_(
        self,
        *,
        document_keys: tuple[str, ...] = (),
        write: bool = False,
        strict_evidence: bool = False,
    ) -> AtlasDataKnowledgeReport:
        keys = self._select(document_keys, exporting=False)
        store = KnowledgeEvidenceStore(self.evidence_root)
        pending = {}
        changes = []
        verified = unverified = 0
        sources: dict[Path, EngineeringDocument] = {}
        for key in keys:
            binding = self.bindings[key]
            manifest = read_knowledge(binding.enrichments_path)
            skeleton = self._skeleton(binding, sources)
            atlasdata_md5s = self._atlasdata_md5s(binding, skeleton)
            _check_header(manifest, _head(binding, skeleton))
            for record in manifest.clauses:
                _check_atlasdata_md5(record, atlasdata_md5s, key=key)
            original = (
                self.documents.load(DocumentKey(value=key))
                if self.documents.exists(DocumentKey(value=key))
                else None
            )
            document = original or skeleton
            if document.key.value != key:
                raise ValueError("canonical repository returned the wrong document")
            # Current reviewed TOC tags always participate, including when restoring into
            # an existing enriched workspace. They cannot be bypassed by a stale document.
            document, tag_changes = self._apply_current_tags(
                document,
                skeleton,
                manifest,
                store,
            )
            changes.extend(tag_changes)
            restored, delta, checked, unchecked = self._restore(
                document,
                manifest,
                store,
                strict_evidence=strict_evidence,
            )
            changes.extend(delta)
            verified += checked
            unverified += unchecked
            if restored != original:
                pending[key] = restored
        if write:
            for document in pending.values():
                self.documents.save(document)
        return self._report("import", keys, pending, changes, write, verified, unverified)

    @staticmethod
    def _apply_current_tags(
        document: EngineeringDocument,
        skeleton: EngineeringDocument,
        manifest: AtlasDataKnowledge,
        store: KnowledgeEvidenceStore,
    ) -> tuple[EngineeringDocument, list[TransferChange]]:
        clauses, baseline = _clauses(document), _clauses(skeleton)
        changes = []
        for record in manifest.clauses:
            current = clauses.get(record.clause_id)
            structural = baseline.get(record.clause_id)
            _check_clause(record, structural, key=document.key.value, structural=True)
            _check_clause(record, current, key=document.key.value)
            attributes = tuple(
                item
                for path in ALL_PATHS
                if (item := project_attribute(structural, path, store)) is not None
                and item.origin == "confirmed"
            )
            if attributes:
                tagged = record.model_copy(update={"attributes": attributes})
                restored, delta, _, _ = AtlasDataKnowledgeService._restore(
                    document.model_copy(update={"clauses": (current,)}),
                    manifest.model_copy(update={"clauses": (tagged,)}),
                    store,
                    strict_evidence=False,
                )
                clauses[record.clause_id] = restored.clauses[0]
                changes.extend(
                    item.model_copy(
                        update={
                            "reason": "current reviewed TOC tags; " + (item.reason or "restored"),
                        }
                    )
                    for item in delta
                )
        restored = document.model_copy(
            update={
                "clauses": tuple(clauses[c.id.value] for c in document.clauses),
            }
        )
        return restored, changes

    @staticmethod
    def _restore(
        document: EngineeringDocument,
        manifest: AtlasDataKnowledge,
        store: KnowledgeEvidenceStore,
        *,
        strict_evidence: bool,
    ) -> tuple[EngineeringDocument, list[TransferChange], int, int]:
        clauses = _clauses(document)
        changes = []
        verified = unverified = 0
        for record in manifest.clauses:
            clause = clauses.get(record.clause_id)
            checked = _check_clause(record, clause, key=document.key.value)
            verified += checked
            unverified += not checked
            semantic, context = {}, {}
            generated, confirmed, unattributed = [], [], []
            for item in record.attributes:
                value, provenance, deferred, missing = hydrate_attribute(item, store)
                if strict_evidence and missing:
                    raise ValueError(
                        f"missing private evidence: {document.key.value}/"
                        f"{record.clause_id}/{item.path}"
                    )
                if deferred:
                    changes.append(
                        TransferChange(
                            document_key=document.key.value,
                            clause_id=record.clause_id,
                            path=item.path,
                            status="deferred",
                            after=item.value,
                            reason="private value unavailable; existing canonical value retained",
                        )
                    )
                    continue
                if missing:
                    changes.append(
                        TransferChange(
                            document_key=document.key.value,
                            clause_id=record.clause_id,
                            path=item.path,
                            status="evidence_unavailable",
                            reason=(
                                "public provenance and hash references retained; "
                                "raw evidence not hydrated"
                            ),
                        )
                    )
                if item.availability == "known":
                    if item.path.startswith("enrichments.semantic."):
                        semantic[item.path.rsplit(".", 1)[-1]] = value
                    else:
                        context[item.path.rsplit(".", 1)[-1]] = value
                if item.origin == "generated":
                    generated.append(provenance)
                elif item.origin == "confirmed":
                    confirmed.append(provenance)
                else:
                    unattributed.append(item.path)
            patch = ClauseEnrichmentPatch(
                semantic=SemanticEnrichmentPatch(**semantic) if semantic else None,
                **context,
            )
            result = merge_persisted_enrichments(
                clause,
                patch,
                KnowledgeStateProvenance(
                    generated_attributes=tuple(generated),
                    confirmed_attributes=tuple(confirmed),
                    unattributed_attributes=tuple(unattributed),
                ),
            )
            clauses[record.clause_id] = result.clause
            changes.extend(
                TransferChange(
                    document_key=document.key.value,
                    clause_id=record.clause_id,
                    path=change.path,
                    status=change.status,
                    reason=change.reason,
                    before=public_value(change.path, change.before),
                    after=public_value(change.path, change.after),
                )
                for change in result.changes
            )
        restored = document.model_copy(
            update={
                "clauses": tuple(clauses[c.id.value] for c in document.clauses),
            }
        )
        return restored, changes, verified, unverified

    @staticmethod
    def _report(operation, keys, pending, changes, write, verified, unverified):
        return AtlasDataKnowledgeReport(
            operation=operation,
            write_requested=write,
            document_keys=keys,
            changed_targets=tuple(str(path) for path in pending),
            written_targets=tuple(str(path) for path in pending) if write else (),
            status_counts=dict(sorted(Counter(item.status for item in changes).items())),
            content_verified_clauses=verified,
            content_unverified_clauses=unverified,
            changes=tuple(changes),
        )
