"""Source provenance survives canonical projection without changing current prompts."""

import copy
import json
from types import SimpleNamespace

import pytest

from standards_atlas.adapters.evaluation import EngineeringDocumentClauseProvider
from standards_atlas.adapters.filesystem import FileSystemEngineeringDocumentRepository
from standards_atlas.application.context.canonical_cbox import canonical_cbox_context
from standards_atlas.application.evaluation.models import PromptDefinition
from standards_atlas.application.semantic_qualification.context_framing import (
    list_cbox_frame_policies,
)
from standards_atlas.application.semantic_qualification.request_builder import (
    build_proposal_request,
)
from standards_atlas.application.semantic_qualification.taxonomy_decisions import (
    derive_clause_decision_plan,
)
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
from standards_atlas.domain.model.structural_profile import DomainCategory, StructuralProfile


def descriptor():
    parent = Clause(
        id=ClauseId(value="parent"),
        clause_type=ClauseType.TOC,
        reference=StandardReference(standard="TEST", clause="3"),
        heading="Terms and definitions",
    )
    clause = Clause(
        id=ClauseId(value="term"),
        clause_type=ClauseType.TERM,
        reference=StandardReference(standard="TEST", clause="3.1"),
        heading="process",
        parent_id=parent.id,
        content=(TextBlock(id="text", text="A sequence of activities."),),
        structural_profile=StructuralProfile(
            document_categories=(
                DomainCategory(
                    taxonomy="document.iec-directives-2", category="terminology", version="1.0.0"
                ),
            )
        ),
    ).confirm_authoritative("clause_type", "baseline.heading", authority="reviewed-source")
    document = EngineeringDocument(
        key=DocumentKey(value="TEST"),
        title="Test",
        document_type=DocumentType.OTHER,
        clauses=(parent, clause),
    )
    return document, EngineeringDocumentClauseProvider._clause_descriptor(document, clause)


def test_descriptor_records_baseline_paths_parent_identity_and_taxonomy_version():
    _, value = descriptor()
    source = value.source_structure
    assert source is not None
    facts = {fact.field: fact for fact in source.facts}
    assert facts["parent_id"].value == "parent"
    assert facts["ancestor_heading"].source_clause_id == "parent"
    assert facts["ancestor_heading"].distance == 1
    assert facts["ancestor_heading"].source_path == "baseline.heading"
    assert facts["clause_type"].origin == "confirmed"
    assert facts["clause_type"].authority == "reviewed-source"
    assert facts["document_categories"].value[0]["version"] == "1.0.0"
    context = canonical_cbox_context(value)
    assert "title" not in context
    assert all("title" not in item for item in context["ancestor_headings"])
    plan = derive_clause_decision_plan(context, text=value.text, content_hash=value.content_hash)
    assert plan.decision("primary_function").value == "definition"


def test_provider_is_read_only_and_does_not_publish_a_source_plan(tmp_path):
    document, _ = descriptor()
    repository = FileSystemEngineeringDocumentRepository(tmp_path)
    repository.save(document)
    before = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    item = EngineeringDocumentClauseProvider(tmp_path).get_clause("term")
    derive_clause_decision_plan(canonical_cbox_context(item), text=item.text)
    assert {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()} == before
    assert "source_structure" not in repository.load(document.key).model_dump_json()


@pytest.mark.parametrize(
    "frame",
    [f"{item.id}-v{item.version}" for item in list_cbox_frame_policies()],
)
def test_added_structure_contract_does_not_change_current_model_input_or_cache_fingerprint(frame):
    _, value = descriptor()
    context = canonical_cbox_context(value)
    without = copy.deepcopy(context)
    without.pop("source_structure")
    config = SimpleNamespace(
        task="semantic-profile-classification",
        prompt_version="test",
        model="model",
        corpus_id="corpus",
        dataset_version="1.0.0",
        temperature=0.0,
        seed=1,
        max_tokens=256,
        reasoning_enabled=False,
        cbox_frame=frame,
    )
    prompt = PromptDefinition(
        task=config.task,
        version="test",
        system_prompt="classify",
        user_template="{content}\n{context_text}",
        output_schema={},
    )
    requests = [
        build_proposal_request(
            config,
            prompt,
            {
                "content": {"text": value.text, "hash": value.content_hash},
                "context": item,
            },
            SimpleNamespace(version="1.0.0"),
        )
        for item in (context, without)
    ]
    assert requests[0].user_prompt == requests[1].user_prompt
    assert (
        requests[0].metadata["qualification_input_fingerprint"]
        == (requests[1].metadata["qualification_input_fingerprint"])
    )


def test_interpreted_descendant_does_not_hide_inside_a_structural_collection():
    document, _ = descriptor()
    term = document.clauses[1]
    term = term.model_copy(
        update={
            "provenance": KnowledgeStateProvenance(
                generated_attributes=(
                    GeneratedAttribute(
                        path="baseline.structural_profile.document_categories.0.category",
                        generator="old-llm",
                        method=GenerationMethod.LLM,
                    ),
                )
            )
        }
    )
    value = EngineeringDocumentClauseProvider._clause_descriptor(document, term)
    fact = next(
        item for item in value.source_structure.facts if item.field == "document_categories"
    )
    assert fact.origin == "excluded"
    assert fact.value is None


def test_structural_contract_cannot_encode_extra_interpretation_fields():
    _, value = descriptor()
    context = canonical_cbox_context(value)
    fact = next(
        item
        for item in context["source_structure"]["facts"]
        if item["field"] == "document_categories"
    )
    fact["value"][0]["semantic"] = {"primary_function": "LEAK"}
    with pytest.raises(ValueError, match="non-structural"):
        derive_clause_decision_plan(context, text=value.text)


def test_source_contract_rejects_unknown_schema():
    _, value = descriptor()
    context = canonical_cbox_context(value)
    context["source_structure"]["schema_version"] = "999"
    with pytest.raises(ValueError, match="schema version"):
        derive_clause_decision_plan(context, text=value.text)


def test_semantic_enrichment_mutation_does_not_change_projected_source_identity():
    _, value = descriptor()
    context = canonical_cbox_context(value)
    expected = derive_clause_decision_plan(context, text=value.text)
    context["semantic"] = {"primary_function": "LEAK", "applicability_present": True}
    context["attribute_sources"] = {"enrichments.semantic": {"origin": "confirmed"}}
    actual = derive_clause_decision_plan(context, text=value.text)
    assert actual.fingerprint == expected.fingerprint
    assert "LEAK" not in json.dumps(actual.model_dump(mode="json"))
