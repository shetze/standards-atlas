"""Exercise schema validation, citation translation and canonical persistence together.

These are controlled HTTP responses, not a live phi-4 quality measurement. Source
text is synthetic; the failing citation strings are taken from the reported log.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from standards_atlas.adapters.filesystem import FileSystemEngineeringDocumentRepository
from standards_atlas.adapters.llm import LlmConfig, OpenAICompatibleLlmGateway
from standards_atlas.application.evaluation.repository import PromptRepository
from standards_atlas.application.ports.llm_gateway import LlmResponseError
from standards_atlas.application.services.context_enrichment_service import (
    ContextEnrichmentService,
    LlmContextRoutingEnricher,
)
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    DocumentType,
    ScopeReach,
    Standard,
    StandardKey,
    StandardReference,
    StructuralContext,
    StructuralNodeKind,
    TextBlock,
)

PROMPTS = Path(__file__).resolve().parents[3] / "src/standards_atlas/resources/semantic/prompts"
PARTS = "Parts 1, 2, 3 and 4 of IEC 61508"
EVIDENCE = f"This synthetic declaration governs {PARTS}."


def documents():
    source = Standard(
        name="Synthetic source",
        key=StandardKey(value="IEC61508-0"),
        title="Synthetic source",
        document_type=DocumentType.STANDARD,
        clauses=tuple(
            Clause(
                id=ClauseId(value=f"source-{coordinate}"),
                reference=StandardReference(
                    standard="IEC 61508", part="0", year=2005, clause=coordinate
                ),
                clause_type=ClauseType.SCOPE,
                content=(TextBlock(id=f"text-{coordinate}", text=text),),
                structural_context=StructuralContext(node_kind=StructuralNodeKind.LEAF),
            )
            for coordinate, text in [
                ("4.5", "This synthetic scope governs this clause."),
                ("4.7", EVIDENCE),
            ]
        ),
    )
    parts = tuple(
        Standard(
            name=f"Synthetic part {number}",
            key=StandardKey(value=f"IEC61508-{number}"),
            title=f"Synthetic part {number}",
            document_type=DocumentType.STANDARD,
            clauses=(
                Clause(
                    id=ClauseId(value=f"part-{number}-1"),
                    clause_type=ClauseType.CLAUSE,
                    reference=StandardReference(
                        standard="IEC 61508", part=str(number), year=2010, clause="1"
                    ),
                ),
            ),
        )
        for number in range(1, 5)
    )
    return source, parts


def answer(reference, evidence="This synthetic scope governs this clause."):
    return {
        "scope_declarations": [
            {
                "reaches": [{"reference": reference, "include_descendants": reference != "4.5"}],
                "conditions": [],
                "exclusions": [],
                "qualifications": [],
                "evidence": [evidence],
            }
        ],
        "reference_routings": [],
    }


class HttpGateway(OpenAICompatibleLlmGateway):
    """Only the HTTP endpoint is controlled; gateway JSON/cache validation is real."""

    def __init__(self, responses, cache):
        super().__init__(LlmConfig(model="fixture-model", cache_directory=cache))
        self.responses = list(responses)
        self.requests = []

    def _request_json(self, method, endpoint, payload=None):
        assert method == "POST" and endpoint == "chat/completions"
        self.requests.append(payload)
        value = self.responses.pop(0)
        return {
            "choices": [{"message": {"content": json.dumps(value)}, "finish_reason": "stop"}],
            "model": "fixture-model",
        }


def enricher(gateway, parts):
    return LlmContextRoutingEnricher(
        gateway,
        prompt=PromptRepository(PROMPTS).load("context-routing-enrichment", "context-routing-v3"),
        model="fixture-model",
        scope_documents=parts,
    )


@pytest.mark.parametrize(
    "kind,reference,part",
    [
        ("document", "IEC 61508-0:2005 4.5", None),
        ("part", "1, 2, 3 and 4 of IEC 61508", "Part 1"),
    ],
)
def test_reported_representations_fail_old_schema_but_v3_preserves_targets(kind, reference, part):
    old = answer(reference)
    old["scope_declarations"][0]["reaches"][0] = {
        "kind": kind,
        "document_key": "IEC61508-0",
        "part": part,
        "clause_id": None,
        "reference": reference,
    }
    repository = PromptRepository(PROMPTS)
    schema = repository.load("context-routing-enrichment", "context-routing-v2").output_schema
    errors = list(Draft202012Validator(schema).iter_errors(old))
    assert any(list(e.path)[-1] == "reference" and e.validator_value == "null" for e in errors)
    current = repository.load("context-routing-enrichment", "context-routing-v3").output_schema
    assert not list(Draft202012Validator(current).iter_errors(answer(reference)))
    assert list(Draft202012Validator(current).iter_errors(old))


def test_real_gateway_to_canonical_persistence_handles_both_scope_cases(tmp_path):
    source, parts = documents()
    repo = FileSystemEngineeringDocumentRepository(tmp_path / "workspace")
    for document in (source, *parts):
        repo.save(document)
    gateway = HttpGateway(
        [answer("4.5"), answer("1, 2, 3 and 4 of IEC 61508", EVIDENCE)], tmp_path / "cache"
    )
    service = ContextEnrichmentService(documents=repo, enricher=enricher(gateway, parts))
    result = service.enrich(source.key.value)
    assert result.context_enrichment_failures == 0 and not result.routing_failures
    assert len(gateway.requests) == 2
    persisted = repo.load(source.key)
    local = persisted.clauses[0].context_routing.scopes[0].reaches
    assert len(local) == 1 and local[0].kind.value == "clause"
    assert local[0].clause_id == "source-4.5"
    assert local[0].reference == "IEC 61508-0:2005 4.5"
    reaches = persisted.clauses[1].context_routing.scopes[0].reaches
    assert [r.document_key for r in reaches] == [d.key.value for d in parts]
    assert all(r.kind.value == "part" and r.reference is None for r in reaches)
    assert persisted.clauses[1].context_routing.scopes[0].evidence == (EVIDENCE,)
    assert all(ScopeReach.model_validate(r.model_dump()) == r for r in (*local, *reaches))
    path = tmp_path / "workspace/documents/IEC61508-0.json"
    before = path.read_bytes()
    second = service.enrich(source.key.value)
    assert second.routing_reused == 2 and path.read_bytes() == before
    assert len(gateway.requests) == 2
    assert "scope_target_documents" in gateway.requests[0]["messages"][1]["content"]


def test_retry_contains_rejected_json_and_does_not_relax_schema(tmp_path):
    source, parts = documents()
    malformed = answer("4.5")
    malformed["scope_declarations"][0]["reaches"][0]["kind"] = "document"
    gateway = HttpGateway([malformed, answer("4.5")], tmp_path / "cache")
    routing = enricher(gateway, parts).enrich(clause=source.clauses[0], document=source)
    assert routing.scopes[0].reaches[0].clause_id == "source-4.5"
    assert len(gateway.requests) == 2
    correction = gateway.requests[1]["messages"][1]["content"]
    assert "Rejected output" in correction and "document" in correction
    assert gateway.requests[0]["response_format"] == gateway.requests[1]["response_format"]
    assert len(list((tmp_path / "cache").glob("*.json"))) == 1


def test_failed_attempts_are_retained_and_do_not_merge_empty_routing(tmp_path):
    source, parts = documents()
    source = source.model_copy(update={"clauses": source.clauses[:1]})
    malformed = answer("4.5")
    malformed["scope_declarations"][0]["reaches"][0]["kind"] = "document"
    gateway = HttpGateway([malformed, malformed], tmp_path / "cache")
    repo = FileSystemEngineeringDocumentRepository(tmp_path / "workspace")
    repo.save(source)
    result = ContextEnrichmentService(documents=repo, enricher=enricher(gateway, parts)).enrich(
        source.key.value
    )
    assert result.context_enrichment_failures == 1 and len(result.routing_failures) == 1
    failure = result.routing_failures[0]
    assert failure["reference"] == "IEC 61508-0:2005 4.5"
    assert "document" in failure["attempts"]["first_response"]
    assert "document" in failure["attempts"]["retry_response"]
    clause = result.document.clauses[0]
    assert clause.provenance.availability("enrichments.context_routing") == "not_evaluated"
    assert not list((tmp_path / "cache").glob("*.json"))


def test_catalog_changes_invalidate_reuse_but_generated_values_do_not(tmp_path):
    source, parts = documents()
    gateway = HttpGateway([], tmp_path / "cache")
    first = enricher(gateway, parts).input_fingerprint(clause=source.clauses[0], document=source)
    missing = enricher(gateway, parts[:-1]).input_fingerprint(
        clause=source.clauses[0], document=source
    )
    assert first != missing
    altered = tuple(part.model_copy(update={"title": "Changed presentation"}) for part in parts)
    assert (
        enricher(gateway, altered).input_fingerprint(clause=source.clauses[0], document=source)
        == first
    )


def test_unresolved_part_list_cannot_escape_as_partial_success(tmp_path):
    source, parts = documents()
    gateway = HttpGateway([answer(PARTS, EVIDENCE)] * 2, tmp_path / "cache")
    with pytest.raises(LlmResponseError, match="Part 4.*found 0") as captured:
        enricher(gateway, parts[:-1]).enrich(clause=source.clauses[1], document=source)
    assert captured.value.raw_content
    assert captured.value.raw_response["first_response"]


def test_reference_routing_contract_is_unchanged(tmp_path):
    source, parts = documents()
    source = source.model_copy(
        update={
            "clauses": (
                source.clauses[0].with_baseline_updates(
                    content=(TextBlock(id="reference-source", text="See Annex G."),)
                ),
                source.clauses[1].model_copy(
                    update={
                        "reference": StandardReference(
                            standard="IEC 61508", part="0", year=2005, clause="G"
                        )
                    }
                ),
            )
        }
    )
    response = {
        "scope_declarations": [],
        "reference_routings": [
            {
                "target": {
                    "document_key": None,
                    "clause_id": None,
                    "title": None,
                    "reference": "Annex G",
                },
                "role": "provides_exception",
                "evidence": ["See Annex G."],
            }
        ],
    }
    gateway = HttpGateway([response], tmp_path / "cache")
    routing = enricher(gateway, parts).enrich(clause=source.clauses[0], document=source)
    assert routing.references[0].target.reference == "IEC 61508-0:2005 G"
    assert routing.references[0].target.clause_id == source.clauses[1].id.value
    assert routing.references[0].role.value == "provides_exception"


def test_target_structure_change_invalidates_context_routing_reuse(tmp_path):
    source, parts = documents()
    gateway = HttpGateway([], tmp_path / "cache")
    old = enricher(gateway, parts).input_fingerprint(clause=source.clauses[0], document=source)
    changed = parts[0].model_copy(
        update={
            "clauses": (
                parts[0].clauses[0].model_copy(update={"id": ClauseId(value="changed-target-id")}),
            )
        }
    )
    new = enricher(gateway, (changed, *parts[1:])).input_fingerprint(
        clause=source.clauses[0], document=source
    )
    assert old != new


def test_reported_figure_table_scope_is_retained_without_retry_and_reported_unresolved(tmp_path):
    source, parts = documents()
    source = source.model_copy(update={"clauses": (source.clauses[0],)})
    citation = "IEC 61508-2 Figure 2 and Table 1"
    # Synthetic scope evidence: the production log does not disclose the source
    # excerpt. This tests address handling, not whether 4.9 actually declares scope.
    evidence = f"These synthetic restrictions apply to {citation}."
    source = source.model_copy(
        update={
            "clauses": (
                source.clauses[0].with_baseline_updates(
                    content=(TextBlock(id="object-scope", text=evidence),)
                ),
            )
        }
    )
    gateway = HttpGateway([answer(citation, evidence)], tmp_path / "cache")
    repository = FileSystemEngineeringDocumentRepository(tmp_path / "workspace")
    for document in (source, *parts):
        repository.save(document)
    service = ContextEnrichmentService(documents=repository, enricher=enricher(gateway, parts))
    result = service.enrich(source.key.value)
    assert result.context_enrichment_failures == 0
    assert not result.routing_failures
    assert len(gateway.requests) == 1
    assert len(result.unresolved_scope_targets) == 1
    assert result.unresolved_scope_targets[0]["reference"] == citation
    assert result.unresolved_scope_targets[0]["status"] == "unresolved"
    stored = repository.load(source.key)
    scope = stored.clauses[0].context_routing.scopes[0]
    assert scope.evidence == (evidence,)
    assert len(scope.reaches) == 1
    reach = scope.reaches[0]
    assert reach.document_key == "IEC61508-2"
    assert reach.clause_id is None and reach.reference == citation
    assert reach.kind.value == "subtree"  # Preserve the supplied descendant intent.
    repeated = service.enrich(source.key.value)
    assert repeated.unresolved_scope_targets == result.unresolved_scope_targets
    assert len(gateway.requests) == 1  # Reuse still reports unresolved addresses.


def test_informational_object_reference_is_not_promoted_to_a_scope(tmp_path):
    source, parts = documents()
    text = "For further information see IEC 61508-2 Figure 2 and Table 1."
    clause = source.clauses[0].with_baseline_updates(
        content=(TextBlock(id="object-reference", text=text),)
    )
    source = source.model_copy(update={"clauses": (clause,)})
    response = {
        "scope_declarations": [],
        "reference_routings": [
            {
                "target": {
                    "document_key": "IEC61508-2",
                    "clause_id": None,
                    "title": None,
                    "reference": "IEC 61508-2 Figure 2 and Table 1",
                },
                "role": "other",
                "evidence": [text],
            }
        ],
    }
    gateway = HttpGateway([response], tmp_path / "cache")
    routing = enricher(gateway, parts).enrich(clause=clause, document=source)
    assert routing.scopes == ()
    assert routing.references[0].target.clause_id is None
    assert routing.references[0].target.reference == "IEC 61508-2 Figure 2 and Table 1"
    assert routing.references[0].role.value == "other"
    assert routing.references[0].evidence == (text,)
    assert len(gateway.requests) == 1
