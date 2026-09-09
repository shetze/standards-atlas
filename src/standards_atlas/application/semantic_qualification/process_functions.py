"""Evidence-aware process-function voting, independent of other dimensions.

Only explicitly supplied structured fields are observations. Provider defaults,
free-text rationale and repetitions must never become extra negative votes.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING, Any

from standards_atlas.domain.model import ProcessFunction

if TYPE_CHECKING:
    from .annotations import ClauseEvaluationAnnotation
    from .consensus import ModelVote

PROCESS_FIELDS = ("process_functions", "primary_process_function")
PROCESS_VOTE_FIELDS = frozenset(
    (
        *PROCESS_FIELDS,
        "process_primary_evaluated",
        "process_repetitions",
        "process_primary_repetitions",
        "process_stability",
    )
)
PROCESS_PRIMARY_FIELDS = (
    "primary_process_function",
    "process_primary_evaluated",
    "process_primary_decided",
    "process_primary_category",
    "process_function_category",
    "process_primary_confidence",
    "process_primary_unanimous",
    "process_primary_participating_models",
    "process_primary_support",
)
PROCESS_SET_FIELDS = (
    "proposed_process_functions",
    "process_set_evaluated",
    "process_set_decided",
    "process_set_category",
    "process_set_confidence",
    "process_exact_set_agreement",
    "process_set_unanimous",
    "process_participating_models",
    "process_function_support",
)
PROCESS_CLAUSE_FIELDS = frozenset(
    (*PROCESS_PRIMARY_FIELDS, *PROCESS_SET_FIELDS, "process_decision_conflict")
)


def with_process_observation_fields(
    annotation: ClauseEvaluationAnnotation, case_directory: Path
) -> ClauseEvaluationAnnotation:
    """Recover legacy field availability only from matching structured responses.

    This is a read-only bridge for recomputing consensus from retained local
    proposal runs. An archived consensus without these observations stays
    unevaluated. Explicit new generator metadata takes precedence over recovery.
    """
    if annotation.generator.provided_fields is not None:
        return annotation
    provided: tuple[str, ...] = ()
    response_path = case_directory / "response.json"
    if response_path.is_file():
        try:
            payload = json.loads(response_path.read_text(encoding="utf-8"))
            generator = annotation.generator
            identity_matches = (
                payload.get("provider") == generator.provider
                and payload.get("model") == generator.model
                and payload.get("prompt_version") == generator.prompt_id
                and generator.input_hash is not None
                and payload.get("input_hash") == generator.input_hash
                and generator.raw_response_hash is not None
                and payload.get("raw_response_hash") == generator.raw_response_hash
            )
            # A focused interview response is not a full-dimension observation.
            # New interviews persist explicit availability; old ones are not
            # reconstructed from their synthesized default-filled selection.
            if identity_matches and not (case_directory / "interview.json").is_file():
                value = payload.get("value")
                if isinstance(value, dict):
                    provided = _matching_fields(value, annotation)
        except (OSError, TypeError, ValueError, KeyError):
            provided = ()
    return annotation.model_copy(
        update={"generator": annotation.generator.model_copy(update={"provided_fields": provided})}
    )


def _matching_fields(
    value: dict[str, Any], annotation: ClauseEvaluationAnnotation
) -> tuple[str, ...]:
    """Validate the raw set, allowing only the generator's harmless normalization."""
    members = value.get("process_functions")
    if not isinstance(members, list):
        return ()
    parsed = tuple(dict.fromkeys(ProcessFunction(item) for item in members))
    primary_supplied = "primary_process_function" in value
    primary = value.get("primary_process_function")
    primary = ProcessFunction(primary) if primary is not None else None
    if primary is not None and primary not in parsed:
        parsed = (primary, *parsed)
    proposal = annotation.proposal
    if parsed != proposal.process_functions:
        return ()
    if primary_supplied and primary != proposal.primary_process_function:
        return ()
    return PROCESS_FIELDS if primary_supplied else ("process_functions",)


def process_vote(annotations: list[ClauseEvaluationAnnotation]) -> dict[str, Any]:
    """Collapse repetitions into at most one coherent observation per model.

    A tied repeat mode abstains rather than depending on filesystem order. A
    partial answer can observe the set without observing the primary. A missing
    set cannot establish a primary with a fabricated supporting set.
    """
    observations = []
    for annotation in annotations:
        fields = set(annotation.generator.provided_fields or ())
        if "process_functions" not in fields:
            continue
        proposal = annotation.proposal
        primary_evaluated = "primary_process_function" in fields
        observations.append(
            (
                tuple(sorted(proposal.process_functions, key=lambda item: item.value)),
                proposal.primary_process_function if primary_evaluated else None,
                primary_evaluated,
            )
        )
    if not observations:
        return {}
    ranked = Counter(observations).most_common()
    selected, count = ranked[0]
    result: dict[str, Any] = {
        "process_repetitions": len(observations),
        "process_primary_repetitions": sum(item[2] for item in observations),
        "process_stability": count / len(observations),
    }
    if len(ranked) > 1 and ranked[1][1] == count:
        return result
    members, primary, primary_evaluated = selected
    result.update(
        process_functions=members,
        primary_process_function=primary,
        process_primary_evaluated=primary_evaluated,
    )
    return result


