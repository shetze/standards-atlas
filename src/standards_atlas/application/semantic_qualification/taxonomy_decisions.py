"""Attribute-specific, provenance-backed structural decisions in shadow mode.

Rules operate only on the source-structure contract. They cannot read semantic
answers, gold labels or interpreted routing. A fixed *diagnostic* primary is not
an accepted set, a model vote, or a production early exit.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from functools import lru_cache
from importlib.resources import files
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from standards_atlas.application.context.source_structure import read_source_structure
from standards_atlas.application.model.source_structure import (
    SourceStructure,
    SourceStructureFact,
    structure_fingerprint,
)
from standards_atlas.application.schema import require_supported_schema
from standards_atlas.application.semantic_qualification.annotations import normalized_content_hash
from standards_atlas.domain.model import KnowledgeKind, StatementFunction

DecisionState = Literal["fixed", "hint", "open", "conflict"]
DecisionAttribute = Literal[
    "primary_function",
    "statement_functions",
    "primary_knowledge_kind",
    "knowledge_kinds",
    "primary_process_function",
    "process_functions",
    "applicability_present",
    "role_semantics_present",
    "role_relations",
    "role_relation_types",
]
DECISION_ATTRIBUTES: tuple[DecisionAttribute, ...] = (
    "primary_function",
    "statement_functions",
    "primary_knowledge_kind",
    "knowledge_kinds",
    "primary_process_function",
    "process_functions",
    "applicability_present",
    "role_semantics_present",
    "role_relations",
    "role_relation_types",
)
RESOURCE_DIRECTORY = "semantic/taxonomy-decisions/source-structure-v1/1.0.0"


class TaxonomyRule(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    version: str
    qualification: Literal["structural-contract", "pending-review"]
    maximum_state: Literal["fixed", "hint"]
    description: str

    @model_validator(mode="after")
    def pending_is_hint(self) -> TaxonomyRule:
        if self.qualification == "pending-review" and self.maximum_state != "hint":
            raise ValueError("unreviewed rules must remain hints")
        return self


class TaxonomyRuleProfile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    id: Literal["source-structure-v1"] = "source-structure-v1"
    version: Literal["1.0.0"] = "1.0.0"
    mode: Literal["diagnostic"] = "diagnostic"
    rules: tuple[TaxonomyRule, ...]
    exact_headings: dict[str, StatementFunction]
    catalogue_heading_pattern: str
    maximum_catalogue_distance: int = Field(ge=1, le=8)

    @model_validator(mode="after")
    def unique_rules(self) -> TaxonomyRuleProfile:
        expected = {
            "term-definition",
            "requirement-character",
            "objective-section",
            "local-heading",
            "broad-heading",
            "enclosing-section",
            "technique-entry",
            "technique-segments",
            "structural-conflict",
        }
        if {rule.id for rule in self.rules} != expected or len(self.rules) != len(expected):
            raise ValueError("incomplete or duplicate taxonomy rule profile")
        re.compile(self.catalogue_heading_pattern)
        return self

    @property
    def fingerprint(self) -> str:
        return structure_fingerprint(self.model_dump(mode="json"))


@lru_cache(maxsize=1)
def load_taxonomy_rules() -> TaxonomyRuleProfile:
    resource = files("standards_atlas.resources").joinpath(RESOURCE_DIRECTORY, "rules.yaml")
    payload = yaml.safe_load(resource.read_text(encoding="utf-8"))
    require_supported_schema("taxonomy-decision-rules", payload.get("schema_version"))
    return TaxonomyRuleProfile.model_validate(payload)


class TaxonomyRuleEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    rule_id: str
    rule_version: str
    qualification: Literal["structural-contract", "pending-review"]
    candidate: str | None = None
    source_fingerprints: tuple[str, ...] = Field(min_length=1)
    reason: str
    # Direct local observations outrank general inherited headings.
    specificity: Literal["local", "enclosing", "catalogue"] = "local"
    fixes_attribute: bool = False

    @model_validator(mode="after")
    def no_unqualified_fix(self) -> TaxonomyRuleEvidence:
        if self.fixes_attribute and self.qualification != "structural-contract":
            raise ValueError("unreviewed evidence cannot fix an attribute")
        return self


class AttributeDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    attribute: DecisionAttribute
    state: DecisionState
    value: str | None = None
    candidates: tuple[str, ...] = ()
    evidence: tuple[TaxonomyRuleEvidence, ...] = ()

    @model_validator(mode="after")
    def explicit_value(self) -> AttributeDecision:
        if (self.state == "fixed") != (self.value is not None):
            raise ValueError("only a fixed attribute carries a decided value")
        if self.state == "open" and (self.evidence or self.candidates):
            raise ValueError("open attributes have no structural assessment")
        if self.state != "open" and not self.evidence:
            raise ValueError("assessed attributes require source evidence")
        if self.state == "fixed" and self.value not in self.candidates:
            raise ValueError("fixed value must be a supported candidate")
        if self.state == "fixed" and not any(item.fixes_attribute for item in self.evidence):
            raise ValueError("fixed attribute needs a source-backed qualifying rule")
        if self.attribute == "primary_function":
            for value in self.candidates:
                StatementFunction(value)
        if self.attribute == "primary_knowledge_kind":
            for value in self.candidates:
                KnowledgeKind(value)
        return self


class ClauseDecisionPlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    diagnostic_only: Literal[True] = True
    rules_id: str
    rules_version: str
    rules_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source: SourceStructure
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    decisions: tuple[AttributeDecision, ...]
    warnings: tuple[str, ...] = ()

    @model_validator(mode="after")
    def complete_attributes(self) -> ClauseDecisionPlan:
        if tuple(item.attribute for item in self.decisions) != DECISION_ATTRIBUTES:
            raise ValueError("decision plan must account for each supported attribute once")
        if self.source_sha256 != self.source.fingerprint:
            raise ValueError("source structure fingerprint mismatch")
        known = {fact.fingerprint: fact for fact in self.source.facts}
        if any(
            not set(evidence.source_fingerprints).issubset(known)
            for decision in self.decisions
            for evidence in decision.evidence
        ):
            raise ValueError("rule evidence references absent source facts")
        for decision in self.decisions:
            for item in decision.evidence:
                if item.fixes_attribute and any(
                    known[key].origin != "confirmed" for key in item.source_fingerprints
                ):
                    raise ValueError("fixed evidence requires confirmed source facts")
        return self

    @property
    def fingerprint(self) -> str:
        return structure_fingerprint(self.model_dump(mode="json"))

    def decision(self, attribute: DecisionAttribute) -> AttributeDecision:
        return next(item for item in self.decisions if item.attribute == attribute)


def derive_clause_decision_plan(
    context: Mapping[str, Any],
    *,
    text: str = "",
    content_hash: str | None = None,
) -> ClauseDecisionPlan:
    """Derive a reproducible plan; no I/O other than the packaged rule definition."""
    actual_hash = normalized_content_hash(text)
    if content_hash is not None and content_hash != actual_hash:
        raise ValueError("content hash does not match the normalized clause text")
    source = read_source_structure(context, text=text, content_hash=actual_hash)
    profile = load_taxonomy_rules()
    rules = {rule.id: rule for rule in profile.rules}
    facts = {fact.field: fact for fact in source.facts if fact.distance == 0}
    ancestors = sorted(
        (fact for fact in source.facts if fact.field == "ancestor_heading"),
        key=lambda fact: fact.distance,
    )
    evidences: dict[str, list[TaxonomyRuleEvidence]] = {key: [] for key in DECISION_ATTRIBUTES}
    warnings = []
    if source.origin == "legacy-context":
        warnings.append("legacy_structure_has_no_independent_authority")
    if any(fact.origin in {"excluded", "unavailable"} for fact in source.facts):
        warnings.append("some_source_facts_are_excluded_or_unavailable")

    def observe(
        rule_id: str,
        candidate: str | None,
        used: list[SourceStructureFact],
        reason: str,
        *,
        attribute: str = "primary_function",
        specificity: str = "local",
        fixed: bool = False,
    ) -> None:
        rule = rules[rule_id]
        evidences[attribute].append(
            TaxonomyRuleEvidence(
                rule_id=rule.id,
                rule_version=rule.version,
                qualification=rule.qualification,
                candidate=candidate,
                source_fingerprints=tuple(fact.fingerprint for fact in used),
                reason=reason,
                specificity=specificity,
                fixes_attribute=(
                    fixed
                    and rule.maximum_state == "fixed"
                    and bool(used)
                    and all(fact.origin == "confirmed" for fact in used)
                ),
            )
        )

    def value(field: str) -> Any:
        fact = facts.get(field)
        return fact.value if fact is not None else None

    heading = _heading(value("heading"))
    clause_type = value("clause_type")
    local_function = profile.exact_headings.get(heading)
    nearest = ancestors[0] if ancestors else None
    nearest_heading = _heading(nearest.value) if nearest is not None else ""
    scope_heading = nearest if nearest_heading in {"scope", "field of application"} else None
    if scope_heading is not None or heading in {"scope", "field of application"}:
        warnings.append("scope_context_is_not_explicit_applicability_presence")

    if clause_type == "term":
        # Definition is a communicative function, never a default knowledge kind.
        observe(
            "term-definition",
            "definition",
            [facts["clause_type"]],
            "Term entry determines only the primary definition function.",
            fixed=True,
        )
    elif clause_type == "requirement":
        prohibitive = bool(re.search(r"\b(?:shall|must)\s+not\b", text, re.I))
        observe(
            "requirement-character",
            "prohibition" if prohibitive else "requirement",
            [facts["clause_type"]],
            "Requirement character needs granularity/mixed-content review; no set inferred.",
        )
    elif clause_type == "objective":
        used = [facts["clause_type"]]
        if heading == "objectives" or heading == "objective":
            used.append(facts["heading"])
        elif nearest_heading in {"objective", "objectives"}:
            used.append(nearest)
        observe(
            "objective-section",
            "objective",
            used,
            "Objective source marking is a candidate, not a qualified semantic primary.",
        )

    if local_function:
        observe(
            "local-heading",
            local_function.value,
            [facts["heading"]],
            "Exact local section role; pending independent semantic review.",
        )
    elif heading:
        # Avoid classifying 'Requirements on objectives' as a pure objective.
        if re.match(r"^requirements?\b", heading):
            broad = StatementFunction.REQUIREMENT
        else:
            broad = next(
                (
                    function
                    for word, function in sorted(profile.exact_headings.items())
                    if re.search(r"\b" + re.escape(word) + r"\b", heading)
                ),
                None,
            )
        if broad is not None:
            observe(
                "broad-heading",
                broad.value,
                [facts["heading"]],
                "Heading mentions a subject/function; keyword is not a predecision.",
            )

    if nearest is not None and nearest_heading in profile.exact_headings:
        observe(
            "enclosing-section",
            profile.exact_headings[nearest_heading].value,
            [nearest],
            "Immediate enclosing section provides context, not unconditional inheritance.",
            specificity="enclosing",
        )

    # Strong contradictory local observations cannot be silently overwritten.
    expected = {"term": "definition", "requirement": "requirement", "objective": "objective"}
    if local_function and clause_type in expected and local_function.value != expected[clause_type]:
        observe(
            "structural-conflict",
            None,
            [facts["clause_type"], facts["heading"]],
            "Direct type and exact local section role disagree.",
        )
    work_products = heading in {"work products", "work product"}
    inherited_work_products = nearest_heading in {"work products", "work product"}
    if clause_type == "objective" and (work_products or inherited_work_products):
        observe(
            "structural-conflict",
            None,
            [facts["clause_type"], facts["heading"] if work_products else nearest],
            "Objective marking conflicts with the local/immediate Work products section.",
        )

    sections = value("semantic_sections")
    sections = sections if isinstance(sections, list) else []
    roles, valid_sections = _segment_roles(sections, text)
    if sections and not valid_sections:
        warnings.append("semantic_section_offsets_or_labels_invalid")
    if valid_sections and {"aim", "description"}.issubset(roles):
        catalogue = next(
            (
                fact
                for fact in ancestors
                if fact.distance <= profile.maximum_catalogue_distance
                and re.search(profile.catalogue_heading_pattern, _heading(fact.value), re.I)
            ),
            None,
        )
        boundary = value("node_kind") == "leaf" and value("child_clause_ids") == []
        if catalogue is not None and boundary:
            observe(
                "technique-entry",
                "technique_or_measure",
                [
                    facts["semantic_sections"],
                    catalogue,
                    facts["node_kind"],
                    facts["child_clause_ids"],
                ],
                "Catalogue + leaf boundary + valid Aim/Description; rule awaits review.",
                attribute="primary_knowledge_kind",
                specificity="catalogue",
            )
        else:
            observe(
                "technique-segments",
                "technique_or_measure",
                [facts["semantic_sections"]],
                "Aim/Description alone cannot confirm a technique catalogue entry.",
                attribute="primary_knowledge_kind",
            )
        warnings.append("technique_usability_does_not_decide_normative_applicability")

    # Historical heading aliases are accepted only at the reader boundary. A
    # contradictory pair is reported rather than letting a legacy alias win.
    if "heading" in context and "title" in context and _heading(context["title"]) != heading:
        warnings.append("conflicting_legacy_title_ignored")

    decisions = tuple(
        _resolve(attribute, evidences[attribute]) for attribute in DECISION_ATTRIBUTES
    )
    return ClauseDecisionPlan(
        rules_id=profile.id,
        rules_version=profile.version,
        rules_sha256=profile.fingerprint,
        source=source,
        source_sha256=source.fingerprint,
        decisions=decisions,
        warnings=tuple(sorted(set(warnings))),
    )


def _resolve(attribute: DecisionAttribute, items: list[TaxonomyRuleEvidence]) -> AttributeDecision:
    candidates = tuple(sorted({item.candidate for item in items if item.candidate is not None}))
    fixed = {item.candidate for item in items if item.fixes_attribute}
    conflict = any(item.rule_id == "structural-conflict" for item in items) or len(fixed) > 1
    state: DecisionState = (
        "conflict" if conflict else "fixed" if fixed else "hint" if items else "open"
    )
    return AttributeDecision(
        attribute=attribute,
        state=state,
        value=next(iter(fixed)) if state == "fixed" else None,
        candidates=candidates,
        evidence=tuple(items),
    )


def _heading(value: object) -> str:
    return " ".join(value.split()).strip().rstrip(":").casefold() if isinstance(value, str) else ""


def _segment_roles(sections: list, text: str) -> tuple[set[str], bool]:
    roles: set[str] = set()
    end = 0
    for section in sections:
        if not isinstance(section, dict):
            return set(), False
        start, stop = section.get("start_offset"), section.get("end_offset")
        label = section.get("label")
        if (
            not isinstance(start, int)
            or isinstance(start, bool)
            or not isinstance(stop, int)
            or isinstance(stop, bool)
            or not (end <= start < stop <= len(text))
            or not isinstance(label, str)
            or not label.strip()
        ):
            return set(), False
        segment = text[start:stop].lstrip()
        if not re.match(re.escape(label.strip()) + r"\s*:", segment, re.I):
            return set(), False
        if section.get("role") in {"aim", "description"}:
            if _heading(label) != section["role"]:
                return set(), False
            roles.add(section["role"])
        end = stop
    return roles, bool(sections)
