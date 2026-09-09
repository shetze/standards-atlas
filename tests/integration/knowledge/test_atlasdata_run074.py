"""Opt-in test against real AtlasData identities and the private qualification archive."""

from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from pathlib import Path
from shutil import copy2
from zipfile import ZipFile

import pytest

from standards_atlas.adapters.atlasdata.knowledge_transfer import AtlasDataKnowledgeService
from standards_atlas.adapters.catalog import YamlStandardCatalogReader
from standards_atlas.adapters.evaluation.qualification_knowledge_source import (
    load_qualification_knowledge,
)
from standards_atlas.adapters.filesystem import FileSystemEngineeringDocumentRepository
from standards_atlas.application.catalog.atlasdata_binding import atlasdata_bindings
from standards_atlas.application.context.canonical_cbox import project_clause_enrichments
from standards_atlas.application.services.knowledge_adoption_service import KnowledgeAdoptionService
from standards_atlas.domain.model import DocumentKey, TextBlock


@pytest.mark.qualification
def test_run074_atlasdata_roundtrip_uses_real_physical_identifiers(tmp_path):
    archive = os.environ.get("STANDARDS_ATLAS_RUN074_ARCHIVE")
    if not archive:
        pytest.skip("set STANDARDS_ATLAS_RUN074_ARCHIVE to the private qualification ZIP")
    project = Path(__file__).resolve().parents[3]
    catalog = YamlStandardCatalogReader().read(project / "manifests/standards.yaml")
    source_bindings = atlasdata_bindings(catalog, root=project)
    for binding in source_bindings.values():
        relative = binding.source.relative_to(project)
        (tmp_path / relative).parent.mkdir(parents=True, exist_ok=True)
        copy2(binding.source, tmp_path / relative)
    bindings = atlasdata_bindings(catalog, root=tmp_path)
    repo = FileSystemEngineeringDocumentRepository(tmp_path / ".atlas/data")
    service = AtlasDataKnowledgeService(
        documents=repo,
        bindings=bindings,
        evidence_root=tmp_path / ".atlas/data/knowledge-evidence",
    )
    batch = load_qualification_knowledge(Path(archive))
    with ZipFile(archive) as zipped:
        name = next(
            p for p in zipped.namelist() if p.endswith("qualification-dataset-snapshot.json")
        )
        examples = json.loads(zipped.read(name))["examples"]
    grouped = defaultdict(dict)
    for example in examples:
        context = example["input"]["context"]
        grouped[context["document_key"]][context["clause_id"]] = example
    changed_headings = 0
    for key, cases in grouped.items():
        document = service._skeleton(bindings[key])
        clauses = []
        found = set()
        for clause in document.clauses:
            example = cases.get(clause.id.value)
            if example is not None:
                found.add(clause.id.value)
                context = example["input"]["context"]
                assert context["reference"] == clause.reference.clause
                changed_headings += (context.get("heading") or "") != (clause.heading or "")
                # Archive-derived private source evidence, not a rewrite of public AtlasData.
                clause = clause.with_baseline_updates(
                    heading=context.get("heading"),
                    content=(
                        TextBlock(
                            id="local-archive",
                            text=example["input"]["content"]["text"],
                        ),
                    ),
                )
            clauses.append(clause)
        assert found == set(cases)
        repo.save(document.model_copy(update={"clauses": tuple(clauses)}))
    KnowledgeAdoptionService(documents=repo).apply(batch, write=True)
    selected = {(item.document_key, item.clause_id) for item in batch.candidates}
    original = {
        (document.key.value, clause.id.value): (clause.enrichments, clause.provenance)
        for document in repo.list()
        for clause in document.clauses
        if (document.key.value, clause.id.value) in selected
    }
    cbox_original = {
        (document.key.value, clause.id.value): project_clause_enrichments(clause)
        for document in repo.list()
        for clause in document.clauses
        if (document.key.value, clause.id.value) in selected
    }
    structures = {b.source: b.source.read_bytes() for b in bindings.values()}
    result = service.export(write=True)
    public = {
        b.enrichments_path: b.enrichments_path.read_bytes()
        for b in bindings.values()
        if b.enrichments_path.exists()
    }
    assert len(public) == 26
    assert not service.export(write=True).written_targets
    for key in grouped:
        repo.delete(DocumentKey(value=key))
    restored = service.import_(write=True, strict_evidence=True)
    assert len(restored.written_targets) == 26
    counts = Counter()
    for document in repo.list():
        for clause in document.clauses:
            coordinate = (document.key.value, clause.id.value)
            if coordinate in selected:
                assert original[coordinate] == (clause.enrichments, clause.provenance)
                assert project_clause_enrichments(clause) == cbox_original[coordinate]
                assert (
                    clause.provenance.availability("enrichments.semantic.applicability_present")
                    == "known"
                )
                counts[clause.enrichments.semantic.applicability_present] += 1
            elif clause.id.value in grouped[document.key.value]:
                assert (
                    clause.provenance.availability("enrichments.semantic.applicability_present")
                    == "not_evaluated"
                )
    assert counts == {True: 45, False: 452}
    assert not service.import_(write=True, strict_evidence=True).written_targets
    assert not service.export(write=True).written_targets
    assert all(path.read_bytes() == value for path, value in structures.items())
    assert all(path.read_bytes() == value for path, value in public.items())
    print(
        json.dumps(
            {
                "adopted_clauses": len(selected),
                "effective_cbox_attribute_roundtrips": len(cbox_original),
                "positive": counts[True],
                "negative": counts[False],
                "physical_documents": len(public),
                "distinct_source_headings": changed_headings,
                "public_files_changed_on_replay": 0,
                "llm_calls": 0,
                "scope": (
                    "isolated full AtlasData skeletons with archive-matched local source evidence"
                ),
                "source_content_not_reconstructed_from_public_atlasdata": True,
                "export_status_counts": result.status_counts,
            },
            sort_keys=True,
        )
    )
