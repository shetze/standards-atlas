"""Concrete envelope writers must reject invalid markers before replacing bytes."""

from __future__ import annotations

import importlib
import json

import pytest

from standards_atlas.application.schema import SCHEMA_POLICIES, SchemaPolicy
from standards_atlas.domain.model import (
    DocumentKnowledgeProposal,
    FormalSemanticProjection,
    KnowledgeProposalProvenance,
)

CASES = (
    (
        "document-knowledge-proposal",
        "knowledge_proposal_repository",
        "FileSystemDocumentKnowledgeProposalRepository",
        "CURRENT_DOCUMENT_KNOWLEDGE_PROPOSAL_SCHEMA_VERSION",
        lambda: DocumentKnowledgeProposal(
            proposal_run_id="run-r5c",
            source_document_key="synthetic-r5c",
            proposal_provenance=KnowledgeProposalProvenance(
                extractor="test", extractor_version="1"
            ),
        ),
        "proposal",
        ("run-r5c", "synthetic-r5c"),
    ),
    (
        "formal-semantic-projection",
        "formal_semantic_projection_repository",
        "FileSystemFormalSemanticProjectionRepository",
        "CURRENT_FORMAL_SEMANTIC_PROJECTION_SCHEMA_VERSION",
        lambda: FormalSemanticProjection(source_document_key="synthetic-r4"),
        "projection",
        ("synthetic-r4",),
    ),
)


def fixture(tmp_path, case):
    family, module, cls, constant, factory, key, load_args = case
    module = importlib.import_module(f"standards_atlas.adapters.filesystem.{module}")
    repository = getattr(module, cls)(tmp_path)
    value = factory()
    repository.save(value)
    path = next(tmp_path.rglob("*.json"))
    return family, module, constant, repository, value, path, key, load_args


@pytest.mark.parametrize("case", CASES, ids=lambda c: c[0])
@pytest.mark.parametrize("marker", [None, True, 1.0, "1", 2])
def test_invalid_envelope_constant_does_not_replace_existing_artifact(
    tmp_path,
    monkeypatch,
    case,
    marker,
):
    _, module, constant, repo, value, path, _, _ = fixture(tmp_path, case)
    before = path.read_bytes()
    monkeypatch.setattr(module, constant, marker)
    with pytest.raises(ValueError, match="writers may only emit"):
        repo.save(value)
    assert path.read_bytes() == before
    assert list(path.parent.iterdir()) == [path]


@pytest.mark.parametrize("case", CASES, ids=lambda c: c[0])
def test_nested_invalid_marker_and_registry_drift_cannot_be_relabelled(tmp_path, monkeypatch, case):
    family, _, _, repo, value, path, _, _ = fixture(tmp_path, case)
    before = path.read_bytes()
    with pytest.raises(ValueError, match="writers may only emit"):
        repo.save(value.model_copy(update={"schema_version": 2}))
    monkeypatch.setitem(SCHEMA_POLICIES, family, SchemaPolicy(family, 2, (2,), "test"))
    with pytest.raises(ValueError, match="writers may only emit"):
        repo.save(value)
    assert path.read_bytes() == before


@pytest.mark.parametrize("case", CASES, ids=lambda c: c[0])
@pytest.mark.parametrize("marker", [None, True, 1.0, "1", 2])
@pytest.mark.parametrize("nested", [False, True])
def test_reader_checks_raw_markers_before_pydantic_can_coerce_them(tmp_path, case, marker, nested):
    _, _, _, repo, _, path, key, load_args = fixture(tmp_path, case)
    payload = json.loads(path.read_bytes())
    target = payload[key] if nested else payload
    if marker is None:
        target.pop("schema_version")
    else:
        target["schema_version"] = marker
    path.write_text(json.dumps(payload))
    before = path.read_bytes()
    with pytest.raises(ValueError, match="schema[ _]version"):
        repo.load(*load_args)
    assert path.read_bytes() == before
