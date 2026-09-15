import json

import pytest

import standards_atlas.adapters.filesystem.knowledge_proposal_repository as repository_module
from standards_atlas.adapters.filesystem import FileSystemDocumentKnowledgeProposalRepository
from standards_atlas.domain.model import DocumentKnowledgeProposal, KnowledgeProposalProvenance


def _proposal(run_id: str, document_key: str) -> DocumentKnowledgeProposal:
    return DocumentKnowledgeProposal(
        proposal_run_id=run_id,
        source_document_key=document_key,
        proposal_provenance=KnowledgeProposalProvenance(
            extractor="test-extractor",
            extractor_version="1.0.0",
        ),
    )


def test_round_trip_is_scoped_by_run_and_document(tmp_path) -> None:
    repository = FileSystemDocumentKnowledgeProposalRepository(tmp_path)
    first = _proposal("run-001", "IEC61508-3")
    second = _proposal("run-002", "IEC61508-3")

    repository.save(first)
    repository.save(second)

    assert repository.load("run-001", "IEC61508-3") == first
    assert repository.load("run-002", "IEC61508-3") == second
    assert (tmp_path / "knowledge-proposals" / "run-001" / "IEC61508-3.json").is_file()


def test_missing_proposal_returns_none(tmp_path) -> None:
    repository = FileSystemDocumentKnowledgeProposalRepository(tmp_path)

    assert repository.load("missing-run", "IEC61508-3") is None


def test_reader_rejects_invalid_envelope_and_nested_schema_markers(tmp_path) -> None:
    repository = FileSystemDocumentKnowledgeProposalRepository(tmp_path)
    proposal = _proposal("run-001", "IEC61508-3")
    repository.save(proposal)
    path = tmp_path / "knowledge-proposals" / "run-001" / "IEC61508-3.json"

    original = json.loads(path.read_text(encoding="utf-8"))
    for target_key in (None, "proposal"):
        payload = json.loads(json.dumps(original))
        target = payload if target_key is None else payload[target_key]
        target["schema_version"] = "1"
        path.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(ValueError, match="schema[ _]version"):
            repository.load("run-001", "IEC61508-3")


def test_writer_rejects_registry_drift_before_replacing_existing_proposal(
    tmp_path,
    monkeypatch,
) -> None:
    repository = FileSystemDocumentKnowledgeProposalRepository(tmp_path)
    proposal = _proposal("run-001", "IEC61508-3")
    repository.save(proposal)
    path = tmp_path / "knowledge-proposals" / "run-001" / "IEC61508-3.json"
    before = path.read_bytes()

    monkeypatch.setattr(repository_module, "CURRENT_DOCUMENT_KNOWLEDGE_PROPOSAL_SCHEMA_VERSION", 2)
    with pytest.raises(ValueError, match="writers may only emit"):
        repository.save(proposal)
    assert path.read_bytes() == before
