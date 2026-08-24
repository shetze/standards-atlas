"""Focused golden-corpus support for role-semantics qualification."""

from __future__ import annotations

import csv
import json
import random
import re
from collections import Counter
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from standards_atlas.application.semantic_qualification.clause_access import (
    ClauseDescriptor,
    ClauseProvider,
)
from standards_atlas.application.semantic_qualification.role_qualification import (
    detect_role_candidate,
    normalize_relation,
)
from standards_atlas.domain.model import RoleRelation


class RoleCorpusCategory(StrEnum):
    """Reviewable role-case categories; sampling proposes one initial value."""

    NONE = "none"
    EXPLICIT_RELATION = "explicit_relation"
    MULTIPLE_RELATIONS = "multiple_relations"
    PASSIVE_WITHOUT_ACTOR = "passive_without_actor"
    ORGANIZATIONAL_RELATION = "organizational_relation"
    ROLE_TERM_WITHOUT_RELATION = "role_term_without_relation"
    NEGATIVE = "negative"
    STRUCTURED_TABLE = "structured_table"


class RoleCorpusBuildManifest(BaseModel):
    """Versioned recipe for reproducible role-corpus candidate selection."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    corpus_id: str = Field(min_length=1)
    task: str = "role-relation-extraction"
    corpus_version: str = Field(min_length=1)
    knowledge_domain: str = "default"
    seed: int = 0
    include_text: bool = True
    strict_quotas: bool = False
    quotas: dict[RoleCorpusCategory, int]

    @model_validator(mode="after")
    def quotas_must_be_positive(self) -> RoleCorpusBuildManifest:
        if not self.quotas:
            raise ValueError("at least one role-corpus quota is required")
        if any(value < 0 for value in self.quotas.values()):
            raise ValueError("role-corpus quotas must be non-negative")
        if sum(self.quotas.values()) < 1:
            raise ValueError("role-corpus quotas must select at least one clause")
        return self

    @classmethod
    def load(cls, path: Path) -> RoleCorpusBuildManifest:
        return cls.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")) or {})


class RoleGoldenExpected(BaseModel):
    """Human-reviewed role-semantics reference for one clause."""

    model_config = ConfigDict(frozen=True)

    role_semantics_present: bool
    relations: tuple[RoleRelation, ...] = ()

    @model_validator(mode="after")
    def relations_require_presence(self) -> RoleGoldenExpected:
        if self.relations and not self.role_semantics_present:
            raise ValueError("gold relations require role_semantics_present=true")
        return self


class RoleGoldenCase(BaseModel):
    """One focused role-corpus item and its optional reviewed reference."""

    model_config = ConfigDict(frozen=True)

    clause_id: str = Field(min_length=1)
    document_key: str = Field(min_length=1)
    reference: str = Field(min_length=1)
    content_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    category: RoleCorpusCategory
    text: str | None = None
    status: Literal["proposed", "published"] = "proposed"
    expected: RoleGoldenExpected | None = None
    review_note: str | None = None

    @model_validator(mode="after")
    def published_cases_require_expected(self) -> RoleGoldenCase:
        if self.status == "published" and self.expected is None:
            raise ValueError("published role golden cases require expected annotations")
        return self


class RoleGoldenCorpus(BaseModel):
    """Focused, reviewable role golden corpus."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    corpus_id: str = Field(min_length=1)
    task: str = "role-relation-extraction"
    corpus_version: str = Field(min_length=1)
    knowledge_domain: str = "default"
    cases: tuple[RoleGoldenCase, ...]

    @model_validator(mode="after")
    def case_keys_must_be_unique(self) -> RoleGoldenCorpus:
        keys = [(case.document_key, case.clause_id) for case in self.cases]
        if len(keys) != len(set(keys)):
            raise ValueError("role golden corpus document_key/clause_id pairs must be unique")
        return self

    @classmethod
    def load(cls, path: Path) -> RoleGoldenCorpus:
        return cls.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")) or {})


class RoleCorpusBuildResult(BaseModel):
    """Paths and selection statistics produced by the focused corpus builder."""

    model_config = ConfigDict(frozen=True)

    dataset_path: Path
    review_path: Path
    review_guide_path: Path
    golden_path: Path
    manifest_path: Path
    review_created: bool
    selected_count: int
    category_counts: dict[str, int]
    shortfalls: dict[str, int]


