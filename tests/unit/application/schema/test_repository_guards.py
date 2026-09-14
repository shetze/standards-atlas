"""Concrete envelope writers must reject invalid markers before replacing bytes."""

from __future__ import annotations

import importlib
import json

import pytest

from standards_atlas.application.schema import SCHEMA_POLICIES, SchemaPolicy
from standards_atlas.domain.model import DocumentSemanticExtraction, FormalSemanticProjection

CASES = (
    (
        "semantic-extraction",
        "semantic_extraction_repository",
        "FileSystemSemanticExtractionRepository",
        "CURRENT_SEMANTIC_EXTRACTION_SCHEMA_VERSION",
        DocumentSemanticExtraction,
        "extraction",
    ),
    (
        "formal-semantic-projection",
        "formal_semantic_projection_repository",
        "FileSystemFormalSemanticProjectionRepository",
        "CURRENT_FORMAL_SEMANTIC_PROJECTION_SCHEMA_VERSION",
        FormalSemanticProjection,
        "projection",
    ),
)


def fixture(tmp_path, case):
    family, module, cls, constant, model, key = case
    module = importlib.import_module(f"standards_atlas.adapters.filesystem.{module}")
    repository = getattr(module, cls)(tmp_path)
    value = model(source_document_key="synthetic-r4")
    repository.save(value)
    path = next(tmp_path.rglob("*.json"))
    return family, module, constant, repository, value, path, key


@pytest.mark.parametrize("case", CASES, ids=lambda c: c[0])
@pytest.mark.parametrize("marker", [None, True, 1.0, "1", 2])
def test_invalid_envelope_constant_does_not_replace_existing_artifact(
    tmp_path,
    monkeypatch,
    case,
    marker,
):
    _, module, constant, repo, value, path, _ = fixture(tmp_path, case)
    before = path.read_bytes()
    monkeypatch.setattr(module, constant, marker)
    with pytest.raises(ValueError, match="writers may only emit"):
        repo.save(value)
    assert path.read_bytes() == before
    assert list(path.parent.iterdir()) == [path]


@pytest.mark.parametrize("case", CASES, ids=lambda c: c[0])
def test_nested_invalid_marker_and_registry_drift_cannot_be_relabelled(tmp_path, monkeypatch, case):
    family, _, _, repo, value, path, _ = fixture(tmp_path, case)
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
    _, _, _, repo, _, path, key = fixture(tmp_path, case)
    payload = json.loads(path.read_bytes())
    target = payload[key] if nested else payload
    if marker is None:
        target.pop("schema_version")
    else:
        target["schema_version"] = marker
    path.write_text(json.dumps(payload))
    before = path.read_bytes()
    with pytest.raises(ValueError, match="schema[ _]version"):
        repo.load("synthetic-r4")
    assert path.read_bytes() == before
