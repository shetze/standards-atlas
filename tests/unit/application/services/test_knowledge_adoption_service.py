import pytest

from standards_atlas.application.model.knowledge_adoption import (
    ClauseKnowledgeCandidate,
    KnowledgeAdoptionBatch,
)
from standards_atlas.application.semantic_qualification.annotations import normalized_content_hash
from standards_atlas.application.services.knowledge_adoption_service import KnowledgeAdoptionService
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    DocumentKey,
    DocumentType,
    EngineeringDocument,
    GeneratedAttribute,
    GenerationMethod,
    StandardReference,
    TextBlock,
)
from standards_atlas.domain.model.enrichment_patch import (
    ClauseEnrichmentPatch,
    SemanticEnrichmentPatch,
)


def document(key="DOC"):
    return EngineeringDocument(
        key=DocumentKey(value=key),
        title=key,
        document_type=DocumentType.OTHER,
        clauses=tuple(
            Clause(
                id=ClauseId(value=f"c{index}"),
                reference=StandardReference(standard=key, clause=str(index)),
                clause_type=ClauseType.CLAUSE,
                content=(TextBlock(id=f"t{index}", text=f"Text {index}"),),
            )
            for index in (1, 2)
        ),
    )


def candidate(key="DOC"):
    return ClauseKnowledgeCandidate(
        document_key=key,
        clause_id="c1",
        reference="1",
        content_hash=normalized_content_hash("Text 1"),
        patch=ClauseEnrichmentPatch(semantic=SemanticEnrichmentPatch(applicability_present=True)),
        attributes=(
            GeneratedAttribute(
                path="enrichments.semantic.applicability_present",
                generator="policy",
                method=GenerationMethod.IMPORTED,
            ),
        ),
        not_evaluated=("enrichments.semantic.process_functions",),
    )


def batch(*candidates):
    return KnowledgeAdoptionBatch(
        source_id="run",
        source_sha256="a" * 64,
        selected_clause_count=len(candidates) + 1,
        unqualified_clause_count=1,
        candidates=candidates,
    )


class Documents:
    def __init__(self, *documents):
        self.documents = {item.key.value: item for item in documents}
        self.saves = []

    def load(self, key):
        if key.value not in self.documents:
            raise FileNotFoundError(key.value)
        return self.documents[key.value]

    def save(self, doc):
        self.saves.append(doc.key.value)
        self.documents[doc.key.value] = doc


def test_preview_never_writes_and_replay_never_resaves():
    docs = Documents(document())
    service = KnowledgeAdoptionService(documents=docs)
    first = service.apply(batch(candidate()))
    assert first.changed_document_keys == ("DOC",)
    assert docs.saves == []
    written = service.apply(batch(candidate()), write=True)
    assert written.written_document_keys == ("DOC",)
    assert docs.documents["DOC"].clauses[1] == document().clauses[1]
    again = service.apply(batch(candidate()), write=True)
    assert again.changed_document_keys == ()
    assert docs.saves == ["DOC"]
    assert again.unqualified_clause_count == 1
    assert again.status_counts["not_evaluated"] == 1


@pytest.mark.parametrize(
    "change",
    [
        {"reference": "wrong"},
        {"content_hash": "sha256:" + "0" * 64},
        {"clause_id": "missing"},
        {"heading": "changed"},
    ],
)
def test_all_documents_are_preflighted_before_first_write(change):
    docs = Documents(document("A"), document("Z"))
    service = KnowledgeAdoptionService(documents=docs)
    with pytest.raises(ValueError):
        service.apply(batch(candidate("A"), candidate("Z").model_copy(update=change)), write=True)
    assert docs.saves == []


def test_document_selection_does_not_require_unselected_targets():
    docs = Documents(document("A"))
    result = KnowledgeAdoptionService(documents=docs).apply(
        batch(candidate("A"), candidate("Z")),
        document_keys=("A",),
        write=True,
    )
    assert result.addressed_clause_count == 1
    assert docs.saves == ["A"]


def test_missing_document_is_not_created_from_archived_text():
    docs = Documents()
    with pytest.raises(FileNotFoundError):
        KnowledgeAdoptionService(documents=docs).apply(batch(candidate()), write=True)
    assert docs.saves == []


def test_protected_value_is_reported_and_not_confirmed_by_acceptance():
    doc = document()
    doc = doc.model_copy(
        update={
            "clauses": (
                doc.clauses[0].confirm_authoritative("enrichments.semantic.applicability_present"),
                doc.clauses[1],
            )
        }
    )
    docs = Documents(doc)
    result = KnowledgeAdoptionService(documents=docs).apply(batch(candidate()), write=True)
    assert result.status_counts["protected"] == 1
    assert docs.saves == []


def test_report_serialization_preserves_explicit_false_and_no_text_in_provenance():
    docs = Documents(document())
    report = KnowledgeAdoptionService(documents=docs).apply(batch(candidate()))
    payload = report.model_dump_json()
    assert '"before":false' in payload
    assert '"after":true' in payload
    assert "Text 1" not in payload