class RoleGoldenRegressionReport(BaseModel):
    """Presence and relation extraction metrics against published role gold cases."""

    model_config = ConfigDict(frozen=True)

    corpus_id: str
    corpus_version: str
    published_cases: int = Field(ge=0)
    matched_cases: int = Field(ge=0)
    missing_predictions: tuple[str, ...] = ()
    presence_accuracy: float = Field(ge=0.0, le=1.0)
    presence_precision: float = Field(ge=0.0, le=1.0)
    presence_recall: float = Field(ge=0.0, le=1.0)
    presence_f1: float = Field(ge=0.0, le=1.0)
    tuple_precision: float = Field(ge=0.0, le=1.0)
    tuple_recall: float = Field(ge=0.0, le=1.0)
    tuple_f1: float = Field(ge=0.0, le=1.0)
    expected_tuple_count: int = Field(ge=0)
    predicted_tuple_count: int = Field(ge=0)
    exact_tuple_matches: int = Field(ge=0)


class RoleGoldenCorpusBuilder:
    """Select a deterministic, role-focused corpus from persisted clauses."""

    def __init__(self, provider: ClauseProvider) -> None:
        self._provider = provider

    def build(
        self,
        manifest: RoleCorpusBuildManifest,
        output_root: Path,
        review_root: Path = Path("local/review"),
    ) -> RoleCorpusBuildResult:
        aggregate_document_keys = _aggregate_document_keys(self._provider)
        population = tuple(
            clause
            for clause in self._provider.list_clauses()
            if clause.text.strip() and clause.document_key not in aggregate_document_keys
        )
        buckets: dict[RoleCorpusCategory, list[ClauseDescriptor]] = {
            category: [] for category in RoleCorpusCategory
        }
        for clause in population:
            buckets[classify_role_corpus_category(clause)].append(clause)

        rng = random.Random(manifest.seed)
        selected: list[tuple[RoleCorpusCategory, ClauseDescriptor]] = []
        shortfalls: dict[str, int] = {}
        for category, quota in manifest.quotas.items():
            candidates = sorted(buckets[category], key=lambda item: (item.document_key, item.id))
            rng.shuffle(candidates)
            chosen = candidates[:quota]
            selected.extend((category, clause) for clause in chosen)
            if len(chosen) < quota:
                shortfalls[category.value] = quota - len(chosen)

        if manifest.strict_quotas and shortfalls:
            details = ", ".join(f"{key}={value}" for key, value in sorted(shortfalls.items()))
            raise ValueError(f"role-corpus quotas cannot be satisfied: {details}")

        selected.sort(key=lambda item: (item[0].value, item[1].document_key, item[1].id))
        target = output_root / manifest.task / manifest.corpus_version
        target.mkdir(parents=True, exist_ok=True)

        cases = tuple(
            RoleGoldenCase(
                clause_id=clause.id,
                document_key=clause.document_key,
                reference=_qualified_clause_reference(clause),
                content_hash=clause.content_hash,
                category=category,
                text=clause.text if manifest.include_text else None,
            )
            for category, clause in selected
        )
        review_path = (
            review_root / manifest.task / manifest.corpus_version / "role-golden-review.csv"
        )
        review_created = False
        if not review_path.exists():
            review_path.parent.mkdir(parents=True, exist_ok=True)
            _write_role_review_csv(review_path, cases)
            review_created = True
        review_guide_path = review_path.parent / "README.md"
        _write_role_review_guide(review_guide_path)
        golden_path = target / "role-golden-corpus.yaml"

        dataset = {
            "task": manifest.task,
            "version": manifest.corpus_version,
            "examples": [
                {
                    "id": f"{case.document_key}:{case.clause_id}",
                    "tags": [case.category.value],
                    "input": {
                        "content": {
                            "hash": case.content_hash,
                            **({"text": case.text} if case.text is not None else {}),
                        },
                        "context": {
                            "knowledge_domain": manifest.knowledge_domain,
                            "document_key": case.document_key,
                            "clause_id": case.clause_id,
                            "reference": case.reference,
                            "role_corpus_category": case.category.value,
                        },
                    },
                    "expected": {},
                    "annotation_status": "proposed",
                }
                for case in cases
            ],
        }
        dataset_path = target / "dataset.json"
        dataset_path.write_text(
            json.dumps(dataset, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

        counts = Counter(category.value for category, _ in selected)
        build_manifest = {
            **manifest.model_dump(mode="json"),
            "population_count": len(population),
            "selected_count": len(selected),
            "category_counts": dict(sorted(counts.items())),
            "shortfalls": dict(sorted(shortfalls.items())),
        }
        manifest_path = target / "corpus-manifest.yaml"
        manifest_path.write_text(
            yaml.safe_dump(build_manifest, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        return RoleCorpusBuildResult(
            dataset_path=dataset_path,
            review_path=review_path,
            review_guide_path=review_guide_path,
            golden_path=golden_path,
            manifest_path=manifest_path,
            review_created=review_created,
            selected_count=len(selected),
            category_counts=dict(sorted(counts.items())),
            shortfalls=dict(sorted(shortfalls.items())),
        )


def _aggregate_document_keys(provider: ClauseProvider) -> frozenset[str]:
    """Return family-level document keys when persisted part documents also exist."""
    keys = {document.key for document in provider.list_documents()}
    return frozenset(
        key
        for key in keys
        if any(candidate.startswith(f"{key}-") for candidate in keys if candidate != key)
    )


def _qualified_clause_reference(clause: ClauseDescriptor) -> str:
    """Return an unambiguous human-facing reference including the document part."""
    return f"{clause.document_key}:{clause.clause_reference}"


def classify_role_corpus_category(clause: ClauseDescriptor) -> RoleCorpusCategory:
    """Assign one deterministic sampling stratum, not a semantic gold label."""
    text = clause.text
    lowered = text.casefold()
    evidence = detect_role_candidate(text)
    action_hits = sum(
        marker in evidence.markers
        for marker in ("responsibility", "verification", "validation", "approval", "participation")
    )
    if clause.table_block_count > 0:
        return RoleCorpusCategory.STRUCTURED_TABLE
    if action_hits >= 2:
        return RoleCorpusCategory.MULTIPLE_RELATIONS
    if re.search(r"\bshall\s+be\s+(?:verified|validated|approved|performed)\b", lowered):
        return RoleCorpusCategory.PASSIVE_WITHOUT_ACTOR
    if any(
        marker in evidence.markers
        for marker in ("independence", "authority", "committee", "assignment")
    ):
        return RoleCorpusCategory.ORGANIZATIONAL_RELATION
    actor_marker = any(
        marker in evidence.markers
        for marker in ("supplier", "manufacturer", "developer", "assessment", "role")
    )
    if actor_marker and action_hits:
        return RoleCorpusCategory.EXPLICIT_RELATION
    if evidence.candidate:
        return RoleCorpusCategory.ROLE_TERM_WITHOUT_RELATION
    return RoleCorpusCategory.NEGATIVE


def evaluate_role_golden_corpus(
    golden: RoleGoldenCorpus, consensus_payload: dict[str, Any]
) -> RoleGoldenRegressionReport:
    """Compare published gold cases with a qualification consensus report."""
    published = tuple(
        case for case in golden.cases if case.status == "published" and case.expected is not None
    )
    if not published:
        raise ValueError("role golden corpus contains no published cases")
    predictions = {
        (str(item.get("document_key")), str(item.get("clause_id"))): item
        for item in consensus_payload.get("clauses", [])
    }

    tp = fp = tn = fn = 0
    expected_tuple_count = predicted_tuple_count = exact_tuple_matches = 0
    missing: list[str] = []
    for case in published:
        prediction = predictions.get((case.document_key, case.clause_id))
        if prediction is None:
            missing.append(f"{case.document_key}:{case.clause_id}")
            predicted_present = False
            predicted_relations: tuple[RoleRelation, ...] = ()
        else:
            predicted_present = bool(prediction.get("role_semantics_present", False))
            predicted_relations = _prediction_relations(prediction)
        expected = case.expected
        assert expected is not None
        if expected.role_semantics_present and predicted_present:
            tp += 1
        elif expected.role_semantics_present:
            fn += 1
        elif predicted_present:
            fp += 1
        else:
            tn += 1

        expected_keys = {normalize_relation(item).key for item in expected.relations}
        predicted_keys = {normalize_relation(item).key for item in predicted_relations}
        expected_tuple_count += len(expected_keys)
        predicted_tuple_count += len(predicted_keys)
        exact_tuple_matches += len(expected_keys & predicted_keys)

    total = len(published)
    presence_precision = _ratio(tp, tp + fp, empty=1.0)
    presence_recall = _ratio(tp, tp + fn, empty=1.0)
    tuple_precision = _ratio(
        exact_tuple_matches, predicted_tuple_count, empty=1.0 if expected_tuple_count == 0 else 0.0
    )
    tuple_recall = _ratio(
        exact_tuple_matches, expected_tuple_count, empty=1.0 if predicted_tuple_count == 0 else 0.0
    )
    return RoleGoldenRegressionReport(
        corpus_id=golden.corpus_id,
        corpus_version=golden.corpus_version,
        published_cases=total,
        matched_cases=total - len(missing),
        missing_predictions=tuple(sorted(missing)),
        presence_accuracy=(tp + tn) / total,
        presence_precision=presence_precision,
        presence_recall=presence_recall,
        presence_f1=_f1(presence_precision, presence_recall),
        tuple_precision=tuple_precision,
        tuple_recall=tuple_recall,
        tuple_f1=_f1(tuple_precision, tuple_recall),
        expected_tuple_count=expected_tuple_count,
        predicted_tuple_count=predicted_tuple_count,
        exact_tuple_matches=exact_tuple_matches,
    )


def _prediction_relations(payload: dict[str, Any]) -> tuple[RoleRelation, ...]:
    relations = []
    for item in payload.get("role_relation_consensus", ()):
        evidence = item.get("evidence")
        if isinstance(evidence, list):
            evidence = evidence[0] if evidence else None
        payload = {
            "actor": item["actor"],
            "target": item["target"],
            "condition": item.get("condition"),
            "evidence": evidence,
            "confidence": item.get("support"),
        }
        if item.get("relation_class") and item.get("predicate"):
            payload["relation_class"] = item["relation_class"]
            payload["predicate"] = item["predicate"]
        elif item.get("relation"):
            payload["relation"] = item["relation"]
        relations.append(RoleRelation.model_validate(payload))
    return tuple(relations)


def _ratio(numerator: int, denominator: int, *, empty: float) -> float:
    return numerator / denominator if denominator else empty


def _f1(precision: float, recall: float) -> float:
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


ROLE_REVIEW_FIELDS = (
    "document_key",
    "reference",
    "category",
    "text",
    "review_status",
    "role_semantics_present",
    "actor",
    "relation_class",
    "predicate",
    "target",
    "condition",
    "evidence",
    "review_note",
    "clause_id",
    "content_hash",
)

ROLE_RELATION_CLASS_CORE = (
    "performance",
    "responsibility",
    "assignment",
    "dependency",
    "consultation",
    "information",
    "participation",
    "membership",
)


def _write_role_review_csv(path: Path, cases: tuple[RoleGoldenCase, ...]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=ROLE_REVIEW_FIELDS)
        writer.writeheader()
        for case in cases:
            writer.writerow(
                {
                    "document_key": case.document_key,
                    "clause_id": case.clause_id,
                    "reference": case.reference,
                    "category": case.category.value,
                    "content_hash": case.content_hash,
                    "text": case.text or "",
                    "review_status": "pending",
                    "role_semantics_present": "",
                    "actor": "",
                    "relation_class": "",
                    "predicate": "",
                    "target": "",
                    "condition": "",
                    "evidence": "",
                    "review_note": "",
                }
            )


def _write_role_review_guide(path: Path) -> None:
    core = ", ".join(f"`{item}`" for item in ROLE_RELATION_CLASS_CORE)
    categories = ", ".join(f"`{item.value}`" for item in RoleCorpusCategory)
    path.write_text(
        "# Role Golden Corpus Review\n\n"
        "Review `role-golden-review.csv`. The initial category is a sampling proposal, "
        "not ground truth. Keep it, replace it with another allowed category, or set it "
        "to `none`.\n\n"
        f"Allowed categories: {categories}.\n\n"
        "Set `review_status=published` when the clause is fully reviewed. "
        "`role_semantics_present` is `true` or `false`.\n\n"
        "For every explicit complete relation, use one CSV row and fill `actor`, "
        "`relation_class`, `predicate`, and `target`. Additional rows for the same clause "
        "may leave review_status and role_semantics_present empty.\n\n"
        f"Recommended relation_class core: {core}. The field is intentionally open: "
        "use another concise class if none of the core values fits. `predicate` is always "
        "open and should preserve the evidence-grounded wording, e.g. `assess`, `record`, "
        "`be independent of`, or `not be included in`.\n\n"
        "`condition` contains only an explicit condition on that relation. `evidence` "
        "contains the smallest original text span supporting actor, predicate and target.\n",
        encoding="utf-8",
    )


def publish_role_golden_review(
    review_path: Path,
    manifest_path: Path,
    output_path: Path,
) -> RoleGoldenCorpus:
    """Compile the flat HITL review CSV into the machine-readable golden corpus."""
    build_manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    with review_path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError("role golden review contains no rows")

    grouped: dict[tuple[str, str], list[dict[str, str]]] = {}
    for row in rows:
        document_key = (row.get("document_key") or "").strip()
        clause_id = (row.get("clause_id") or "").strip()
        if not document_key or not clause_id:
            raise ValueError("every review row requires document_key and clause_id")
        grouped.setdefault((document_key, clause_id), []).append(row)

    cases: list[RoleGoldenCase] = []
    for key, case_rows in sorted(grouped.items()):
        first = case_rows[0]
        category_values = [
            (row.get("category") or "").strip()
            for row in case_rows
            if (row.get("category") or "").strip()
        ]
        if not category_values:
            raise ValueError(f"published review requires category for {key[0]}:{key[1]}")
        if len(set(category_values)) > 1:
            raise ValueError(f"conflicting category values for {key[0]}:{key[1]}")
        reviewed_category = RoleCorpusCategory(category_values[0])
        status_values = [
            (row.get("review_status") or "").strip().casefold()
            for row in case_rows
            if (row.get("review_status") or "").strip()
        ]
        status = next((value for value in status_values if value != "pending"), "pending")
        conflicting_statuses = {value for value in status_values if value != "pending"}
        if len(conflicting_statuses) > 1:
            raise ValueError(f"conflicting review_status values for {key[0]}:{key[1]}")
        if status == "rejected":
            continue
        if status == "pending":
            continue
        if status != "published":
            raise ValueError(f"unsupported review_status {status!r} for {key[0]}:{key[1]}")

        presence_values = [
            _parse_review_bool(row.get("role_semantics_present") or "")
            for row in case_rows
            if (row.get("role_semantics_present") or "").strip()
        ]
        if not presence_values:
            raise ValueError(
                f"published review requires role_semantics_present for {key[0]}:{key[1]}"
            )
        if len(set(presence_values)) > 1:
            raise ValueError(f"conflicting role_semantics_present values for {key[0]}:{key[1]}")
        presence = presence_values[0]

        relations: list[RoleRelation] = []
        for row in case_rows:
            actor = (row.get("actor") or "").strip()
            relation_class = (row.get("relation_class") or "").strip()
            predicate = (row.get("predicate") or "").strip()
            target = (row.get("target") or "").strip()
            condition = (row.get("condition") or "").strip() or None
            evidence = (row.get("evidence") or "").strip() or None
            relation_fields = (actor, relation_class, predicate, target)
            if not any(relation_fields):
                continue
            if not all(relation_fields):
                raise ValueError(
                    "relation rows require actor, relation_class, predicate and target "
                    f"for {key[0]}:{key[1]}"
                )
            relations.append(
                RoleRelation(
                    actor=actor,
                    relation_class=relation_class,
                    predicate=predicate,
                    target=target,
                    condition=condition,
                    evidence=evidence,
                )
            )
        if relations and not presence:
            raise ValueError(f"relations require role_semantics_present=true for {key[0]}:{key[1]}")

        notes = [
            (row.get("review_note") or "").strip()
            for row in case_rows
            if (row.get("review_note") or "").strip()
        ]
        cases.append(
            RoleGoldenCase(
                clause_id=key[1],
                document_key=key[0],
                reference=(first.get("reference") or "").strip(),
                content_hash=(first.get("content_hash") or "").strip(),
                category=reviewed_category,
                text=first.get("text") or None,
                status="published",
                expected=RoleGoldenExpected(
                    role_semantics_present=presence,
                    relations=tuple(relations),
                ),
                review_note=notes[0] if notes else None,
            )
        )

    if not cases:
        raise ValueError("role golden review contains no published cases")
    corpus = RoleGoldenCorpus(
        corpus_id=str(build_manifest["corpus_id"]),
        corpus_version=str(build_manifest["corpus_version"]),
        knowledge_domain=str(build_manifest.get("knowledge_domain", "default")),
        cases=tuple(cases),
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        yaml.safe_dump(corpus.model_dump(mode="json"), sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return corpus


def _parse_review_bool(value: str) -> bool:
    normalized = value.strip().casefold()
    if normalized in {"true", "yes", "1", "y"}:
        return True
    if normalized in {"false", "no", "0", "n"}:
        return False
    raise ValueError(f"invalid role_semantics_present value: {value!r}")
