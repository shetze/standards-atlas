from __future__ import annotations

import json
from pathlib import Path

from standards_atlas.adapters.evaluation import ResourcePromptCatalog
from standards_atlas.adapters.llm import OntologyGuidedKnowledgeProposalExtractor
from standards_atlas.application.evaluation.source_bound_prompt import semantic_prompt_repository
from standards_atlas.application.ports.llm_gateway import StructuredGenerationResult
from standards_atlas.application.prompt_workbench.models import (
    ModelCatalogEntry,
    SourceBoundKnowledgeExperimentRequest,
)
from standards_atlas.application.prompt_workbench.service import PromptExperimentService
from standards_atlas.application.semantic_qualification.clause_access import (
    ClauseDescriptor,
    DocumentDescriptor,
)
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    DocumentKey,
    DocumentType,
    EngineeringDocument,
    EvidenceSourceKind,
    ReferenceMention,
    ReferenceMentionKind,
    ReferenceResolutionStatus,
    StandardReference,
    TextBlock,
)

PROMPT_ROOT = Path("src/standards_atlas/resources/semantic/prompts")
ONTOLOGIES = ("standards-atlas-core@2.0.0", "functional-safety@2.1.0")
PROMPT = "engineering-policy-v1"
MODEL_REF = "hf.co/example/model:Q4"
STAT = "http://lunetix.org/standards-atlas#"


def _fixture() -> tuple[EngineeringDocument, Clause, ClauseDescriptor]:
    parent = Clause(
        id=ClauseId(value="parent"),
        reference=StandardReference(standard="TEST", year=2026, clause="5"),
        clause_type=ClauseType.CLAUSE,
        heading="Verification records",
    )
    unresolved = ReferenceMention(
        kind=ReferenceMentionKind.CLAUSE,
        surface_text="9.9",
        start_offset=57,
        end_offset=60,
        reference="9.9",
        status=ReferenceResolutionStatus.UNRESOLVED,
    )
    target = Clause(
        id=ClauseId(value="target"),
        reference=StandardReference(standard="TEST", year=2026, clause="5.1"),
        clause_type=ClauseType.REQUIREMENT,
        parent_id=parent.id,
        content=(
            TextBlock(
                id="target-body",
                text="The rationale shall be recorded only when the option is excluded. See 9.9.",
            ),
        ),
        reference_mentions=(unresolved,),
    )
    document = EngineeringDocument(
        key=DocumentKey(value="TEST"),
        title="Synthetic test standard",
        document_type=DocumentType.STANDARD,
        clauses=(parent, target),
    )
    descriptor = ClauseDescriptor(
        id="target",
        document_key="TEST",
        reference="TEST:2026 5.1",
        clause_reference="5.1",
        content_hash="sha256:" + "a" * 64,
        clause_type=ClauseType.REQUIREMENT,
        text=target.plain_text,
        parent_id="parent",
        ancestor_headings=(
            {"clause_id": "parent", "reference": "5", "heading": "Verification records"},
        ),
    )
    return document, target, descriptor


class Clauses:
    def __init__(self, descriptor: ClauseDescriptor) -> None:
        self.descriptor = descriptor

    def get_clause(self, clause_id):
        if clause_id != self.descriptor.id:
            raise KeyError(clause_id)
        return self.descriptor

    def list_clauses(self, *, filters=None, limit=None, offset=0):
        del filters
        values = (self.descriptor,)
        end = None if limit is None else offset + limit
        return values[offset:end]

    def list_documents(self):
        return (
            DocumentDescriptor(
                key="TEST",
                title="Synthetic test standard",
                document_type=DocumentType.STANDARD,
                year=2026,
                clause_count=2,
            ),
        )


class Documents:
    def __init__(self, document: EngineeringDocument) -> None:
        self.document = document

    def load(self, key):
        assert key == self.document.key
        return self.document


class Models:
    model = ModelCatalogEntry(id="model", model_ref=MODEL_REF)

    def get_model(self, model_id):
        assert model_id == self.model.id
        return self.model


class NeverGateway:
    calls = 0

    def generate_structured(self, request):
        self.calls += 1
        raise AssertionError("model gateway must not be called by preview")


class EmptyGateway:
    def __init__(self) -> None:
        self.request = None

    def generate_structured(self, request):
        self.request = request
        return StructuredGenerationResult(
            value={"entities": [], "assertions": []},
            model=request.model or "",
            provider="fake",
            prompt_version=request.prompt_version,
            input_hash="i" * 64,
            raw_response_hash="r" * 64,
            duration_ms=1,
        )


