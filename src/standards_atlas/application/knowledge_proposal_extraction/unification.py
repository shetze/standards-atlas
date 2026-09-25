"""Deterministic document-local unification of non-canonical knowledge proposals."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from standards_atlas.application.formal_semantics import ResourceFormalOntologyRepository
from standards_atlas.domain.model import (
    DocumentKnowledgeProposal,
    EntityAssertionObject,
    EvidenceAnchor,
    KnowledgeEntityProposal,
    KnowledgeProposalFailure,
    KnowledgeProposalInput,
    KnowledgeProposalProvenance,
    KnowledgeProposalViolation,
    LiteralAssertionObject,
    NormativeAssertionProposal,
    NormativeForce,
)

KNOWLEDGE_PROPOSAL_UNIFICATION_VERSION = "1.0.0"
_SUBCLASS = re.compile(
    r"stat:(?P<child>[A-Za-z][A-Za-z0-9_-]*)\s+a\s+owl:Class\s*;\s*"
    r"rdfs:subClassOf\s+stat:(?P<parent>[A-Za-z][A-Za-z0-9_-]*)"
)


@dataclass(frozen=True)
class _EntitySource:
    proposal_run_id: str
    entity: KnowledgeEntityProposal


@dataclass(frozen=True)
class _ResolvedEntityGroup:
    normalized_label: str
    class_iri: str
    sources: tuple[_EntitySource, ...]


@dataclass(frozen=True)
class _RewrittenAssertion:
    assertion: NormativeAssertionProposal
    proposal_run_id: str


class _ClassHierarchy:
    def __init__(self, parents: dict[str, frozenset[str]]) -> None:
        self._parents = parents

    def is_ancestor_or_same(self, ancestor: str, descendant: str) -> bool:
        if ancestor == descendant:
            return True
        seen: set[str] = set()
        pending = list(self._parents.get(descendant, ()))
        while pending:
            current = pending.pop()
            if current == ancestor:
                return True
            if current in seen:
                continue
            seen.add(current)
            pending.extend(self._parents.get(current, ()))
        return False

    def compatible(self, left: str, right: str) -> bool:
        return self.is_ancestor_or_same(left, right) or self.is_ancestor_or_same(right, left)

    def most_specific(self, classes: Iterable[str]) -> str:
        unique = set(classes)
        candidates = {
            candidate
            for candidate in unique
            if all(self.is_ancestor_or_same(other, candidate) for other in unique)
        }
        if len(candidates) != 1:
            raise ValueError(
                "compatible ontology class chain must have exactly one most-specific class"
            )
        return next(iter(candidates))


class DocumentKnowledgeProposalUnifier:
    """Merge proposal runs and resolve document-local entities deterministically.

    Resolution is intentionally conservative. Entities merge only when their normalized labels
    match and their ontology classes form one unambiguous subclass chain. The unifier never uses
    embeddings, model similarity, or fuzzy label matching.
    """

    def __init__(
        self,
        ontology_repository: ResourceFormalOntologyRepository | None = None,
    ) -> None:
        self._ontology_repository = ontology_repository or ResourceFormalOntologyRepository()

    def unify(
        self,
        proposals: Sequence[DocumentKnowledgeProposal],
        *,
        proposal_run_id: str,
    ) -> DocumentKnowledgeProposal:
        if not proposals:
            raise ValueError("knowledge proposal unification requires at least one input proposal")
        ordered = tuple(sorted(proposals, key=lambda item: item.proposal_run_id))
        _validate_input_identity(ordered, proposal_run_id)
        document_key = ordered[0].source_document_key
        ontology_versions = ordered[0].ontology_versions
        hierarchy, declared_classes, declared_properties = self._ontology_context(ontology_versions)
        for proposal in ordered:
            if proposal.source_document_key != document_key:
                raise ValueError("knowledge proposal inputs must belong to the same document")
            if proposal.ontology_versions != ontology_versions:
                raise ValueError(
                    "knowledge proposal inputs must use the same ordered ontology selection"
                )
            _validate_semantic_terms(proposal, declared_classes, declared_properties)

        anchors = _merge_anchors(ordered)
        entity_groups = _resolve_entity_groups(ordered, hierarchy)
        entities, entity_ids = _materialize_entities(document_key, entity_groups)
        rewritten_assertions = _rewrite_assertions(ordered, entity_ids)
        assertions = _merge_assertions(document_key, rewritten_assertions)

        return DocumentKnowledgeProposal(
            proposal_run_id=proposal_run_id,
            source_document_key=document_key,
            ontology_versions=ontology_versions,
            input_proposals=tuple(_proposal_input(item) for item in ordered),
            evidence_anchors=tuple(anchors.values()),
            entity_proposals=entities,
            assertion_proposals=assertions,
            violations=_merge_violations(ordered),
            failures=_merge_failures(ordered),
            attempts=tuple(attempt for item in ordered for attempt in item.attempts),
            proposal_provenance=KnowledgeProposalProvenance(
                extractor="document-knowledge-proposal-unifier",
                extractor_version=KNOWLEDGE_PROPOSAL_UNIFICATION_VERSION,
                semantic_task="document-local-entity-resolution",
            ),
        )

    def _ontology_context(
        self,
        ontology_versions: tuple[str, ...],
    ) -> tuple[_ClassHierarchy, set[str], set[str]]:
        if not ontology_versions:
            raise ValueError("knowledge proposal unification requires explicit ontology versions")
        parents: dict[str, set[str]] = defaultdict(set)
        declared_classes: set[str] = set()
        declared_properties: set[str] = set()
        for reference in ontology_versions:
            ontology_id, version = reference.rsplit("@", 1)
            definition = self._ontology_repository.load(ontology_id, version)
            vocabulary = self._ontology_repository.declared_vocabulary(ontology_id, version)
            declared_classes.update(vocabulary.classes)
            declared_properties.update(vocabulary.properties)
            text = self._ontology_repository.read_text(ontology_id, version)
            for match in _SUBCLASS.finditer(text):
                child = f"{definition.namespace}{match.group('child')}"
                parent = f"{definition.namespace}{match.group('parent')}"
                parents[child].add(parent)
        return (
            _ClassHierarchy({key: frozenset(value) for key, value in parents.items()}),
            declared_classes,
            declared_properties,
        )


def _validate_input_identity(
    proposals: tuple[DocumentKnowledgeProposal, ...], output_run_id: str
) -> None:
    run_ids = [proposal.proposal_run_id for proposal in proposals]
    if len(run_ids) != len(set(run_ids)):
        raise ValueError("knowledge proposal unification input run ids must be unique")
    if output_run_id in set(run_ids):
        raise ValueError("knowledge proposal unification output run id must differ from inputs")


def _validate_semantic_terms(
    proposal: DocumentKnowledgeProposal,
    declared_classes: set[str],
    declared_properties: set[str],
) -> None:
    unknown_classes = {
        entity.class_iri
        for entity in proposal.entity_proposals
        if entity.class_iri not in declared_classes
    }
    if unknown_classes:
        raise ValueError(
            "knowledge proposal input uses undeclared ontology classes: "
            f"{sorted(unknown_classes)!r}"
        )
    unknown_properties = {
        assertion.predicate
        for assertion in proposal.assertion_proposals
        if assertion.predicate not in declared_properties
    }
    if unknown_properties:
        raise ValueError(
            "knowledge proposal input uses undeclared ontology properties: "
            f"{sorted(unknown_properties)!r}"
        )


def _merge_anchors(
    proposals: tuple[DocumentKnowledgeProposal, ...],
) -> dict[str, EvidenceAnchor]:
    merged: dict[str, EvidenceAnchor] = {}
    for proposal in proposals:
        for anchor in proposal.evidence_anchors:
            existing = merged.get(anchor.id)
            if existing is not None and existing != anchor:
                raise ValueError(
                    f"conflicting evidence anchor id across proposal inputs: {anchor.id}"
                )
            merged[anchor.id] = anchor
    return dict(sorted(merged.items()))


def _resolve_entity_groups(
    proposals: tuple[DocumentKnowledgeProposal, ...],
    hierarchy: _ClassHierarchy,
) -> tuple[_ResolvedEntityGroup, ...]:
    by_label: dict[str, list[_EntitySource]] = defaultdict(list)
    for proposal in proposals:
        for entity in proposal.entity_proposals:
            by_label[_normalize_label(entity.normalized_label)].append(
                _EntitySource(proposal.proposal_run_id, entity)
            )

    groups: list[_ResolvedEntityGroup] = []
    for label in sorted(by_label):
        sources = tuple(
            sorted(
                by_label[label],
                key=lambda item: (
                    item.entity.class_iri,
                    item.proposal_run_id,
                    item.entity.id,
                ),
            )
        )
        classes = {source.entity.class_iri for source in sources}
        leaf_classes = {
            class_iri
            for class_iri in classes
            if not any(
                class_iri != other and hierarchy.is_ancestor_or_same(class_iri, other)
                for other in classes
            )
        }
        assigned: dict[str, list[_EntitySource]] = defaultdict(list)
        for source in sources:
            candidates = {
                leaf
                for leaf in leaf_classes
                if hierarchy.is_ancestor_or_same(source.entity.class_iri, leaf)
            }
            if len(candidates) == 1:
                assigned[next(iter(candidates))].append(source)
            else:
                assigned[source.entity.class_iri].append(source)

        for key in sorted(assigned):
            members = tuple(assigned[key])
            member_classes = {member.entity.class_iri for member in members}
            if not all(
                hierarchy.compatible(left, right)
                for left in member_classes
                for right in member_classes
            ):
                raise ValueError(
                    f"entity resolution produced incompatible ontology classes for label {label!r}"
                )
            groups.append(
                _ResolvedEntityGroup(
                    normalized_label=label,
                    class_iri=hierarchy.most_specific(member_classes),
                    sources=members,
                )
            )
    return tuple(groups)


def _materialize_entities(
    document_key: str,
    groups: tuple[_ResolvedEntityGroup, ...],
) -> tuple[tuple[KnowledgeEntityProposal, ...], dict[tuple[str, str], str]]:
    entities: list[KnowledgeEntityProposal] = []
    entity_ids: dict[tuple[str, str], str] = {}
    for group in groups:
        entity_id = _resolved_entity_id(document_key, group.normalized_label, group.class_iri)
        anchor_ids = tuple(
            sorted(
                {
                    anchor_id
                    for source in group.sources
                    for anchor_id in source.entity.source_anchor_ids
                }
            )
        )
        aliases = tuple(
            sorted(
                {
                    alias
                    for source in group.sources
                    for alias in (
                        *source.entity.aliases,
                        *(
                            (source.entity.normalized_label,)
                            if source.entity.normalized_label != group.normalized_label
                            else ()
                        ),
                    )
                    if alias != group.normalized_label
                }
            )
        )
        confidence = max(source.entity.confidence for source in group.sources)
        if len(group.sources) == 1:
            rationale = group.sources[0].entity.rationale
        else:
            rationale = (
                f"Document-local entity resolution merged {len(group.sources)} proposals by "
                "normalized label and compatible ontology type."
            )
        proposal_clause_ids = tuple(
            sorted(
                {
                    clause_id
                    for source in group.sources
                    for clause_id in source.entity.proposal_clause_ids
                },
                key=lambda item: item.value,
            )
        )
        entity = KnowledgeEntityProposal(
            id=entity_id,
            proposal_clause_ids=proposal_clause_ids,
            class_iri=group.class_iri,
            normalized_label=group.normalized_label,
            aliases=aliases,
            source_anchor_ids=anchor_ids,
            confidence=confidence,
            rationale=rationale,
        )
        entities.append(entity)
        for source in group.sources:
            entity_ids[(source.proposal_run_id, source.entity.id)] = entity_id
    return tuple(entities), entity_ids


def _rewrite_assertions(
    proposals: tuple[DocumentKnowledgeProposal, ...],
    entity_ids: dict[tuple[str, str], str],
) -> tuple[_RewrittenAssertion, ...]:
    rewritten: list[_RewrittenAssertion] = []
    for proposal in proposals:
        run_id = proposal.proposal_run_id
        for assertion in proposal.assertion_proposals:
            subject_id = entity_ids[(run_id, assertion.subject_id)]
            if isinstance(assertion.object, EntityAssertionObject):
                object_ = EntityAssertionObject(
                    entity_id=entity_ids[(run_id, assertion.object.entity_id)]
                )
            else:
                object_ = assertion.object
            rewritten.append(
                _RewrittenAssertion(
                    proposal_run_id=run_id,
                    assertion=assertion.model_copy(
                        update={"subject_id": subject_id, "object": object_}
                    ),
                )
            )
    return tuple(rewritten)


def _merge_assertions(
    document_key: str,
    rewritten: tuple[_RewrittenAssertion, ...],
) -> tuple[NormativeAssertionProposal, ...]:
    by_semantics: dict[str, list[_RewrittenAssertion]] = defaultdict(list)
    for item in rewritten:
        by_semantics[_assertion_semantic_key(item.assertion)].append(item)

    merged: list[NormativeAssertionProposal] = []
    for semantic_key in sorted(by_semantics):
        items = by_semantics[semantic_key]
        specific_forces = {
            item.assertion.normative_force
            for item in items
            if item.assertion.normative_force is not NormativeForce.UNSPECIFIED
        }
        force_groups: dict[NormativeForce, list[_RewrittenAssertion]] = defaultdict(list)
        if len(specific_forces) <= 1:
            resolved_force = next(iter(specific_forces), NormativeForce.UNSPECIFIED)
            force_groups[resolved_force].extend(items)
        else:
            for item in items:
                force_groups[item.assertion.normative_force].append(item)

        for normative_force in sorted(force_groups, key=lambda value: value.value):
            members = tuple(
                sorted(
                    force_groups[normative_force],
                    key=lambda item: (item.proposal_run_id, item.assertion.id),
                )
            )
            first = members[0].assertion
            evidence_anchor_ids = tuple(
                sorted(
                    {
                        anchor_id
                        for item in members
                        for anchor_id in item.assertion.evidence_anchor_ids
                    }
                )
            )
            confidence = max(item.assertion.confidence for item in members)
            if len(members) == 1:
                rationale = first.rationale
            else:
                rationale = (
                    f"Document-local proposal unification merged {len(members)} equivalent "
                    "assertions after entity resolution."
                )
            merged.append(
                NormativeAssertionProposal(
                    id=_resolved_assertion_id(
                        document_key=document_key,
                        source_clause_id=first.source_clause_id.value,
                        subject_id=first.subject_id,
                        predicate=first.predicate,
                        object_=first.object,
                        normative_force=normative_force,
                    ),
                    source_clause_id=first.source_clause_id,
                    subject_id=first.subject_id,
                    predicate=first.predicate,
                    object=first.object,
                    normative_force=normative_force,
                    evidence_anchor_ids=evidence_anchor_ids,
                    confidence=confidence,
                    rationale=rationale,
                )
            )
    return tuple(sorted(merged, key=lambda item: item.id))


def _assertion_semantic_key(assertion: NormativeAssertionProposal) -> str:
    return json.dumps(
        {
            "source_clause_id": assertion.source_clause_id.value,
            "subject_id": assertion.subject_id,
            "predicate": assertion.predicate,
            "object": assertion.object.model_dump(mode="json"),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _resolved_entity_id(document_key: str, normalized_label: str, class_iri: str) -> str:
    digest = hashlib.sha256(
        json.dumps(
            {
                "document_key": document_key,
                "normalized_label": normalized_label,
                "class_iri": class_iri,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()[:24]
    return f"entity:{document_key}:resolved:{digest}"


def _resolved_assertion_id(
    *,
    document_key: str,
    source_clause_id: str,
    subject_id: str,
    predicate: str,
    object_: EntityAssertionObject | LiteralAssertionObject,
    normative_force: NormativeForce,
) -> str:
    digest = hashlib.sha256(
        json.dumps(
            {
                "document_key": document_key,
                "source_clause_id": source_clause_id,
                "subject_id": subject_id,
                "predicate": predicate,
                "object": object_.model_dump(mode="json"),
                "normative_force": normative_force.value,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()[:24]
    return f"assertion:{document_key}:resolved:{digest}"


def _proposal_input(proposal: DocumentKnowledgeProposal) -> KnowledgeProposalInput:
    payload = json.dumps(
        proposal.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return KnowledgeProposalInput(
        proposal_run_id=proposal.proposal_run_id,
        proposal_hash=hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        proposal_provenance=proposal.proposal_provenance,
    )


def _merge_violations(
    proposals: tuple[DocumentKnowledgeProposal, ...],
) -> tuple[KnowledgeProposalViolation, ...]:
    unique = {
        json.dumps(item.model_dump(mode="json"), sort_keys=True): item
        for proposal in proposals
        for item in proposal.violations
    }
    return tuple(unique[key] for key in sorted(unique))


def _merge_failures(
    proposals: tuple[DocumentKnowledgeProposal, ...],
) -> tuple[KnowledgeProposalFailure, ...]:
    by_clause: dict[str, KnowledgeProposalFailure] = {}
    for proposal in proposals:
        for failure in proposal.failures:
            key = failure.clause_id.value
            existing = by_clause.get(key)
            if existing is not None and existing != failure:
                raise ValueError(
                    f"conflicting terminal proposal failures for source clause {key!r}"
                )
            by_clause[key] = failure
    return tuple(by_clause[key] for key in sorted(by_clause))


def _normalize_label(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip().casefold()
    return re.sub(r"\s+", " ", normalized)
