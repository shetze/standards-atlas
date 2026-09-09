"""Opt-in acceptance test with the user's local run; no copyrighted fixtures in Git."""

from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from pathlib import Path
from zipfile import ZipFile

import pytest

from standards_atlas.adapters.evaluation.qualification_knowledge_source import (
    load_qualification_knowledge,
)
from standards_atlas.adapters.filesystem.document_repository import (
    FileSystemEngineeringDocumentRepository,
)
from standards_atlas.application.services.knowledge_adoption_service import KnowledgeAdoptionService
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


@pytest.mark.qualification
def test_run074_materializes_497_cases_without_models_and_replays_unchanged(tmp_path: Path) -> None:
    source = os.environ.get("STANDARDS_ATLAS_RUN074_ARCHIVE")
    if not source:
        pytest.skip("set STANDARDS_ATLAS_RUN074_ARCHIVE to the local qualification-run-074.zip")
    archive = Path(source)
    batch = load_qualification_knowledge(archive)
    assert batch.selected_clause_count == 500
    assert batch.unqualified_clause_count == 3
    assert len(batch.candidates) == 497
    with ZipFile(archive) as zipped:
        name = next(
            p for p in zipped.namelist() if p.endswith("qualification-dataset-snapshot.json")
        )
        examples = json.loads(zipped.read(name))["examples"]
    # Isolated canonical target fixtures, not a claim about the user's complete
    # production workspace. Only identifiers, headings and source text are needed.
    by_document = defaultdict(list)
    for example in examples:
        context, content = example["input"]["context"], example["input"]["content"]
        by_document[context["document_key"]].append(
            Clause(
                id=ClauseId(value=context["clause_id"]),
                reference=StandardReference(
                    standard=context["document_key"],
                    clause=context["reference"],
                ),
                clause_type=ClauseType.CLAUSE,
                heading=context.get("heading"),
                content=(TextBlock(id=example["id"], text=content["text"]),),
            )
        )
    repository = FileSystemEngineeringDocumentRepository(tmp_path)
    for key, clauses in by_document.items():
        repository.save(
            EngineeringDocument(
                key=DocumentKey(value=key),
                title=key,
                document_type=DocumentType.OTHER,
                clauses=tuple(clauses),
            )
        )
    before = {path.name: path.read_bytes() for path in (tmp_path / "documents").glob("*.json")}
    service = KnowledgeAdoptionService(documents=repository)
    preview = service.apply(batch)
    assert preview.written_document_keys == ()
    assert before == {
        path.name: path.read_bytes() for path in (tmp_path / "documents").glob("*.json")
    }
    result = service.apply(batch, write=True)
    assert result.addressed_clause_count == 497
    adopted = {(item.document_key, item.clause_id) for item in batch.candidates}
    counts = Counter()
    unassessed = 0
    for document in repository.list():
        for clause in document.clauses:
            if (document.key.value, clause.id.value) in adopted:
                assert (
                    clause.provenance.availability("enrichments.semantic.applicability_present")
                    == "known"
                )
                counts[clause.enrichments.semantic.applicability_present] += 1
                assert (
                    clause.provenance.availability("enrichments.semantic.process_functions")
                    == "not_evaluated"
                )
            else:
                assert clause.provenance.generated_attributes == ()
                unassessed += 1
    assert counts == {True: 45, False: 452}
    assert unassessed == 3
    written = {path.name: path.read_bytes() for path in (tmp_path / "documents").glob("*.json")}
    replay = service.apply(batch, write=True)
    assert replay.changed_document_keys == replay.written_document_keys == ()
    assert written == {
        path.name: path.read_bytes() for path in (tmp_path / "documents").glob("*.json")
    }
    print(
        json.dumps(
            {
                "source": batch.source_id,
                "addressed": result.addressed_clause_count,
                "positive": counts[True],
                "negative": counts[False],
                "unqualified_untouched": unassessed,
                "written_documents": len(result.written_document_keys),
                "replay_writes": 0,
                "llm_calls": 0,
                "workspace": "isolated source-matching canonical test fixtures",
            },
            sort_keys=True,
        )
    )