class BadGroundingGateway:
    def __init__(self) -> None:
        self.calls = 0

    def generate_structured(self, request):
        self.calls += 1
        payload = json.loads(request.user_prompt)
        body_ref = next(
            item["source_ref"]
            for item in payload["source_package"]["source_surfaces"]
            if item["clause_id"] == "target" and item["source_kind"] == "body"
        )
        return StructuredGenerationResult(
            value={
                "entities": [
                    {
                        "class_iri": f"{STAT}EngineeringRecord",
                        "label": "exclusion rationale record",
                        "confidence": 0.9,
                        "evidence": [
                            {
                                "source_ref": body_ref,
                                "exact_quote": "text that is not in the delivered surface",
                                "selector": {"kind": "unique"},
                                "contribution": "direct_statement",
                            }
                        ],
                        "rationale": None,
                    }
                ],
                "assertions": [],
            },
            model=request.model or "",
            provider="fake",
            prompt_version=request.prompt_version,
            input_hash="i" * 64,
            raw_response_hash="r" * 64,
            duration_ms=1,
        )


def _service(gateway):
    document, _, descriptor = _fixture()
    repository = semantic_prompt_repository()
    return PromptExperimentService(
        clauses=Clauses(descriptor),
        prompts=ResourcePromptCatalog(PROMPT_ROOT, repository=repository),
        models=Models(),
        gateway=gateway,
        documents=Documents(document),
        source_bound_prompt_repository=repository,
    )


def _request() -> SourceBoundKnowledgeExperimentRequest:
    return SourceBoundKnowledgeExperimentRequest(
        clause_identifier="target",
        prompt_version=PROMPT,
        model_id="model",
        ontology_versions=ONTOLOGIES,
    )


def test_source_bound_preview_is_model_free_and_keeps_heading_and_missing_source_diagnostics() -> (
    None
):
    gateway = NeverGateway()
    preview = _service(gateway).preview_source_bound_knowledge(_request())

    assert gateway.calls == 0
    assert preview.generation_request.task == "formal-semantic-knowledge-proposal"
    assert preview.generation_request.prompt_version == PROMPT
    assert preview.generation_request.metadata["preview_only"] is True
    assert any(
        surface.identity.clause_id == "parent"
        and surface.source_ref.source_kind is EvidenceSourceKind.HEADING
        and surface.text == "Verification records"
        for surface in preview.source_package.input_surfaces
    )
    assert any(gap.code == "unresolved_reference" for gap in preview.source_package.selection.gaps)


def test_workbench_preview_and_productive_extractor_have_same_fachliche_request_and_binding() -> (
    None
):
    document, target, _ = _fixture()
    workbench_preview = _service(NeverGateway()).preview_source_bound_knowledge(_request())

    gateway = EmptyGateway()
    productive = OntologyGuidedKnowledgeProposalExtractor(
        gateway,
        model=MODEL_REF,
        prompt_version=PROMPT,
        prompt_repository=semantic_prompt_repository(),
    ).extract(
        target,
        document_key="TEST",
        ontology_versions=ONTOLOGIES,
        source_package=workbench_preview.source_package,
        interpretation_context=workbench_preview.interpretation_context,
    )

    assert gateway.request.task == workbench_preview.generation_request.task
    assert gateway.request.prompt_version == workbench_preview.generation_request.prompt_version
    assert gateway.request.system_prompt == workbench_preview.generation_request.system_prompt
    assert gateway.request.user_prompt == workbench_preview.generation_request.user_prompt
    assert gateway.request.output_schema == workbench_preview.generation_request.output_schema
    assert (
        productive.source_package_binding.package_sha256
        == workbench_preview.generation_request.metadata["source_package_sha256"]
    )


def test_schema_valid_but_wrong_grounding_is_explicitly_not_technical_success() -> None:
    gateway = BadGroundingGateway()
    result = _service(gateway).run_source_bound_knowledge(_request())

    assert gateway.calls == 1
    assert result.schema_valid is True
    assert result.parser_error is None
    assert result.proposal_result is not None
    assert result.proposal_result.entity_proposals == ()
    assert result.proposal_result.violations
    assert any("quote_not_found" in item.reason for item in result.proposal_result.violations)
