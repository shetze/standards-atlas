"""Deterministic semantic projection from PublicationDocument to Gemara GuidanceCatalog."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable

from standards_atlas import __version__
from standards_atlas.adapters.gemara.models import (
    GemaraActor,
    GemaraGroup,
    GemaraGuidanceCatalog,
    GemaraGuideline,
    GemaraMappingReference,
    GemaraMetadata,
    GemaraRationale,
    GemaraStatement,
)
from standards_atlas.application.model import PublicationDocument
from standards_atlas.domain.model import (
    AnnotationType,
    AnnotationVisibility,
    ApplicabilityFunction,
    Clause,
    ClauseAnnotation,
    ClauseType,
    ProcessFunction,
    RelationScope,
    StatementFunction,
)
from standards_atlas.domain.model.structural_profile import CanonicalDocumentSection

DEFAULT_GEMARA_VERSION = "v0.17.0-dev"

_OMITTED_SECTIONS = {
    CanonicalDocumentSection.FRONT_MATTER,
    CanonicalDocumentSection.REFERENCES,
    CanonicalDocumentSection.BIBLIOGRAPHY,
    CanonicalDocumentSection.BACK_MATTER,
}
_OMITTED_TYPES = {ClauseType.TOC, ClauseType.TABLE}
_STATEMENT_FUNCTIONS = {
    StatementFunction.REQUIREMENT,
    StatementFunction.PROHIBITION,
    StatementFunction.CONFORMANCE_STATEMENT,
    StatementFunction.PREREQUISITE,
    StatementFunction.ASSUMPTION,
}
_RECOMMENDATION_FUNCTIONS = {
    StatementFunction.RECOMMENDATION,
    StatementFunction.GUIDELINE,
}
_RATIONALE_FUNCTIONS = {
    StatementFunction.RATIONALE,
    StatementFunction.EXPLANATION,
}
_POSITIVE_APPLICABILITY_FUNCTIONS = {
    ApplicabilityFunction.SCOPE_DEFINITION,
    ApplicabilityFunction.INCLUSION,
    ApplicabilityFunction.APPLICABILITY_CONDITION,
}


class GemaraGuidanceMapper:
    """Build a Gemara GuidanceCatalog without invoking interpretation or LLMs.

    Semantic classifications already present in the canonical knowledge state are
    projected onto Gemara fields. Objective clauses become aggregation anchors;
    compatible descendants are folded into statements, recommendations, rationale,
    or applicability instead of being emitted as duplicate standalone guidelines.
    Clauses without a usable semantic anchor retain the conservative one-clause/
    one-guideline fallback used by the MVP exporter.
    """

    def __init__(self, *, gemara_version: str = DEFAULT_GEMARA_VERSION) -> None:
        self._gemara_version = gemara_version

    def map(self, document: PublicationDocument) -> GemaraGuidanceCatalog:
        root_group_id = gemara_id(f"{document.key.value}-root")
        children = _children_by_parent(document.clauses)
        known_ids = {clause.id.value: clause for clause in document.clauses}
        annotations = _annotations_by_clause(document.annotations)
        group_clause_ids = {
            clause.id.value
            for clause in document.clauses
            if children.get(clause.id.value) and _is_structural_group_candidate(clause)
        }

        groups = _groups(document, root_group_id=root_group_id, group_clause_ids=group_clause_ids)
        _ensure_unique_ids((group.id for group in groups), kind="group")

        objective_anchor_ids = {
            clause.id.value
            for clause in document.clauses
            if _is_exportable_guideline(clause) and _is_objective_anchor(clause)
        }
        projection_targets: dict[str, list[Clause]] = defaultdict(list)
        standalone: list[Clause] = []
        for clause in document.clauses:
            if not _is_exportable_guideline(clause) or clause.id.value in objective_anchor_ids:
                continue
            anchor = _nearest_objective_anchor(
                clause,
                known_ids=known_ids,
                objective_anchor_ids=objective_anchor_ids,
            )
            if anchor is not None and _can_fold_into_anchor(clause):
                projection_targets[anchor.id.value].append(clause)
            else:
                standalone.append(clause)

        owner_guideline_by_clause = _owner_guideline_by_clause(
            document.clauses,
            objective_anchor_ids=objective_anchor_ids,
            projection_targets=projection_targets,
            standalone=standalone,
        )
        see_also_by_guideline = _internal_see_also(
            document.clauses, owner_guideline_by_clause=owner_guideline_by_clause
        )
        mapping_references = _external_mapping_references(document.clauses)

        applicability_groups: list[GemaraGroup] = []
        guidelines: list[GemaraGuideline] = []
        for clause in document.clauses:
            if clause.id.value not in objective_anchor_ids:
                continue
            folded = tuple(projection_targets.get(clause.id.value, ()))
            guideline, new_applicability_groups = _semantic_guideline(
                clause,
                folded=folded,
                annotations=annotations,
                group_id=_nearest_group_id(
                    clause,
                    known_ids=known_ids,
                    group_clause_ids=group_clause_ids,
                    root_group_id=root_group_id,
                ),
            )
            guidelines.append(guideline)
            applicability_groups.extend(new_applicability_groups)

        folded_ids = {item.id.value for values in projection_targets.values() for item in values}
        for clause in document.clauses:
            if (
                clause.id.value in objective_anchor_ids
                or clause.id.value in folded_ids
                or clause not in standalone
            ):
                continue
            guidelines.append(
                _standalone_guideline(
                    clause,
                    annotations=annotations,
                    group_id=_nearest_group_id(
                        clause,
                        known_ids=known_ids,
                        group_clause_ids=group_clause_ids,
                        root_group_id=root_group_id,
                    ),
                )
            )

        guidelines = [
            guideline.model_copy(
                update={"see_also": see_also_by_guideline.get(guideline.id) or None}
            )
            for guideline in guidelines
        ]

        _ensure_unique_ids((guideline.id for guideline in guidelines), kind="guideline")
        _ensure_unique_ids((group.id for group in applicability_groups), kind="applicability group")

        description = f"Gemara guidance projection of {document.title}."
        if document.source:
            description += f" Source: {document.source}."

        return GemaraGuidanceCatalog(
            title=document.title,
            metadata=GemaraMetadata(
                id=gemara_id(document.key.value),
                **{"gemara-version": self._gemara_version},
                version=(
                    document.version or (str(document.year) if document.year is not None else None)
                ),
                description=description,
                author=GemaraActor(
                    id="standards-atlas",
                    name="Standards Atlas",
                    type="Software",
                    version=__version__,
                ),
                **{
                    "mapping-references": mapping_references or None,
                    "applicability-groups": tuple(applicability_groups) or None,
                },
            ),
            type="Standard",
            front_matter=_front_matter(document.clauses),
            groups=tuple(groups),
            guidelines=tuple(guidelines) or None,
        )


def gemara_id(value: str) -> str:
    """Return a stable, conservative Gemara identifier."""
    normalized = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    if not normalized:
        raise ValueError(f"Cannot derive Gemara id from {value!r}.")
    return normalized


def _owner_guideline_by_clause(
    clauses: tuple[Clause, ...],
    *,
    objective_anchor_ids: set[str],
    projection_targets: dict[str, list[Clause]],
    standalone: list[Clause],
) -> dict[str, str]:
    """Map projected clause ids to their owning Gemara guideline id."""
    owners = {clause_id: gemara_id(clause_id) for clause_id in objective_anchor_ids}
    for anchor_id, folded in projection_targets.items():
        owner = gemara_id(anchor_id)
        for clause in folded:
            owners[clause.id.value] = owner
    for clause in standalone:
        owners[clause.id.value] = gemara_id(clause.id.value)
    return owners


def _internal_see_also(
    clauses: tuple[Clause, ...], *, owner_guideline_by_clause: dict[str, str]
) -> dict[str, tuple[str, ...]]:
    """Project resolved internal clause relations to Gemara guideline see-also links."""
    related: dict[str, list[str]] = defaultdict(list)
    for clause in clauses:
        source_owner = owner_guideline_by_clause.get(clause.id.value)
        if source_owner is None:
            continue
        for relation in clause.reference_relations:
            if relation.scope is not RelationScope.INTERNAL or relation.target_clause_id is None:
                continue
            target_owner = owner_guideline_by_clause.get(relation.target_clause_id)
            if target_owner is None or target_owner == source_owner:
                continue
            if target_owner not in related[source_owner]:
                related[source_owner].append(target_owner)
    return {key: tuple(value) for key, value in related.items()}


def _external_mapping_references(clauses: tuple[Clause, ...]) -> tuple[GemaraMappingReference, ...]:
    """Register versioned external document targets in Gemara metadata.

    Gemara requires every MappingReference to carry a version. Standards Atlas therefore
    emits one only when the resolved source evidence contains a deterministic four-digit
    version/year. Exact clause-to-clause provenance is retained in the traceability sidecar.
    """
    refs: dict[tuple[str, str], GemaraMappingReference] = {}
    for clause in clauses:
        for relation in clause.reference_relations:
            if relation.scope is not RelationScope.EXTERNAL or not relation.target_document_key:
                continue
            version = _external_version(relation.display_text)
            if version is None:
                continue
            key = (relation.target_document_key, version)
            refs.setdefault(
                key,
                GemaraMappingReference(
                    id=gemara_id(f"ref-{relation.target_document_key}-{version}"),
                    title=relation.target_document_key,
                    version=version,
                    description=(
                        "External standard referenced from this guidance catalog: "
                        f"{relation.target_document_key}."
                    ),
                ),
            )
    ordered = tuple(refs[key] for key in sorted(refs))
    _ensure_unique_ids((item.id for item in ordered), kind="mapping reference")
    return ordered


def _external_version(display_text: str | None) -> str | None:
    if not display_text:
        return None
    match = re.search(r"(?<!\d)((?:19|20)\d{2})(?!\d)", display_text)
    return match.group(1) if match else None


def _groups(
    document: PublicationDocument, *, root_group_id: str, group_clause_ids: set[str]
) -> list[GemaraGroup]:
    groups = [
        GemaraGroup(
            id=root_group_id,
            title=document.title,
            description=f"Guidance projected from {document.title}.",
        )
    ]
    for clause in document.clauses:
        if clause.id.value not in group_clause_ids:
            continue
        title = _clause_title(clause)
        groups.append(
            GemaraGroup(
                id=gemara_id(clause.id.value),
                title=title,
                description=f"Section {clause.reference.as_text()}: {title}",
            )
        )
    return groups


def _semantic_guideline(
    anchor: Clause,
    *,
    folded: tuple[Clause, ...],
    annotations: dict[str, tuple[ClauseAnnotation, ...]],
    group_id: str,
) -> tuple[GemaraGuideline, tuple[GemaraGroup, ...]]:
    statements: list[GemaraStatement] = []
    recommendations: list[str] = []
    rationale_parts = list(_public_rationale_annotations(anchor, annotations))
    applicability: list[str] = []
    applicability_groups: list[GemaraGroup] = []

    for clause in folded:
        functions = set(clause.semantic_classification.statement_functions)
        if functions & _STATEMENT_FUNCTIONS:
            statements.append(
                GemaraStatement(
                    id=gemara_id(clause.id.value),
                    title=_optional_heading(clause),
                    text=clause.plain_text.strip(),
                )
            )
        elif functions & _RECOMMENDATION_FUNCTIONS:
            recommendations.append(clause.plain_text.strip())
        elif functions & _RATIONALE_FUNCTIONS:
            rationale_parts.append(clause.plain_text.strip())
        elif _is_positive_applicability(clause):
            app_group = GemaraGroup(
                id=gemara_id(f"app-{clause.id.value}"),
                title=_clause_title(clause),
                description=clause.plain_text.strip(),
            )
            applicability_groups.append(app_group)
            applicability.append(app_group.id)

    rationale = _rationale(anchor.plain_text.strip(), rationale_parts)
    return (
        GemaraGuideline(
            id=gemara_id(anchor.id.value),
            title=_clause_title(anchor),
            objective=anchor.plain_text.strip(),
            group=group_id,
            recommendations=tuple(recommendations) or None,
            applicability=tuple(applicability) or None,
            rationale=rationale,
            statements=tuple(statements) or None,
            state="Active",
        ),
        tuple(applicability_groups),
    )


def _standalone_guideline(
    clause: Clause,
    *,
    annotations: dict[str, tuple[ClauseAnnotation, ...]],
    group_id: str,
) -> GemaraGuideline:
    rationale = _rationale(
        clause.plain_text.strip(), list(_public_rationale_annotations(clause, annotations))
    )
    return GemaraGuideline(
        id=gemara_id(clause.id.value),
        title=_clause_title(clause),
        objective=clause.plain_text.strip(),
        group=group_id,
        rationale=rationale,
        state="Active",
    )


def _rationale(objective: str, parts: list[str]) -> GemaraRationale | None:
    cleaned = tuple(dict.fromkeys(part.strip() for part in parts if part.strip()))
    if not cleaned:
        return None
    return GemaraRationale(importance="\n\n".join(cleaned), goals=(objective,))


def _public_rationale_annotations(
    clause: Clause, annotations: dict[str, tuple[ClauseAnnotation, ...]]
) -> tuple[str, ...]:
    return tuple(
        annotation.content
        for annotation in annotations.get(clause.id.value, ())
        if annotation.visibility is AnnotationVisibility.PUBLIC
        and annotation.annotation_type in {AnnotationType.RATIONALE, AnnotationType.EXPLANATION}
    )


def _annotations_by_clause(
    annotations: tuple[ClauseAnnotation, ...],
) -> dict[str, tuple[ClauseAnnotation, ...]]:
    grouped: dict[str, list[ClauseAnnotation]] = defaultdict(list)
    for annotation in annotations:
        grouped[annotation.clause_id.value].append(annotation)
    return {key: tuple(value) for key, value in grouped.items()}


def _children_by_parent(clauses: tuple[Clause, ...]) -> dict[str, tuple[Clause, ...]]:
    children: dict[str, list[Clause]] = defaultdict(list)
    for clause in clauses:
        if clause.parent_id is not None:
            children[clause.parent_id.value].append(clause)
    return {key: tuple(value) for key, value in children.items()}


def _is_structural_group_candidate(clause: Clause) -> bool:
    return (
        clause.clause_type not in _OMITTED_TYPES
        and not _is_omitted_section(clause)
        and not _is_scope_clause(clause)
    )


def _is_exportable_guideline(clause: Clause) -> bool:
    if (
        clause.clause_type in _OMITTED_TYPES
        or _is_omitted_section(clause)
        or _is_scope_clause(clause)
    ):
        return False
    return bool(clause.plain_text.strip())


def _is_objective_anchor(clause: Clause) -> bool:
    semantic = clause.semantic_classification
    return (
        clause.clause_type is ClauseType.OBJECTIVE
        or StatementFunction.OBJECTIVE in semantic.statement_functions
        or ProcessFunction.OBJECTIVE in semantic.process_functions
    )


def _can_fold_into_anchor(clause: Clause) -> bool:
    functions = set(clause.semantic_classification.statement_functions)
    return bool(
        functions & (_STATEMENT_FUNCTIONS | _RECOMMENDATION_FUNCTIONS | _RATIONALE_FUNCTIONS)
        or _is_positive_applicability(clause)
    )


def _is_positive_applicability(clause: Clause) -> bool:
    semantic = clause.semantic_classification
    return (
        semantic.applicability_present
        and bool(set(semantic.applicability_functions) & _POSITIVE_APPLICABILITY_FUNCTIONS)
        and ApplicabilityFunction.EXCLUSION not in semantic.applicability_functions
    )


def _is_scope_clause(clause: Clause) -> bool:
    return clause.clause_type is ClauseType.SCOPE or (
        clause.structural_profile is not None
        and clause.structural_profile.canonical_section is CanonicalDocumentSection.SCOPE
    )


def _is_omitted_section(clause: Clause) -> bool:
    profile = clause.structural_profile
    return profile is not None and profile.canonical_section in _OMITTED_SECTIONS


def _nearest_objective_anchor(
    clause: Clause,
    *,
    known_ids: dict[str, Clause],
    objective_anchor_ids: set[str],
) -> Clause | None:
    parent_id = clause.parent_id
    visited: set[str] = set()
    while parent_id is not None and parent_id.value not in visited:
        visited.add(parent_id.value)
        parent = known_ids.get(parent_id.value)
        if parent is None:
            break
        if parent.id.value in objective_anchor_ids:
            return parent
        parent_id = parent.parent_id
    return None


def _nearest_group_id(
    clause: Clause,
    *,
    known_ids: dict[str, Clause],
    group_clause_ids: set[str],
    root_group_id: str,
) -> str:
    parent_id = clause.parent_id
    visited: set[str] = set()
    while parent_id is not None and parent_id.value not in visited:
        visited.add(parent_id.value)
        if parent_id.value in group_clause_ids:
            return gemara_id(parent_id.value)
        parent = known_ids.get(parent_id.value)
        if parent is None:
            break
        parent_id = parent.parent_id
    return root_group_id


def _front_matter(clauses: tuple[Clause, ...]) -> str | None:
    scope = [
        clause.plain_text.strip()
        for clause in clauses
        if clause.plain_text.strip() and _is_scope_clause(clause)
    ]
    return "\n\n".join(scope) or None


def _clause_title(clause: Clause) -> str:
    return _optional_heading(clause) or clause.reference.as_text()


def _optional_heading(clause: Clause) -> str | None:
    heading = (clause.heading or "").strip()
    return heading or None


def _ensure_unique_ids(values: Iterable[str], *, kind: str) -> None:
    seen: set[str] = set()
    for value in values:
        if value in seen:
            raise ValueError(f"Gemara {kind} id collision after normalization: {value!r}.")
        seen.add(value)
