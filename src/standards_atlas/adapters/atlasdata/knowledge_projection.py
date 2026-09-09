"""Allowlisted public projection and verified private evidence hydration."""

from __future__ import annotations

import re

from pydantic import BaseModel, TypeAdapter

from standards_atlas.domain.model.clause import Clause, ClauseEnrichments
from standards_atlas.domain.model.context_routing import ContextRouting
from standards_atlas.domain.model.knowledge_state import (
    ConfirmedAttribute,
    GeneratedAttribute,
    paths_overlap,
)
from standards_atlas.domain.model.subject_context import ClauseSubjectContext

from .knowledge_contract import (
    PRIVATE_PATHS,
    SEMANTIC_ADAPTERS,
    EvidenceBlob,
    PublishedAttribute,
    ReferenceView,
    RoleView,
    RoutingView,
    ScopeView,
    SubjectView,
)
from .knowledge_evidence import KnowledgeEvidenceStore, canonical_bytes, digest

_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/@+=%-]*\Z")
_HASH_REFERENCE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_JSON_ADAPTER = TypeAdapter(object)
_DEFAULT_ENRICHMENTS = ClauseEnrichments()


def field_value(clause: Clause, path: str) -> object:
    value: object = clause
    for field in path.split("."):
        value = getattr(value, field)
    return value


def _json(value: object) -> object:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return _JSON_ADAPTER.dump_python(value, mode="json")


def _identifier(value: str | None) -> str | None:
    if value is None:
        return None
    if _IDENTIFIER.fullmatch(value) and ".." not in value and len(value) <= 512:
        return value
    return "sha256:" + digest(value.encode())


def public_generated(item: GeneratedAttribute) -> GeneratedAttribute:
    payload = item.model_dump(mode="json")
    payload["generator"] = _identifier(item.generator)
    payload["evidence"] = [
        evidence if _HASH_REFERENCE.fullmatch(evidence) else "sha256:" + digest(evidence.encode())
        for evidence in item.evidence
    ]
    if item.decision is not None:
        decision = payload["decision"]
        for field in (
            "rule",
            "source_artifact",
            "stage",
            "prompt_id",
            "reasoning_mode_id",
            "category",
        ):
            decision[field] = _identifier(decision[field])
        decision["model_ids"] = [_identifier(value) for value in decision["model_ids"]]
        decision["label_votes"] = {
            _identifier(key): count for key, count in decision["label_votes"].items()
        }
    return GeneratedAttribute.model_validate(payload)


def public_confirmed(item: ConfirmedAttribute) -> ConfirmedAttribute:
    return item.model_copy(update={"authority": _identifier(item.authority)})


def check_public_attribute(item: PublishedAttribute) -> None:
    if item.generated is not None and public_generated(item.generated) != item.generated:
        raise ValueError("public generated provenance contains unredacted text or a local path")
    if item.confirmed is not None and public_confirmed(item.confirmed) != item.confirmed:
        raise ValueError("public confirmation contains unredacted text or a local path")


def public_value(path: str, value: object) -> object:
    if path == "enrichments.subject_context":
        subject = ClauseSubjectContext.model_validate(value)
        primary = subject.primary_subject
        return SubjectView(
            normalized_label=primary.normalized_label if primary else None,
            confidence=primary.confidence if primary else None,
            ambiguous_candidates=subject.ambiguous_candidates,
        ).model_dump(mode="json")
    if path == "enrichments.context_routing":
        routing = ContextRouting.model_validate(value)
        return RoutingView(
            scopes=tuple(
                ScopeView(
                    source_clause_id=scope.source_clause_id,
                    reaches=scope.reaches,
                    conditions=len(scope.conditions),
                    exclusions=len(scope.exclusions),
                    qualifications=len(scope.qualifications),
                )
                for scope in routing.scopes
            ),
            references=tuple(
                ReferenceView(
                    source_clause_id=reference.source_clause_id,
                    document_key=reference.target.document_key,
                    clause_id=reference.target.clause_id,
                    reference=reference.target.reference,
                    role=reference.role.value,
                )
                for reference in routing.references
            ),
        ).model_dump(mode="json")
    if path == "enrichments.semantic.role_relations":
        return RoleView(count=len(value)).model_dump(mode="json")
    return _json(value)


