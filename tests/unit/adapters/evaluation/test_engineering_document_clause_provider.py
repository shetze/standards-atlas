from pathlib import Path

import pytest

from standards_atlas.adapters.evaluation import EngineeringDocumentClauseProvider
from standards_atlas.adapters.filesystem import FileSystemEngineeringDocumentRepository
from standards_atlas.application.semantic_qualification.clause_access import (
    ClauseFilter,
    SamplingStrategy,
)
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    DocumentKey,
    DocumentType,
    EngineeringDocument,
    SemanticClassification,
    StandardReference,
    StatementFunction,
    TextBlock,
)


def _clause(
    clause_id: str,
    document: str,
    reference: str,
    text: str,
    *,
    function: StatementFunction = StatementFunction.REQUIREMENT,
) -> Clause:
    return Clause(
        id=ClauseId(value=clause_id),
        reference=StandardReference(standard=document, year=2024, clause=reference),
        clause_type=ClauseType.REQUIREMENT,
        heading=f"Clause {reference}",
        content=(TextBlock(id=f"{clause_id}-text", text=text),),
        semantic_classification=SemanticClassification(statement_functions=(function,)),
    )


def _save_documents(workspace: Path) -> None:
    repository = FileSystemEngineeringDocumentRepository(workspace)
    repository.save(
        EngineeringDocument(
            key=DocumentKey(value="alpha:2024"),
            title="Alpha",
            document_type=DocumentType.OTHER,
            year=2024,
            clauses=(
                _clause("alpha-1", "ALPHA", "1", "The supplier shall verify the result."),
                _clause("alpha-2", "ALPHA", "2", "An informative example."),
            ),
        )
    )
    repository.save(
        EngineeringDocument(
            key=DocumentKey(value="beta"),
            title="Beta",
            document_type=DocumentType.SPECIFICATION,
            clauses=(
                _clause("beta-1", "BETA", "4.2", "The operator shall record evidence."),
                _clause("beta-2", "BETA", "5", "Verification shall be independent."),
            ),
        )
    )


def test_lists_documents_and_resolves_clause(tmp_path: Path) -> None:
    _save_documents(tmp_path)
    provider = EngineeringDocumentClauseProvider(tmp_path)

    documents = provider.list_documents()

    assert [document.key for document in documents] == ["alpha:2024", "beta"]
    assert documents[0].clause_count == 2
    assert provider.get_clause("beta-1").document_key == "beta"


def test_filters_and_searches_clauses(tmp_path: Path) -> None:
    _save_documents(tmp_path)
    provider = EngineeringDocumentClauseProvider(tmp_path)

    clauses = provider.list_clauses(
        filters=ClauseFilter(document_keys=("beta",), min_text_length=30)
    )
    matches = provider.search_clauses("independent verification")

    assert [clause.id for clause in clauses] == ["beta-1", "beta-2"]
    assert [clause.id for clause in matches] == ["beta-2"]


def test_sampling_is_reproducible_and_balanced(tmp_path: Path) -> None:
    _save_documents(tmp_path)
    provider = EngineeringDocumentClauseProvider(tmp_path)

    first = provider.sample_clauses(count=3, seed=17)
    second = provider.sample_clauses(count=3, seed=17)
    balanced = provider.sample_clauses(
        count=2,
        strategy=SamplingStrategy.BALANCED_BY_DOCUMENT,
        seed=4,
    )

    assert first == second
    assert {clause.document_key for clause in balanced} == {"alpha:2024", "beta"}


def test_rejects_unknown_clause_and_oversized_sample(tmp_path: Path) -> None:
    _save_documents(tmp_path)
    provider = EngineeringDocumentClauseProvider(tmp_path)

    with pytest.raises(KeyError, match="Unknown clause id"):
        provider.get_clause("missing")
    with pytest.raises(ValueError, match="exceeds matching population"):
        provider.sample_clauses(count=5)
