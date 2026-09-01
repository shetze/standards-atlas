"""Deterministic projection from PublicationDocument to Gemara ControlCatalog."""

from __future__ import annotations

from collections import defaultdict

from standards_atlas import __version__
from standards_atlas.adapters.gemara.mapper import (
    DEFAULT_GEMARA_VERSION,
    _children_by_parent,
    _ensure_unique_ids,
    _groups,
    _is_objective_anchor,
    _is_omitted_section,
    _is_scope_clause,
    _is_structural_group_candidate,
    _nearest_group_id,
    _nearest_objective_anchor,
    gemara_id,
)
from standards_atlas.adapters.gemara.models import (
    GemaraActor,
    GemaraAssessmentRequirement,
    GemaraControl,
    GemaraControlCatalog,
    GemaraGroup,
    GemaraMetadata,
)
from standards_atlas.application.model import PublicationDocument
from standards_atlas.domain.model import Clause, ClauseType, NormativeStatus, StatementFunction

_ASSESSMENT_FUNCTIONS = {
    StatementFunction.REQUIREMENT,
    StatementFunction.PROHIBITION,
    StatementFunction.CONFORMANCE_STATEMENT,
}
_OMITTED_TYPES = {ClauseType.TOC, ClauseType.TABLE}
_DEFAULT_APPLICABILITY_ID = "all"


class GemaraControlMapper:
    """Project qualified normative clauses into verifiable Gemara controls.

    The mapper does not infer new controls or rewrite normative prose. Objective
    clauses act as control anchors only when they own at least one explicit
    assessment clause. Normative clauses without such an anchor are emitted as
    standalone controls so that qualified requirements are not lost.
    """

    def __init__(self, *, gemara_version: str = DEFAULT_GEMARA_VERSION) -> None:
        self._gemara_version = gemara_version

    def map(self, document: PublicationDocument) -> GemaraControlCatalog:
        root_group_id = gemara_id(f"{document.key.value}-root")
        children = _children_by_parent(document.clauses)
        known_ids = {clause.id.value: clause for clause in document.clauses}
        group_clause_ids = {
            clause.id.value
            for clause in document.clauses
            if children.get(clause.id.value) and _is_structural_group_candidate(clause)
        }
        groups = _groups(
            document,
            root_group_id=root_group_id,
            group_clause_ids=group_clause_ids,
        )
        _ensure_unique_ids((group.id for group in groups), kind="group")

        objective_anchor_ids = {
            clause.id.value
            for clause in document.clauses
            if _is_control_candidate_container(clause) and _is_objective_anchor(clause)
        }
        assessment_by_anchor: dict[str, list[Clause]] = defaultdict(list)
        standalone: list[Clause] = []

        for clause in document.clauses:
            if not _is_assessment_requirement(clause):
                continue
            anchor = _nearest_objective_anchor(
                clause,
                known_ids=known_ids,
                objective_anchor_ids=objective_anchor_ids,
            )
            if anchor is None:
                standalone.append(clause)
            else:
                assessment_by_anchor[anchor.id.value].append(clause)

        controls: list[GemaraControl] = []
        for clause in document.clauses:
            requirements = tuple(assessment_by_anchor.get(clause.id.value, ()))
            if not requirements:
                continue
            controls.append(
                GemaraControl(
                    id=gemara_id(clause.id.value),
                    title=_clause_title(clause),
                    objective=clause.plain_text.strip(),
                    group=_nearest_group_id(
                        clause,
                        known_ids=known_ids,
                        group_clause_ids=group_clause_ids,
                        root_group_id=root_group_id,
                    ),
                    **{
                        "assessment-requirements": tuple(
                            _assessment_requirement(item) for item in requirements
                        )
                    },
                    state="Active",
                )
            )

        for clause in standalone:
            controls.append(
                GemaraControl(
                    id=gemara_id(f"control-{clause.id.value}"),
                    title=_clause_title(clause),
                    objective=clause.plain_text.strip(),
                    group=_nearest_group_id(
                        clause,
                        known_ids=known_ids,
                        group_clause_ids=group_clause_ids,
                        root_group_id=root_group_id,
                    ),
                    **{"assessment-requirements": (_assessment_requirement(clause),)},
                    state="Active",
                )
            )

        _ensure_unique_ids((control.id for control in controls), kind="control")
        _ensure_unique_ids(
            (
                requirement.id
                for control in controls
                for requirement in control.assessment_requirements
            ),
            kind="assessment requirement",
        )

        description = f"Gemara control projection of {document.title}."
        if document.source:
            description += f" Source: {document.source}."

        applicability_groups = (
            GemaraGroup(
                id=_DEFAULT_APPLICABILITY_ID,
                title="All applicable contexts",
                description=(
                    "Default applicability for assessment requirements that do not "
                    "carry a separately representable Standards Atlas scope context."
                ),
            ),
        )

        return GemaraControlCatalog(
            title=document.title,
            metadata=GemaraMetadata(
                id=gemara_id(f"{document.key.value}-controls"),
                type="ControlCatalog",
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
                **{"applicability-groups": applicability_groups},
            ),
            groups=tuple(groups),
            controls=tuple(controls) or None,
        )


def _is_control_candidate_container(clause: Clause) -> bool:
    return (
        clause.clause_type not in _OMITTED_TYPES
        and not _is_omitted_section(clause)
        and not _is_scope_clause(clause)
        and bool(clause.plain_text.strip())
    )


def _is_assessment_requirement(clause: Clause) -> bool:
    if not _is_control_candidate_container(clause):
        return False
    if clause.normative_status in {
        NormativeStatus.INFORMATIVE,
        NormativeStatus.NOT_APPLICABLE,
    }:
        return False
    functions = set(clause.semantic_classification.statement_functions)
    return clause.clause_type is ClauseType.REQUIREMENT or bool(functions & _ASSESSMENT_FUNCTIONS)


def _assessment_requirement(clause: Clause) -> GemaraAssessmentRequirement:
    return GemaraAssessmentRequirement(
        id=gemara_id(f"ar-{clause.id.value}"),
        text=clause.plain_text.strip(),
        applicability=(_DEFAULT_APPLICABILITY_ID,),
        state="Active",
    )


def _clause_title(clause: Clause) -> str:
    heading = (clause.heading or "").strip()
    return heading or clause.reference.as_text()
