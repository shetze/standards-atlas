"""Replay package, proposal and review invariants without trusting derived reports."""

from __future__ import annotations

import json
from collections import Counter

from jsonschema import Draft202012Validator

from standards_atlas.application.model.source_structure import structure_fingerprint
from standards_atlas.application.schema import require_supported_schema
from standards_atlas.application.semantic_qualification.annotations import normalized_content_hash
from standards_atlas.application.semantic_qualification.partial_observations import (
    PRIMARY_SET_FIELDS,
)
from standards_atlas.application.semantic_qualification.semantic_readiness import _value_key

from .model import (
    EvidenceQuote,
    ReviewPackage,
    ReviewState,
    predicate_data,
    validate_predicate,
)
from .sources import clause_type, fingerprint, population_hash, resolve_evidence, select_holdout


def seal(cls, data: dict, field: str):
    value = cls.model_validate({**data, field: "0" * 64})
    return cls.model_validate({**value.model_dump(mode="json"), field: fingerprint(value, field)})


def same_predicate(a, b) -> bool:
    x, y = predicate_data(a), predicate_data(b)
    return x.keys() == y.keys() and all(_value_key(x[k]) == _value_key(y[k]) for k in x)


def verify_package(package: ReviewPackage) -> None:
    require_supported_schema("partial-review-package", package.schema_version)
    require_supported_schema("partial-review-profile", package.profile.schema_version)
    if fingerprint(package, "package_sha256") != package.package_sha256:
        raise ValueError("review package fingerprint mismatch")
    if structure_fingerprint(package.rules) != package.rules_sha256:
        raise ValueError("review rules fingerprint mismatch")
    rule_names = {
        "tasks/semantic-attribute-observation/1.0.0/schema.json",
        "tasks/semantic-attribute-observation/1.0.0/task.yaml",
        "profiles/functional-safety/1.0.0/profile.yaml",
        "review/partial-semantic-reference-v1/guidelines.md",
    }
    if set(package.rules) not in (rule_names, rule_names | {"project-review-instructions"}):
        raise ValueError("review rule inventory differs from the closed contract")
    Draft202012Validator.check_schema(package.output_schema)
    schema_key = "tasks/semantic-attribute-observation/1.0.0/schema.json"
    if (
        schema_key not in package.rules
        or json.loads(package.rules[schema_key]) != package.output_schema
    ):
        raise ValueError("review schema differs from the frozen annotation rules")
    if population_hash(package.population) != package.population_sha256:
        raise ValueError("review source population fingerprint mismatch")
    by_id = {s.example_id: s for s in package.population}
    if len(by_id) != len(package.population):
        raise ValueError("duplicate review source identity")
    for coordinates in (
        [(s.document_key, s.clause_id) for s in package.population],
        [(s.document_key, s.reference) for s in package.population],
    ):
        if len(set(coordinates)) != len(coordinates):
            raise ValueError("duplicate review source coordinates")
    for source in package.population:
        if (
            normalized_content_hash(source.text) != source.content_hash
            or fingerprint(source, "source_sha256") != source.source_sha256
            or source.structure.fingerprint != source.context_sha256
            or (source.document_key, source.clause_id, source.reference, source.content_hash)
            != (
                source.structure.document_key,
                source.structure.clause_id,
                source.structure.reference,
                source.structure.content_hash,
            )
        ):
            raise ValueError(f"invalid review source binding: {source.example_id}")
    cases = {c.example_id: c for c in package.cases}
    if len(cases) != len(package.cases) or not cases.keys() <= by_id.keys():
        raise ValueError("review cases require unique bound source identities")
    for case in package.cases:
        if case.attributes != package.profile.attributes:
            raise ValueError("review case attributes differ from frozen profile")
    for values in (
        package.known_development_ids,
        package.excluded_holdout_ids,
        package.existing_holdout_ids,
    ):
        if len(values) != len(set(values)) or not set(values) <= by_id.keys():
            raise ValueError("invalid frozen membership/exclusion identities")
    dev = {c.example_id for c in package.cases if c.split == "development"}
    holdout = {c.example_id for c in package.cases if c.split == "holdout"}
    if not dev or dev != set(package.known_development_ids):
        raise ValueError("known Development membership must be preserved completely")
    if not dev <= set(package.excluded_holdout_ids):
        raise ValueError("Development must be excluded from holdout")
    expected = select_holdout(
        package.population,
        package.excluded_holdout_ids,
        package.existing_holdout_ids,
        package.holdout_size,
        package.seed,
    )
    if holdout != set(expected):
        raise ValueError("holdout differs from frozen source-only selection")
    for rule in package.profile.coverage:
        if rule.predicate is not None:
            validate_predicate(rule.attribute, rule.predicate, package.output_schema)