def canonical_value(path: str, value: object) -> object:
    if path == "enrichments.subject_context":
        return ClauseSubjectContext.model_validate(value)
    if path == "enrichments.context_routing":
        return ContextRouting.model_validate(value)
    field = path.rsplit(".", 1)[-1]
    return SEMANTIC_ADAPTERS[field].validate_python(value)


def project_attribute(
    clause: Clause,
    path: str,
    store: KnowledgeEvidenceStore,
) -> PublishedAttribute | None:
    value = field_value(clause, path)
    provenance = clause.provenance
    confirmations = [
        item
        for item in provenance.confirmed_attributes
        if path == item.path or path.startswith(item.path + ".")
    ]
    generations = [
        item
        for item in provenance.generated_attributes
        if path == item.path or path.startswith(item.path + ".")
    ]
    # A confirmed descendant cannot be rounded up to a confirmed complete context object.
    if not confirmations and any(
        paths_overlap(path, item.path) for item in provenance.confirmed_attributes
    ):
        raise ValueError(
            f"partial object confirmation requires an explicit whole-object review: {path}"
        )
    private_provenance = None
    generated, confirmed = None, None
    availability = "known"
    if confirmations:
        original = sorted(confirmations, key=lambda item: len(item.path), reverse=True)[0]
        original = original.model_copy(update={"path": path})
        confirmed = public_confirmed(original)
        origin = "confirmed"
        if confirmed != original:
            private_provenance = store.put(kind="confirmed", path=path, value=original)
    elif generations:
        original = sorted(generations, key=lambda item: len(item.path), reverse=True)[0]
        original = original.model_copy(update={"path": path})
        generated = public_generated(original)
        origin, availability = "generated", original.availability
        if generated != original:
            private_provenance = store.put(kind="generated", path=path, value=original)
    else:
        default: object = _DEFAULT_ENRICHMENTS
        for field in path.split(".")[1:]:
            default = getattr(default, field)
        if value == default and not provenance.protection(path):
            return None
        origin = "unattributed"
    private_value = None
    projected = None
    if availability == "known":
        projected = public_value(path, value)
        if path in PRIVATE_PATHS:
            private_value = store.put(kind="value", path=path, value=_json(value))
    return PublishedAttribute(
        path=path,
        origin=origin,
        availability=availability,
        value=projected,
        generated=generated,
        confirmed=confirmed,
        private_value_sha256=private_value,
        private_provenance_sha256=private_provenance,
    )


def hydrate_attribute(
    item: PublishedAttribute,
    store: KnowledgeEvidenceStore,
) -> tuple[object, GeneratedAttribute | ConfirmedAttribute | None, bool, bool]:
    """Return value, provenance, deferred-value and missing-evidence flags.

    Missing raw provenance retains the public metadata/hash references. Missing
    contextual values defer the whole attribute; never replace conditions by [].
    """
    check_public_attribute(item)
    provenance: GeneratedAttribute | ConfirmedAttribute | None = item.generated or item.confirmed
    missing = False
    if item.private_provenance_sha256:
        raw = store.get(item.private_provenance_sha256, kind=item.origin, path=item.path)
        if raw is None:
            missing = True
        else:
            if item.generated is not None:
                restored = GeneratedAttribute.model_validate(raw)
                valid = public_generated(restored) == item.generated
            else:
                restored = ConfirmedAttribute.model_validate(raw)
                valid = public_confirmed(restored) == item.confirmed
            if not valid:
                raise ValueError("private provenance disagrees with its public projection")
            provenance = restored
    if item.availability == "unknown":
        return None, provenance, False, missing
    value = item.value
    if item.private_value_sha256:
        value = store.get(item.private_value_sha256, kind="value", path=item.path)
        if value is None:
            defaults = {
                "enrichments.subject_context": ClauseSubjectContext().model_dump(mode="json"),
                "enrichments.context_routing": ContextRouting().model_dump(mode="json"),
                "enrichments.semantic.role_relations": [],
            }
            candidate = EvidenceBlob(kind="value", path=item.path, value=defaults[item.path])
            if digest(canonical_bytes(candidate)) != item.private_value_sha256:
                return None, provenance, True, True
            # An explicitly referenced empty value needs no protected evidence.
            value = candidate.value
    value = canonical_value(item.path, value)
    if public_value(item.path, value) != item.value:
        raise ValueError("private value disagrees with its public projection")
    return value, provenance, False, missing
