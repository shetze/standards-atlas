"""Schema-valid but semantically wrong replies must not publish reading-list scopes."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from typer.testing import CliRunner

from standards_atlas.adapters.filesystem import FileSystemEngineeringDocumentRepository
from standards_atlas.adapters.llm import LlmConfig, OpenAICompatibleLlmGateway
from standards_atlas.application.evaluation.repository import PromptRepository
from standards_atlas.application.services.context_enrichment_service import (
    ContextEnrichmentService,
    LlmContextRoutingEnricher,
)
from standards_atlas.cli import app
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    DocumentType,
    Standard,
    StandardKey,
    StandardReference,
    StructuralContext,
    TextBlock,
)

FAQ = "Further information and frequently asked questions are available in Annex A."
READING = (
    "You may find it helpful to read the following sections first:\n\n"
    "- Clause 7 of IEC 61508-2 and IEC 61508-3 respectively.\n"
    "- Figure 2 and Table 1 of IEC 61508-2."
)
ADVICE = "Each requirement should be considered in the context of the example (where applicable)."
PROMPTS = Path("src/standards_atlas/resources/semantic/prompts")


class ControlledHttp(OpenAICompatibleLlmGateway):
    def __init__(self, responses, cache):
        super().__init__(LlmConfig(model="test-model", cache_directory=cache))
        self.responses = list(responses)
        self.requests = []

    def _request_json(self, method, endpoint, payload=None):
        assert method == "POST" and endpoint == "chat/completions"
        self.requests.append(payload)
        value = self.responses.pop(0)
        return {"choices": [{"message": {"content": json.dumps(value)}, "finish_reason": "stop"}]}


def document(part, coordinates, text=""):
    return Standard(
        name="Synthetic context pipeline",
        key=StandardKey(value=f"IEC61508-{part}"),
        title="Synthetic context pipeline",
        document_type=DocumentType.STANDARD,
        clauses=tuple(
            Clause(
                id=ClauseId(value=f"p{part}-{coord}"),
                clause_type=ClauseType.CLAUSE,
                reference=StandardReference(
                    standard="IEC 61508", part=part, year=2010, clause=coord
                ),
                content=(TextBlock(id="body", text=text),) if coord == "4.9" else (),
                structural_context=StructuralContext(node_kind="leaf"),
            )
            for coord in coordinates
        ),
    )


def scope(citations, evidence, conditions=()):
    return {
        "reaches": [{"reference": text, "include_descendants": False} for text in citations],
        "conditions": list(conditions),
        "exclusions": [],
        "qualifications": [],
        "evidence": [evidence],
    }


def service(repo, responses, cache, source, external=()):
    for doc in (source, *external):
        repo.save(doc)
    gateway = ControlledHttp(responses, cache)
    enricher = LlmContextRoutingEnricher(
        gateway,
        prompt=PromptRepository(PROMPTS).load("context-routing-enrichment", "context-routing-v3"),
        model="test-model",
        scope_documents=external,
    )
    return ContextEnrichmentService(documents=repo, enricher=enricher), gateway


def test_bad_v3_reply_is_repaired_before_save_with_private_reports_and_stable_reuse(
    tmp_path,
    monkeypatch,
):
    from standards_atlas.cli.commands.document_commands import management

    source = document("0", ("4.9", "A"), "\n\n".join((FAQ, READING, ADVICE)))
    external = tuple(document(part, ("7",)) for part in ("2", "3"))
    response = {
        "scope_declarations": [
            scope(["IEC 61508-2 Clause 7", "IEC 61508-2 Figure 2 and Table 1"], READING, (ADVICE,)),
            scope(["Annex A"], FAQ),
        ],
        "reference_routings": [
            {
                "target": {
                    "document_key": "IEC61508-0",
                    "clause_id": None,
                    "reference": "Annex A",
                    "title": None,
                },
                "role": "provides_applicability",
                "evidence": [FAQ],
            }
        ],
    }
    workspace = tmp_path / "workspace"
    repo = FileSystemEngineeringDocumentRepository(workspace)
    real_service, gateway = service(repo, [response], tmp_path / "cache", source, external)
    results = []

    def capture(key):
        result = real_service.enrich(key)
        results.append(result)
        return result

    monkeypatch.setattr(
        management, "managed_llm_server", lambda *_: SimpleNamespace(start=lambda: None)
    )
    monkeypatch.setattr(
        management,
        "build_context_enrichment_service",
        lambda *a, **kw: SimpleNamespace(enrich=capture),
    )
    args = [
        "document",
        "enrich-context",
        "IEC61508-0",
        "--workspace",
        str(workspace),
        "--fail-on-failure",
    ]
    first = CliRunner().invoke(app, args)
    assert first.exit_code == 0, first.output
    result = results[0]
    assert result.context_enrichment_failures == 0
    assert len(gateway.requests) == 1  # No retry needed for a proven informational passage.
    assert not result.document.clauses[0].context_routing.scopes
    references = result.document.clauses[0].context_routing.references
    assert len(references) == 4 and all(edge.role == "other" for edge in references)
    assert {edge.target.clause_id for edge in references} == {"p0-A", "p2-7", "p3-7", None}
    assert not result.unresolved_scope_targets
    assert len(result.unresolved_reference_targets) == 1
    context = gateway.requests[0]["messages"][1]["content"]
    assert '"range_start": "61508"' not in context
    assert "IEC 61508-3 Clause 7" in context
    reports = workspace / "evaluation/context-routing"
    report = json.loads((reports / "IEC61508-0-unresolved-targets.json").read_text())
    assert not report["unresolved_scope_targets"]
    assert report["unresolved_reference_targets"][0]["evidence"]
    corrections = reports / "IEC61508-0-routing-corrections.json"
    assert len(json.loads(corrections.read_text())["corrections"]) == 3
    before_audit = corrections.read_bytes()
    path = workspace / "documents/IEC61508-0.json"
    before = path.read_bytes()
    second = CliRunner().invoke(app, args)
    assert second.exit_code == 0, second.output
    assert results[-1].routing_reused == 1
    assert len(gateway.requests) == 1 and path.read_bytes() == before
    assert corrections.read_bytes() == before_audit


def test_info_target_without_catalogued_document_is_not_validated_as_scope(tmp_path):
    text = "For further information see Figure 2 of IEC 61508-9."
    source = document("0", ("4.9",), text)
    response = {
        "scope_declarations": [scope(["IEC 61508-9 Figure 2"], text)],
        "reference_routings": [],
    }
    repo = FileSystemEngineeringDocumentRepository(tmp_path / "workspace")
    real_service, gateway = service(repo, [response], tmp_path / "cache", source)
    result = real_service.enrich(source.key.value)
    assert result.context_enrichment_failures == 0
    assert len(gateway.requests) == 1
    routing = result.document.clauses[0].context_routing
    assert not routing.scopes
    assert routing.references[0].target.reference == "IEC 61508-9 Figure 2"
    assert routing.references[0].target.clause_id is None
    assert routing.references[0].target.document_key is None


def test_mixed_context_requires_governing_evidence_and_corrective_reply(tmp_path):
    instruction = "The restrictions apply to Table 1."
    source = document("0", ("4.9", "A"), FAQ + "\n\n" + instruction)
    bad = {"scope_declarations": [scope(["Table 1"], FAQ)], "reference_routings": []}
    good = {"scope_declarations": [scope(["Table 1"], instruction)], "reference_routings": []}
    repo = FileSystemEngineeringDocumentRepository(tmp_path / "workspace")
    real_service, gateway = service(repo, [bad, good], tmp_path / "cache", source)
    result = real_service.enrich(source.key.value)
    assert result.context_enrichment_failures == 0
    assert len(gateway.requests) == 2
    assert "governing statement" in gateway.requests[1]["messages"][0]["content"]
    assert result.document.clauses[0].context_routing.scopes[0].evidence == (instruction,)


def test_persistent_semantic_failure_does_not_publish_an_empty_success(tmp_path):
    source = document("0", ("4.9", "A"), FAQ + "\n\nThe restrictions apply to Table 1.")
    bad = {"scope_declarations": [scope(["Table 1"], FAQ)], "reference_routings": []}
    repo = FileSystemEngineeringDocumentRepository(tmp_path / "workspace")
    real_service, gateway = service(repo, [bad, bad], tmp_path / "cache", source)
    result = real_service.enrich(source.key.value)
    assert len(gateway.requests) == 2
    assert result.context_enrichment_failures == 1
    provenance = result.document.clauses[0].provenance
    assert provenance.availability("enrichments.context_routing") == "not_evaluated"
    assert "governing statement" in result.routing_failures[0]["error"]