def verify_state(package: ReviewPackage, state: ReviewState) -> None:
    require_supported_schema("partial-review-state", state.schema_version)
    if (
        state.package_sha256 != package.package_sha256
        or fingerprint(state, "state_sha256") != state.state_sha256
    ):
        raise ValueError("review state/package fingerprint mismatch")
    events = sorted((*state.proposals, *state.decisions), key=lambda e: e.revision)
    if [e.revision for e in events] != list(range(1, state.revision + 1)):
        raise ValueError("review revisions must be unique and contiguous")
    cases = {c.example_id: c for c in package.cases}
    sources = {s.example_id: s for s in package.population}
    proposals, previous = {}, {}
    for event in events:
        case = cases.get(event.example_id)
        if case is None or event.attribute not in case.attributes:
            raise ValueError("review event is outside the frozen task selection")
        if event.predicate is not None:
            validate_predicate(event.attribute, event.predicate, package.output_schema)
        key = (event.example_id, event.attribute)
        if hasattr(event, "producer_kind"):
            if fingerprint(event, "proposal_sha256") != event.proposal_sha256:
                raise ValueError("proposal fingerprint mismatch")
            for span in event.evidence:
                quote = EvidenceQuote.model_validate(span.model_dump(exclude={"start", "end"}))
                if resolve_evidence(sources[event.example_id], quote) != span:
                    raise ValueError("evidence offsets do not match frozen quote")
            proposals[event.proposal_sha256] = event
            continue
        if fingerprint(event, "decision_sha256") != event.decision_sha256:
            raise ValueError("decision fingerprint mismatch")
        prior = previous.get(key)
        if event.supersedes != (prior.decision_sha256 if prior else None):
            raise ValueError("review must explicitly supersede the preceding decision")
        if event.proposal_sha256:
            proposal = proposals.get(event.proposal_sha256)
            if proposal is None or (proposal.example_id, proposal.attribute) != key:
                raise ValueError("review references missing, future or unrelated proposal")
            if event.status == "confirmed" and not same_predicate(
                event.predicate, proposal.predicate
            ):
                raise ValueError("confirmation must retain the exact reviewed proposal")
        previous[key] = event


def active_decisions(state: ReviewState) -> dict:
    return {
        (d.example_id, d.attribute): d for d in sorted(state.decisions, key=lambda d: d.revision)
    }


def confirmed_decisions(state: ReviewState) -> dict:
    return {
        k: d for k, d in active_decisions(state).items() if d.status in {"confirmed", "corrected"}
    }


def _covers(actual, required) -> bool:
    """Count proved coverage only: an inclusive sentinel is not an exact empty/negative."""
    a, r = predicate_data(actual), predicate_data(required)
    if same_predicate(actual, required):
        return True
    if r.get("must_be_empty"):
        return a.get("must_be_empty") is True or a.get("equals", None) == []
    if "must_include" in r:
        values = a.get("equals", a.get("must_include"))
        return isinstance(values, list) and set(r["must_include"]) <= set(values)
    return "equals" in r and r["equals"] == [] and a.get("must_be_empty") is True