def resolve_process_votes(
    votes: tuple[ModelVote, ...],
    *,
    minimum_models: int,
    strong_threshold: float,
    majority_threshold: float,
    label_threshold: float,
) -> dict[str, Any]:
    """Resolve primary and label-wise set with separate denominators/support.

    Explicit null primaries and empty sets are valid negative observations.
    Missing fields do not vote. Ties and an absence of majority labels are not
    silently converted to negative decisions. Support is not accuracy.
    """
    from .consensus import ConsensusCategory, _category_for_confidence

    set_votes = [vote for vote in votes if vote.process_functions is not None]
    primary_votes = [vote for vote in votes if vote.process_primary_evaluated]
    n_set, n_primary = len(set_votes), len(primary_votes)
    if (
        len({vote.model_id for vote in set_votes}) != n_set
        or len({vote.model_id for vote in primary_votes}) != n_primary
    ):
        raise ValueError("process votes must have unique model ids")
    primary_counts = Counter(vote.primary_process_function for vote in primary_votes)
    primary, count = primary_counts.most_common(1)[0] if primary_counts else (None, 0)
    primary_confidence = count / n_primary if n_primary else 0.0
    primary_decided = primary_confidence > 0.5
    if not primary_decided:
        primary = None
    label_counts = Counter(label for vote in set_votes for label in vote.process_functions)
    label_support = {label.value: count / n_set for label, count in label_counts.items()}
    selected = tuple(
        sorted(
            (
                label
                for label, count in label_counts.items()
                if count / n_set > 0.5 and (count / n_set >= label_threshold or label == primary)
            ),
            key=lambda item: item.value,
        )
    )
    empty_count = sum(vote.process_functions == () for vote in set_votes)
    set_confidence = (
        min(label_support[label.value] for label in selected)
        if selected
        else empty_count / n_set
        if n_set
        else 0.0
    )
    set_decided = bool(selected) or set_confidence > 0.5
    exact_agreement = (
        sum(set(vote.process_functions) == set(selected) for vote in set_votes) / n_set
        if n_set
        else 0.0
    )

    def category(confidence: float, count: int, decided: bool) -> ConsensusCategory:
        candidate = _category_for_confidence(
            confidence, count, minimum_models, strong_threshold, majority_threshold
        )
        if not decided and candidate != ConsensusCategory.INSUFFICIENT:
            return ConsensusCategory.DISPUTED
        return candidate

    primary_category = category(primary_confidence, n_primary, primary_decided)
    return {
        "primary_process_function": primary,
        "proposed_process_functions": selected,
        "process_primary_evaluated": n_primary > 0
        or any(vote.process_primary_repetitions > 0 for vote in votes),
        "process_set_evaluated": n_set > 0 or any(vote.process_repetitions > 0 for vote in votes),
        "process_primary_decided": primary_decided,
        "process_set_decided": set_decided,
        "process_function_category": primary_category,
        "process_primary_category": primary_category,
        "process_set_category": category(set_confidence, n_set, set_decided),
        "process_primary_confidence": primary_confidence,
        "process_set_confidence": set_confidence,
        "process_exact_set_agreement": exact_agreement,
        "process_primary_unanimous": n_primary > 0 and len(primary_counts) == 1,
        "process_set_unanimous": n_set > 0
        and len({frozenset(vote.process_functions) for vote in set_votes}) == 1,
        "process_primary_participating_models": n_primary,
        "process_participating_models": n_set,
        "process_primary_support": {
            "none" if key is None else key.value: value / n_primary
            for key, value in sorted(
                primary_counts.items(), key=lambda item: "" if item[0] is None else item[0].value
            )
        },
        "process_function_support": dict(sorted(label_support.items())),
        "process_decision_conflict": bool(
            primary_decided and primary is not None and primary not in selected
        ),
    }


def apply_process_overrides(
    result: dict[str, Any], overrides: dict[str, dict[str, Any]], sources: dict[str, str]
) -> None:
    """Keep final primary/set snapshots independent of subsequent model votes."""
    from .consensus import ConsensusCategory

    for dimension, fields in (
        ("process_function", PROCESS_PRIMARY_FIELDS),
        ("process_set", PROCESS_SET_FIELDS),
    ):
        if dimension not in overrides:
            continue
        snapshot = overrides[dimension]
        if not set(fields).issubset(snapshot):
            raise ValueError(f"incomplete {dimension} cascade snapshot")
        for field in fields:
            value = snapshot[field]
            if field.endswith("category"):
                value = ConsensusCategory(value)
            elif field == "primary_process_function":
                value = ProcessFunction(value) if value is not None else None
            elif field == "proposed_process_functions":
                value = tuple(ProcessFunction(item) for item in value)
            result[field] = value
        sources[dimension] = str(snapshot["source"])
    primary = result["primary_process_function"]
    result["process_decision_conflict"] = bool(
        result["process_primary_decided"]
        and primary is not None
        and result["process_set_decided"]
        and primary not in result["proposed_process_functions"]
    )


def process_report_metrics(clauses: Any) -> dict[str, Any]:
    """Coverage and agreement only; no invented Gold accuracy metrics."""
    items = tuple(clauses)
    return {
        "clause_count": len(items),
        "set_evaluated": sum(item.process_set_evaluated for item in items),
        "primary_evaluated": sum(item.process_primary_evaluated for item in items),
        "set_not_evaluated": sum(not item.process_set_evaluated for item in items),
        "primary_not_evaluated": sum(not item.process_primary_evaluated for item in items),
        "set_decided": sum(item.process_set_decided for item in items),
        "primary_decided": sum(item.process_primary_decided for item in items),
        "empty_set_decisions": sum(
            item.process_set_decided and not item.proposed_process_functions for item in items
        ),
        "null_primary_decisions": sum(
            item.process_primary_decided and item.primary_process_function is None for item in items
        ),
        "decision_conflicts": sum(item.process_decision_conflict for item in items),
        "set_participation": dict(
            sorted(Counter(str(item.process_participating_models) for item in items).items())
        ),
        "primary_participation": dict(
            sorted(
                Counter(str(item.process_primary_participating_models) for item in items).items()
            )
        ),
    }
