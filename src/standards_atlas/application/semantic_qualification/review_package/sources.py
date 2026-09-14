"""Freeze complete clause text and source-only structure; never promote context hints."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from standards_atlas.application.context.source_structure import read_source_structure
from standards_atlas.application.model.source_structure import structure_fingerprint
from standards_atlas.application.semantic_qualification.annotations import normalized_content_hash
from standards_atlas.application.semantic_qualification.campaign_selection import stratified_sample
from standards_atlas.application.semantic_qualification.clause_access import ClauseProvider
from standards_atlas.application.semantic_qualification.partial_proposals import load_partial_inputs

from .model import EvidenceQuote, EvidenceSpan, ReviewPackage, ReviewSource, SemanticPredicate


def canonical_enrichment_suggestions(
    package: ReviewPackage, provider: ClauseProvider, *, example_ids: set[str] | None = None
) -> list[dict]:
    """Expose canonical semantic enrichments as review candidates, never as gold.

    Qualification inputs deliberately strip semantic answers. Review preparation
    re-opens the normalized EngineeringDocument through the existing ClauseProvider.
    The provider is also used to detect a stale corpus whose canonical structure no
    longer matches the normalized document.
    """
    sources = {source.example_id: source for source in package.population}
    selected = [
        case for case in package.cases if example_ids is None or case.example_id in example_ids
    ]
    suggestions: list[dict] = []
    for case in selected:
        source = sources[case.example_id]
        descriptor = provider.get_clause(source.clause_id)
        if (
            descriptor.id != source.clause_id
            or descriptor.document_key != source.document_key
            or descriptor.clause_reference != source.reference
            or descriptor.content_hash != source.content_hash
        ):
            raise ValueError(
                f"canonical EngineeringDocument source drift for review case: {source.example_id}"
            )
        if (
            source.structure.origin == "canonical"
            and descriptor.source_structure is not None
            and descriptor.source_structure != source.structure
        ):
            raise ValueError(
                "canonical EngineeringDocument structure drift for review case: "
                f"{source.example_id}; "
                "regenerate the qualification corpus/review package after normalization"
            )
        attributes = {item.path: item for item in descriptor.enrichment_context.attributes}
        for attribute in case.attributes:
            item = attributes.get(f"enrichments.semantic.{attribute}")
            if item is None or item.availability != "known":
                continue
            provenance = {
                "path": item.path,
                "origin": item.origin,
                "generated": (
                    item.generated.model_dump(mode="json") if item.generated is not None else None
                ),
                "confirmed": (
                    item.confirmed.model_dump(mode="json") if item.confirmed is not None else None
                ),
            }
            suggestions.append(
                {
                    "example_id": source.example_id,
                    "attribute": attribute,
                    "predicate": SemanticPredicate(equals=item.value),
                    "producer": "canonical-engineering-document",
                    "producer_kind": "engineering",
                    "rationale": (
                        "Current normalized EngineeringDocument enrichment under review; "
                        "critically assess it against the complete clause and structure, "
                        "and add evidence with an independent recommendation."
                    ),
                    "provenance": json.dumps(
                        provenance, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                    ),
                }
            )
    return suggestions


def fingerprint(model, field: str) -> str:
    return structure_fingerprint(model.model_dump(mode="json", exclude={field}))


def freeze_source(example) -> ReviewSource:
    context, content = example.input["context"], example.input["content"]
    text = content["text"]
    if normalized_content_hash(text) != content["hash"]:
        raise ValueError(f"source text/content hash mismatch: {example.id}")
    if content.get("truncated") or context.get("truncated") or example.input.get("truncated"):
        raise ValueError(f"truncated review source: {example.id}")
    structure = read_source_structure(context, text=text, content_hash=content["hash"])
    data = dict(
        example_id=example.id,
        document_key=context["document_key"],
        clause_id=context["clause_id"],
        reference=str(context.get("reference") or ""),
        text=text,
        content_hash=content["hash"],
        structure=structure.model_dump(mode="json"),
        context_sha256=structure_fingerprint(structure.model_dump(mode="json")),
    )
    return ReviewSource(**data, source_sha256=structure_fingerprint(data))


def freeze_population(examples) -> tuple[ReviewSource, ...]:
    sources = tuple(sorted((freeze_source(e) for e in examples), key=lambda e: e.example_id))
    for keys in (
        [s.example_id for s in sources],
        [(s.document_key, s.clause_id) for s in sources],
        [(s.document_key, s.reference) for s in sources],
    ):
        if len(keys) != len(set(keys)):
            raise ValueError(
                "review population needs unique example, clause and reference identities"
            )
    return sources


def population_hash(sources) -> str:
    return structure_fingerprint([s.source_sha256 for s in sources])


def duplicate_key(source: ReviewSource) -> str:
    """Conservative exact-content duplicate guard, beyond differing clause identifiers.

    Whitespace/case/Unicode equivalence is used ONLY for leakage checks, never for
    source identity. Near-duplicates/translations need future selection review.
    """
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", source.text)).strip().casefold()


@dataclass(frozen=True)
class _SampleItem:
    id: str
    input: dict


def select_holdout(population, excluded_ids, existing_ids, size: int, seed: int) -> tuple[str, ...]:
    by_id = {s.example_id: s for s in population}
    if not set(excluded_ids) <= by_id.keys() or not set(existing_ids) <= by_id.keys():
        raise ValueError("holdout exclusions/existing selection are absent from the population")
    blocked = {duplicate_key(by_id[i]) for i in excluded_ids}
    if any(duplicate_key(by_id[i]) in blocked for i in existing_ids):
        raise ValueError("holdout overlaps development/Golden/sentinel content")
    existing_keys = [duplicate_key(by_id[i]) for i in existing_ids]
    if len(set(existing_keys)) != len(existing_keys):
        raise ValueError("duplicate content within existing holdout")
    if size < len(existing_ids):
        raise ValueError("holdout size cannot discard existing holdout membership")
    # One representative per content group, stable under corpus order changes.
    eligible = {}
    for source in sorted(population, key=lambda s: s.example_id):
        key = duplicate_key(source)
        if key not in blocked and key not in existing_keys:
            eligible.setdefault(key, source)
    remaining = size - len(existing_ids)
    if remaining > len(eligible):
        raise ValueError(
            f"not enough disjoint holdout sources: need {remaining}, available {len(eligible)}"
        )
    items = [
        _SampleItem(
            s.example_id,
            {
                "content": {"hash": s.content_hash},
                "context": {"document_key": s.document_key, "clause_type": clause_type(s)},
            },
        )
        for s in eligible.values()
    ]
    selected = stratified_sample(items, remaining, seed) if remaining else ()
    return tuple(sorted((*existing_ids, *(e.id for e in selected))))


def clause_type(source: ReviewSource) -> str:
    return next(
        (
            str(f.value)
            for f in source.structure.facts
            if f.field == "clause_type" and f.distance == 0
        ),
        "unknown",
    )


def evidence_text(source: ReviewSource, target: str) -> str:
    if target == "text":
        return source.text
    if re.fullmatch(r"fact:\d+", target):
        index = int(target.split(":")[1])
        if index < len(source.structure.facts):
            value = source.structure.facts[index].value
            if isinstance(value, str):
                return value
    raise ValueError(f"evidence target is not frozen source text: {target}")


def resolve_evidence(source: ReviewSource, quote: EvidenceQuote) -> EvidenceSpan:
    text = evidence_text(source, quote.target)
    matches = []
    pos = text.find(quote.quote)
    while pos >= 0:
        if text[:pos].endswith(quote.prefix) and text[pos + len(quote.quote) :].startswith(
            quote.suffix
        ):
            matches.append(pos)
            if len(matches) > 1:
                break
        pos = text.find(quote.quote, pos + 1)
    if len(matches) != 1:
        raise ValueError("evidence quote must have exactly one source match; add prefix/suffix")
    return EvidenceSpan(**quote.model_dump(), start=matches[0], end=matches[0] + len(quote.quote))


def verify_current_sources(
    package: ReviewPackage, *, run: Path | None = None, dataset: Path | None = None
) -> None:
    """Re-open originals on import. A relocated source can be supplied explicitly."""
    if run is None and dataset is None:
        location = package.source_location
        run = Path(location["run"]) if "run" in location else None
        dataset = Path(location["dataset"]) if "dataset" in location else None
    sources = freeze_population(load_partial_inputs(run=run, dataset=dataset).examples)
    if sources != package.population:
        raise ValueError(
            "source text, identity, population or structural context changed since build"
        )
    for name, expected in package.input_files.items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"review input/rules changed since build: {name}")