def cross_attribute_errors(values: dict) -> list[str]:
    errors = []
    for primary, collection in PRIMARY_SET_FIELDS:
        p, c = values.get(primary), values.get(collection)
        if p is None or c is None:
            continue
        p_data, c_data = predicate_data(p), predicate_data(c)
        scalar = p_data.get("equals")
        exact = c_data.get("equals", [] if c_data.get("must_be_empty") else None)
        if scalar is not None and isinstance(exact, list) and scalar not in exact:
            errors.append(f"{primary} conflicts with exact {collection}")
    presence, relations = values.get("role_semantics_present"), values.get("role_relations")
    if presence is not None and relations is not None:
        p, r = predicate_data(presence), predicate_data(relations)
        if p.get("equals") is False and (r.get("equals") or r.get("must_include")):
            errors.append("negative role presence conflicts with nonempty role relations")
    return errors


def review_report(package: ReviewPackage, state: ReviewState) -> dict:
    verify_package(package)
    verify_state(package, state)
    active, confirmed = active_decisions(state), confirmed_decisions(state)
    sources = {s.example_id: s for s in package.population}
    missing, conflicts, splits = [], [], {}
    for split in ("development", "holdout"):
        cases = [c for c in package.cases if c.split == split]
        counts, values, strata = Counter(), {}, Counter()
        complete = 0
        for case in cases:
            attributes = {}
            for attribute in case.attributes:
                decision = confirmed.get((case.example_id, attribute))
                if decision is None:
                    current = active.get((case.example_id, attribute))
                    missing.append(
                        {
                            "example_id": case.example_id,
                            "split": split,
                            "attribute": attribute,
                            "status": current.status if current else "pending",
                        }
                    )
                else:
                    attributes[attribute] = decision.predicate
                    counts[attribute] += 1
                    label = str(predicate_data(decision.predicate))
                    histogram = values.setdefault(attribute, Counter())
                    histogram[label] += 1
            complete += len(attributes) == len(case.attributes)
            source = sources[case.example_id]
            strata[f"{source.document_key}|{clause_type(source)}"] += 1
            conflicts.extend(
                {"example_id": case.example_id, "reason": reason}
                for reason in cross_attribute_errors(attributes)
            )
        splits[split] = {
            "selected_cases": len(cases),
            "complete_cases": complete,
            "confirmed_attributes": dict(counts),
            "predicate_distribution": values,
            "selected_strata": dict(strata),
        }
    gaps = []
    for split, data in splits.items():
        if data["complete_cases"] < package.profile.minimum_cases_per_split:
            gaps.append({"split": split, "reason": "minimum complete cases not reached"})
        for attribute in package.profile.attributes:
            if not data["confirmed_attributes"].get(attribute):
                gaps.append(
                    {
                        "split": split,
                        "attribute": attribute,
                        "reason": "no confirmed check",
                    }
                )
    for index, rule in enumerate(package.profile.coverage):
        count = 0
        for case in package.cases:
            if case.split != rule.split:
                continue
            source = sources[case.example_id]
            if (rule.document_key and source.document_key != rule.document_key) or (
                rule.clause_type and clause_type(source) != rule.clause_type
            ):
                continue
            decision = confirmed.get((case.example_id, rule.attribute))
            if decision and (rule.predicate is None or _covers(decision.predicate, rule.predicate)):
                count += 1
        if count < rule.minimum:
            gaps.append(
                {
                    "rule": index,
                    "split": rule.split,
                    "attribute": rule.attribute,
                    "required": rule.minimum,
                    "observed": count,
                }
            )
    return {
        "package_sha256": package.package_sha256,
        "state_sha256": state.state_sha256,
        "revision": state.revision,
        "splits": splits,
        "unresolved": missing,
        "coverage_gaps": gaps,
        "conflicts": conflicts,
        "ready_for_publication": not (missing or gaps or conflicts),
        "source_binding": "frozen full text and source structure; live import check required",
        "overlap_check": "identities and Unicode/case/whitespace-equivalent content",
        "holdout_exposure": (
            "unknown; prior use/near-duplicates/translations need human declaration"
        ),
    }
