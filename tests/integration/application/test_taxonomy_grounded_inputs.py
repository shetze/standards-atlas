"""Full-output source-context integration through the unchanged gateway and workbench."""

import json
from pathlib import Path
from types import SimpleNamespace

from standards_atlas.adapters.evaluation import EngineeringDocumentClauseProvider
from standards_atlas.application.context.canonical_cbox import canonical_cbox_context
from standards_atlas.application.evaluation.repository import PromptRepository
from standards_atlas.application.ports.llm_gateway import LlmHealth, StructuredGenerationResult
from standards_atlas.application.prompt_workbench.compiler import PromptCompiler
from standards_atlas.application.prompt_workbench.context import ClausePromptContextAssembler
from standards_atlas.application.semantic_qualification.proposals import (
    BaselineProposalGenerator,
    ProposalRunConfig,
    SemanticTaskRepository,
)
from standards_atlas.application.semantic_qualification.request_builder import (
    build_proposal_request,
)
from standards_atlas.application.services.cbox_report_service import CBoxReportService
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    DocumentKey,
    DocumentType,
    EngineeringDocument,
    StandardReference,
    TextBlock,
)
from standards_atlas.domain.model.knowledge_state import (
    GeneratedAttribute,
    GenerationMethod,
    KnowledgeStateProvenance,
)

RESOURCES = Path("src/standards_atlas/resources/semantic")


def descriptor(*, excluded_heading=False):
    clause = Clause(
        id=ClauseId(value="term"),
        clause_type=ClauseType.TERM,
        reference=StandardReference(standard="TEST", clause="3.1"),
        heading="LEAK-INTERPRETED-HEADING" if excluded_heading else "process",
        content=(TextBlock(id="text", text="A sequence of activities.\nNOTE: Source note."),),
    ).confirm_authoritative("clause_type", authority="baseline-review")
    if excluded_heading:
        clause = clause.model_copy(
            update={
                "provenance": KnowledgeStateProvenance(
                    generated_attributes=(
                        GeneratedAttribute(
                            path="baseline.heading",
                            generator="old-model",
                            method=GenerationMethod.LLM,
                        ),
                    ),
                )
            }
        )
    document = EngineeringDocument(
        key=DocumentKey(value="TEST"),
        title="Test",
        document_type=DocumentType.OTHER,
        clauses=(clause,),
    )
    return EngineeringDocumentClauseProvider._clause_descriptor(document, clause)


def configuration():
    return ProposalRunConfig(
        corpus_id="semantic-profile-v1",
        task="semantic-profile-classification",
        task_version="2.5.0",
        dataset_version="2.2.0",
        prompt_version="taxonomy-grounded-v1",
        cbox_frame="taxonomy-grounded-v1",
        provider="fake",
        model="test-model",
        max_tokens=512,
    )


class RecordingGateway:
    def __init__(self):
        self.requests = []

    def health(self):
        return LlmHealth(True, ("test-model",))

    def generate_structured(self, request):
        self.requests.append(request)
        return StructuredGenerationResult(
            value={
                "statement_functions": ["definition", "note"],
                "primary_function": "definition",
                "knowledge_kinds": ["process"],
                "primary_knowledge_kind": "process",
                "process_functions": [],
                "primary_process_function": None,
                "applicability_present": False,
                "role_semantics_present": False,
                "role_relations": [],
                "confidence": 0.9,
                "rationale": "Defines a process.",
            },
            model="test-model",
            provider="fake",
            prompt_version=request.prompt_version,
            input_hash="request-hash",
            raw_response_hash="response-hash",
            duration_ms=12,
            raw_response={"fake": True},
        )


def test_full_output_generation_reuses_hidden_changes_but_not_changed_source(tmp_path):
    clause = descriptor()
    example = {
        "id": clause.id,
        "input": {
            "content": {"text": clause.text, "hash": clause.content_hash},
            "context": canonical_cbox_context(clause),
        },
        "expected": {},
    }
    cfg = configuration()
    dataset = {"task": cfg.task, "version": cfg.dataset_version, "examples": [example]}
    root = tmp_path / "corpus"
    path = root / cfg.task / cfg.dataset_version / "dataset.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(dataset))
    gateway = RecordingGateway()
    generator = BaselineProposalGenerator(gateway)
    kwargs = {"resources": RESOURCES, "corpus_root": root, "output_root": tmp_path / "runs"}
    result = generator.run(cfg, **kwargs)
    assert result.generated == 1 and result.failed == 0
    assert len(gateway.requests) == 1  # No Slice-4 partial requests or zero-call shortcuts yet.
    request = gateway.requests[0]
    assert set(request.output_schema["required"]) <= set(
        json.loads((result.run_directory / clause.id / "response.json").read_text())["value"]
    )
    assert clause.text in request.user_prompt
    assert "confirmed" in request.user_prompt
    assert "clause_type" in request.user_prompt
    assert not (result.run_directory / clause.id / "interview.json").exists()
    saved = json.loads((result.run_directory / clause.id / "request.json").read_text())
    assert saved["metadata"]["framed_cbox"] == dict(request.metadata["framed_cbox"])
    source = example["input"]["context"]
    source["semantic"] = {"primary_function": "LEAK"}
    source["expected"] = {"applicability_present": True}
    path.write_text(json.dumps(dataset))
    resumed = generator.run(cfg, **kwargs)
    assert resumed.reused_predictions == 1
    assert len(gateway.requests) == 1
    for fact in source["source_structure"]["facts"]:
        if fact["field"] == "heading":
            fact["value"] = "Updated source heading"
    source["heading"] = "Updated source heading"
    path.write_text(json.dumps(dataset))
    refreshed = generator.run(cfg, **kwargs)
    assert refreshed.generated == 1 and refreshed.failed == 0
    assert len(gateway.requests) == 2
    assert "Updated source heading" in gateway.requests[-1].user_prompt
    assert "LEAK" not in gateway.requests[-1].user_prompt


def test_workbench_and_canonical_report_use_the_same_source_projection():
    clause = descriptor()
    cfg = configuration()
    prompt = PromptRepository(RESOURCES / "prompts").load(cfg.task, cfg.prompt_version)
    task, _ = SemanticTaskRepository(RESOURCES / "tasks").load(cfg.task, cfg.task_version)
    request = build_proposal_request(
        cfg,
        prompt,
        {
            "content": {"text": clause.text, "hash": clause.content_hash},
            "context": canonical_cbox_context(clause),
        },
        task,
    )
    assembled = ClausePromptContextAssembler().assemble(clause, variant_id=cfg.cbox_frame)
    compiled = PromptCompiler().compile(prompt, assembled)
    assert compiled.user_prompt == request.user_prompt
    assert assembled.selected_context == request.metadata["framed_cbox"]
    provider = SimpleNamespace(
        list_documents=lambda: (SimpleNamespace(key="TEST"),),
        list_clauses=lambda **_: (clause,),
    )
    report = CBoxReportService(provider).build(frame=cfg.cbox_frame)
    assert report.clauses[0]["framed"] == assembled.selected_context
    assert report.clauses[0]["rendered"] == assembled.context_text


def test_workbench_alternate_variables_cannot_reintroduce_excluded_source_fields():
    clause = descriptor(excluded_heading=True)
    context = ClausePromptContextAssembler().assemble(
        clause,
        variant_id="taxonomy-grounded-v1",
        document_title="LEAK-UNSELECTED-TITLE",
    )
    assert context.values["heading"] == ""
    assert "LEAK" not in json.dumps(context.selected_context)
    assert "LEAK" not in context.values["metadata"]
    assert context.values["structural_context"] == "{}"
