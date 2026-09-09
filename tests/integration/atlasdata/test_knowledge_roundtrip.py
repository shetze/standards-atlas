"""Source-free fixtures for public knowledge persistence and private hydration."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from standards_atlas.adapters.atlasdata.knowledge_evidence import KnowledgeEvidenceStore
from standards_atlas.adapters.atlasdata.knowledge_transfer import (
    AtlasDataKnowledgeService,
    read_knowledge,
)
from standards_atlas.adapters.filesystem import FileSystemEngineeringDocumentRepository
from standards_atlas.application.catalog.atlasdata_binding import atlasdata_bindings
from standards_atlas.application.catalog.models import StandardCatalog
from standards_atlas.cli import app
from standards_atlas.domain.model import (
    ClauseSubjectContext,
    ContextRouting,
    PrimarySubjectContext,
    ReferenceRole,
    ReferenceRouting,
    ReferenceTarget,
    ScopeDeclaration,
    ScopeReach,
    SubjectContextEvidence,
    TextBlock,
)
from standards_atlas.domain.model.enrichment_patch import (
    ClauseEnrichmentPatch,
    SemanticEnrichmentPatch,
    merge_generated_enrichments,
)
from standards_atlas.domain.model.knowledge_state import (
    DecisionSupport,
    GeneratedAttribute,
    GenerationMethod,
)

S = "enrichments.semantic."
SECRET = "LOCAL-ONLY synthetic evidence must never occur in a public artifact."


@pytest.fixture
def world(tmp_path):
    public = tmp_path / "data"
    public.mkdir()
    (public / "EXAMPLE").write_text(
        'name="Example"\ndigits=4\nlifecycle_status="published"\n'
        'semanticProfile="functional-safety:1.0.0"\n'
        'structure=(\n "2025 r1 r2 r3"\n)\n#---data---#\n'
        "TOC;a;Example:2025 1;One;r\nTOC;b;Example:2025 2;Two;r\n"
        "TOC;c;Example:2025 3;Three;r\n"
    )
    payload = {
        "manifest_type": "standards",
        "schema_version": 2,
        "knowledge_domains": [],
        "industry_sectors": [],
        "families": [
            {
                "key": "EXAMPLE",
                "name": "Example",
                "organization": "Example",
                "publication_year": 2025,
                "source": {"pdf": "local/example.pdf"},
                "atlasdata": {"path": "data/EXAMPLE"},
            }
        ],
    }
    (tmp_path / "manifests").mkdir()
    (tmp_path / "manifests/standards.yaml").write_text(yaml.safe_dump(payload))
    bindings = atlasdata_bindings(StandardCatalog.model_validate(payload), root=tmp_path)
    repository = FileSystemEngineeringDocumentRepository(tmp_path / ".atlas/data")
    service = AtlasDataKnowledgeService(
        documents=repository,
        bindings=bindings,
        evidence_root=tmp_path / ".atlas/data/knowledge-evidence",
    )
    document = service._skeleton(bindings["EXAMPLE"])
    repository.save(document)
    return tmp_path, repository, service, bindings["EXAMPLE"], document


def patch_clause(document, index=0, *, fields=None, unknown=(), context=None, secret=False):
    fields = fields or {}
    context = context or {}
    attributes = []
    for name in fields:
        attributes.append(
            GeneratedAttribute(
                path=S + name,
                generator="test-model-v1",
                method=GenerationMethod.LLM,
                evidence=(SECRET,) if secret else (),
                decision=DecisionSupport(
                    rule="majority-v1",
                    source_artifact="inputs/consensus.json",
                    source_sha256="a" * 64,
                    valid_votes=3,
                    supporting_votes=2,
                    model_ids=("one", "two", "three"),
                ),
            )
        )
    for name in unknown:
        attributes.append(
            GeneratedAttribute(
                path=S + name,
                generator="test",
                method=GenerationMethod.LLM,
                availability="unknown",
            )
        )
    for name in context:
        attributes.append(
            GeneratedAttribute(
                path="enrichments." + name,
                generator="context-v1",
                method=GenerationMethod.LLM,
                evidence=(SECRET,) if secret else (),
            )
        )
    clause = merge_generated_enrichments(
        document.clauses[index],
        ClauseEnrichmentPatch(semantic=SemanticEnrichmentPatch(**fields), **context),
        tuple(attributes),
    ).clause
    clauses = list(document.clauses)
    clauses[index] = clause
    return document.model_copy(update={"clauses": tuple(clauses)})


def contexts(clause_id):
    return {
        "subject_context": ClauseSubjectContext(
            primary_subject=PrimarySubjectContext(
                normalized_label="safety lifecycle",
                confidence=0.8,
                evidence=SubjectContextEvidence(
                    kind="clause_text",
                    matched_label="safety lifecycle",
                    source_text=SECRET,
                    source_clause_id=clause_id,
                ),
            )
        ),
        "context_routing": ContextRouting(
            scopes=(
                ScopeDeclaration(
                    source_clause_id=clause_id,
                    reaches=(ScopeReach(kind="document"),),
                    conditions=(SECRET,),
                    exclusions=(SECRET,),
                    qualifications=(SECRET,),
                    evidence=(SECRET,),
                ),
            ),
            references=(
                ReferenceRouting(
                    source_clause_id=clause_id,
                    target=ReferenceTarget(reference="2", title=SECRET),
                    role=ReferenceRole.REQUIRES,
                    evidence=(SECRET,),
                ),
            ),
        ),
    }


def save(world, document):
    world[1].save(document)
    return document


def export(world, **kwargs):
    return world[2].export(write=True, **kwargs)


def record(world):
    return read_knowledge(world[3].enrichments_path)


def replace_record(world, update):
    value = record(world).model_dump(mode="json")
    update(value)
    world[3].enrichments_path.write_text(yaml.safe_dump(value, sort_keys=False))


def test_complete_roundtrip_preserves_values_support_authority_and_private_context(world):
    root, repo, service, binding, document = world
    document = patch_clause(
        document,
        fields={
            "statement_functions": ("requirement", "description"),
            "primary_function": "requirement",
            "knowledge_kinds": ("process",),
            "primary_knowledge_kind": "process",
            "process_functions": ("activity",),
            "primary_process_function": "activity",
            "applicability_present": True,
            "role_semantics_present": True,
            "role_relations": (
                {"actor": SECRET, "relation_class": "responsibility", "target": SECRET},
            ),
        },
        context=contexts(document.clauses[0].id.value),
        secret=True,
    )
    first = document.clauses[0].confirm_authoritative(S + "process_functions", authority="review-1")
    document = document.model_copy(update={"clauses": (first, *document.clauses[1:])})
    document = patch_clause(
        document,
        1,
        fields={"applicability_present": False},
        unknown=("knowledge_kinds", "primary_knowledge_kind"),
    )
    document = document.model_copy(
        update={
            "clauses": tuple(
                clause.with_baseline_updates(content=(TextBlock(id="synthetic", text=SECRET),))
                for clause in document.clauses
            )
        }
    )
    save(world, document)
    original_structure = binding.source.read_bytes()
    preview = service.export()
    assert preview.changed_targets and not preview.written_targets
    assert not binding.enrichments_path.exists()
    assert not service.evidence_root.exists()
    exported = export(world)
    assert exported.written_targets
    public = binding.enrichments_path.read_bytes()
    assert SECRET.encode() not in public
    assert SECRET not in exported.model_dump_json()
    assert SECRET not in record(world).model_dump_json()
    assert any(SECRET in path.read_text() for path in service.evidence_root.glob("*.json"))
    assert binding.source.read_bytes() == original_structure
    assert service.export(write=True).written_targets == ()
    repo.delete(document.key)
    service.import_(write=True, strict_evidence=True)
    restored = repo.load(document.key)
    for old, new in zip(document.clauses, restored.clauses, strict=True):
        assert old.enrichments == new.enrichments
        assert old.provenance == new.provenance
    assert restored.clauses[1].provenance.availability(S + "knowledge_kinds") == "unknown"
    assert restored.clauses[2].provenance.availability(S + "knowledge_kinds") == "not_evaluated"
    assert (
        restored.clauses[2].provenance.availability(S + "applicability_present") == "not_evaluated"
    )
    assert service.import_(write=True).written_targets == ()
    assert service.export(write=True).written_targets == ()
    assert binding.enrichments_path.read_bytes() == public
    assert binding.source.read_bytes() == original_structure


@pytest.mark.parametrize("value", [True, False])
def test_presence_only_false_empty_and_unknown_are_not_conflated(world, value):
    document = patch_clause(
        world[4],
        fields={"applicability_present": value, "knowledge_kinds": ()},
        unknown=("process_functions",),
    )
    save(world, document)
    export(world)
    world[1].delete(document.key)
    world[2].import_(write=True)
    clause = world[1].load(document.key).clauses[0]
    assert clause.enrichments.semantic.applicability_present is value
    assert clause.provenance.availability(S + "applicability_present") == "known"
    assert clause.provenance.availability(S + "knowledge_kinds") == "known"
    assert clause.provenance.availability(S + "process_functions") == "unknown"
    assert clause.provenance.availability(S + "role_semantics_present") == "not_evaluated"


def test_public_only_import_defers_context_without_inventing_empty_conditions(world):
    root, repo, service, _, document = world
    document = patch_clause(
        document,
        fields={"applicability_present": True},
        context=contexts(document.clauses[0].id.value),
        secret=True,
    )
    save(world, document)
    export(world)
    repo.delete(document.key)
    no_evidence = AtlasDataKnowledgeService(
        documents=repo, bindings=service.bindings, evidence_root=root / "missing"
    )
    result = no_evidence.import_(write=True)
    assert result.status_counts["deferred"] == 2
    assert result.status_counts["evidence_unavailable"] == 1
    restored = repo.load(document.key).clauses[0]
    assert restored.enrichments.semantic.applicability_present is True
    assert restored.provenance.availability("enrichments.context_routing") == "not_evaluated"
    assert restored.provenance.availability("enrichments.subject_context") == "not_evaluated"
    assert restored.provenance.availability(S + "applicability_present") == "known"
    assert result.content_unverified_clauses == 1
    original = world[3].enrichments_path.read_bytes()
    assert no_evidence.export(write=True).written_targets == ()
    assert world[3].enrichments_path.read_bytes() == original
    # Hydrate later into the same document, without a model call or source text fabrication.
    service.import_(write=True, strict_evidence=True)
    assert repo.load(document.key).clauses[0].enrichments == document.clauses[0].enrichments


def test_strict_missing_evidence_aborts_before_writes(world):
    root, repo, service, _, document = world
    document = patch_clause(document, context=contexts(document.clauses[0].id.value))
    save(world, document)
    export(world)
    repo.delete(document.key)
    missing = AtlasDataKnowledgeService(
        documents=repo, bindings=service.bindings, evidence_root=root / "missing"
    )
    with pytest.raises(ValueError, match="missing private evidence"):
        missing.import_(write=True, strict_evidence=True)
    assert not repo.exists(document.key)


def test_partial_export_preserves_other_dimensions_and_unselected_clauses(world):
    document = patch_clause(
        world[4],
        fields={"applicability_present": True, "knowledge_kinds": ("process",)},
    )
    document = patch_clause(document, 1, fields={"applicability_present": False})
    save(world, document)
    export(world)
    old = record(world)
    document = patch_clause(
        document,
        fields={"knowledge_kinds": ("concept",), "applicability_present": False},
    )
    save(world, document)
    export(world, dimensions=("knowledge_kinds",), clause_ids=(document.clauses[0].id.value,))
    new = record(world)
    old_by_id = {c.clause_id: c for c in old.clauses}
    new_by_id = {c.clause_id: c for c in new.clauses}
    assert old_by_id[document.clauses[1].id.value] == new_by_id[document.clauses[1].id.value]
    attrs = {a.path: a for a in new_by_id[document.clauses[0].id.value].attributes}
    assert attrs[S + "applicability_present"].value is True
    assert attrs[S + "knowledge_kinds"].value == ["concept"]


def test_generated_update_cannot_overwrite_confirmation_in_companion(world):
    document = patch_clause(world[4], fields={"applicability_present": True})
    document = document.model_copy(
        update={
            "clauses": (
                document.clauses[0].confirm_authoritative(S + "applicability_present"),
                *document.clauses[1:],
            )
        }
    )
    save(world, document)
    export(world)
    original = world[3].enrichments_path.read_bytes()
    # A different local workspace has an unconfirmed contrary result.
    document = patch_clause(world[4], fields={"applicability_present": False})
    save(world, document)
    result = export(world)
    assert result.status_counts["protected"] == 2
    assert world[3].enrichments_path.read_bytes() == original


def test_conflicting_explicit_confirmations_fail_before_write(world):
    document = patch_clause(world[4], fields={"applicability_present": True})
    document = document.model_copy(
        update={
            "clauses": (
                document.clauses[0].confirm_authoritative(S + "applicability_present"),
                *document.clauses[1:],
            )
        }
    )
    save(world, document)
    export(world)
    other = patch_clause(world[4], fields={"applicability_present": False})
    other = other.model_copy(
        update={
            "clauses": (
                other.clauses[0].confirm_authoritative(S + "applicability_present"),
                *other.clauses[1:],
            )
        }
    )
    save(world, other)
    original = world[3].enrichments_path.read_bytes()
    with pytest.raises(ValueError, match="conflicting authoritative"):
        export(world)
    with pytest.raises(ValueError, match="conflicting authoritative"):
        world[2].import_(write=True)
    assert world[3].enrichments_path.read_bytes() == original


def test_current_toc_confirmation_wins_over_generated_values_even_existing_workspace(world):
    root, repo, service, binding, document = world
    document = patch_clause(document, fields={"applicability_present": False})
    save(world, document)
    export(world)
    text = binding.source.read_text().replace(";One;r\n", ";One;r;AF-INC\n")
    binding.source.write_text(text)
    result = service.import_(write=True)
    clause = repo.load(document.key).clauses[0]
    assert clause.enrichments.semantic.applicability_present is True
    assert clause.enrichments.semantic.applicability_functions == ("inclusion",)
    assert clause.provenance.protection(S + "applicability_present") == "confirmed"
    assert result.status_counts["protected"] == 2


@pytest.mark.parametrize(
    "damage",
    ["heading", "reference", "clause_id", "content", "structure", "edition"],
)
def test_stale_identity_or_sources_are_rejected_before_write(world, damage):
    root, repo, service, binding, document = world
    document = patch_clause(document, fields={"applicability_present": True})
    clause = document.clauses[0].with_baseline_updates(
        content=(TextBlock(id="synthetic", text=SECRET),),
    )
    document = document.model_copy(update={"clauses": (clause, *document.clauses[1:])})
    save(world, document)
    export(world)
    if damage == "structure":
        binding.source.write_text(binding.source.read_text().replace(";One;r", ";Changed;r"))
    elif damage == "content":
        clause = clause.with_baseline_updates(content=(TextBlock(id="other", text="Different"),))
        save(world, document.model_copy(update={"clauses": (clause, *document.clauses[1:])}))
    else:

        def change(payload):
            if damage == "edition":
                payload["publication_year"] = 2024
            elif damage == "heading":
                payload["clauses"][0]["heading_sha256"] = "a" * 64
            elif damage == "reference":
                payload["clauses"][0]["reference"]["clause"] = "absent"
            else:
                payload["clauses"][0]["clause_id"] = "absent"

        replace_record(world, change)
    stored = (root / ".atlas/data/documents/EXAMPLE.json").read_bytes()
    with pytest.raises(ValueError, match="mismatch|missing"):
        service.import_(write=True)
    assert (root / ".atlas/data/documents/EXAMPLE.json").read_bytes() == stored


def test_corrupt_private_payload_fails_without_overwrite(world):
    document = patch_clause(world[4], context=contexts(world[4].clauses[0].id.value))
    save(world, document)
    export(world)
    path = next(world[2].evidence_root.glob("*.json"))
    path.write_text("{}")
    world[1].delete(document.key)
    with pytest.raises(ValueError, match="hash mismatch"):
        world[2].import_(write=True)
    assert not world[1].exists(document.key)


def test_private_store_rejects_corrupt_preexisting_blobs(world):
    store = KnowledgeEvidenceStore(world[0] / "evidence")
    key = store.put(
        kind="value",
        path="enrichments.subject_context",
        value={"primary_subject": None, "ambiguous_candidates": []},
    )
    store.commit()
    (store.root / f"{key}.json").write_bytes(b"bad")
    with pytest.raises(ValueError, match="inconsistent"):
        store.commit()


def test_private_provenance_redacts_free_text_and_absolute_paths(world):
    document = patch_clause(world[4], fields={"applicability_present": True})
    clause = document.clauses[0]
    attribute = clause.provenance.generated_attributes[0].model_copy(
        update={
            "generator": SECRET,
            "evidence": (SECRET,),
            "decision": DecisionSupport(
                rule=SECRET, source_artifact="/home/private/data/file.json", source_sha256="0" * 64
            ),
        }
    )
    clause = clause.mark_generated(attribute)
    save(world, document.model_copy(update={"clauses": (clause, *document.clauses[1:])}))
    export(world)
    public = world[3].enrichments_path.read_text()
    assert SECRET not in public and "/home/private" not in public
    world[1].delete(document.key)
    world[2].import_(write=True, strict_evidence=True)
    assert world[1].load(document.key).clauses[0].provenance == clause.provenance


def test_missing_private_evidence_cannot_replace_preexisting_routing(world):
    root, repo, service, _, document = world
    save(
        world,
        patch_clause(
            document,
            fields={"applicability_present": True},
            context=contexts(document.clauses[0].id.value),
        ),
    )
    export(world)
    # Keep another local routing object; missing imported evidence must not empty it.
    other = patch_clause(
        document,
        context={
            "context_routing": ContextRouting(
                scopes=(
                    ScopeDeclaration(
                        source_clause_id=document.clauses[0].id.value,
                        reaches=(ScopeReach(kind="document"),),
                        conditions=("LOCAL OTHER",),
                    ),
                )
            )
        },
    )
    save(world, other)
    missing = AtlasDataKnowledgeService(
        documents=repo, bindings=service.bindings, evidence_root=root / "missing"
    )
    missing.import_(write=True)
    restored = repo.load(document.key)
    assert restored.clauses[0].context_routing == other.clauses[0].context_routing
    assert restored.clauses[0].semantic_classification.applicability_present is True


def test_cli_preview_export_and_restore_use_explicit_write(world):
    root, repo, _, binding, document = world
    save(world, patch_clause(document, fields={"applicability_present": True}))
    runner = CliRunner()
    common = ["--root", str(root), "--document", "EXAMPLE"]
    result = runner.invoke(
        app, ["atlasdata", "export-enrichments", *common, "--output", "local/preview.json"]
    )
    assert result.exit_code == 0, result.output
    assert "Dry run" in result.output
    assert not binding.enrichments_path.exists()
    result = runner.invoke(app, ["atlasdata", "export-enrichments", *common, "--write"])
    assert result.exit_code == 0, result.output
    repo.delete(document.key)
    result = runner.invoke(app, ["atlasdata", "import-enrichments", *common])
    assert result.exit_code == 0, result.output
    assert not repo.exists(document.key)
    result = runner.invoke(app, ["atlasdata", "import-enrichments", *common, "--write"])
    assert result.exit_code == 0, result.output
    assert repo.load(document.key).clauses[0].enrichments.semantic.applicability_present is True


@pytest.mark.parametrize(
    "report",
    [
        "data/EXAMPLE",
        "data/enrichments/EXAMPLE.yaml",
        ".atlas/data/documents/EXAMPLE.json",
        "manifests/standards.yaml",
        ".atlas/data/knowledge-evidence/test.json",
    ],
)
def test_report_destination_cannot_overwrite_inputs_or_persistence(world, report):
    result = CliRunner().invoke(
        app,
        ["atlasdata", "export-enrichments", "--root", str(world[0]), "--output", report, "--write"],
    )
    assert result.exit_code == 2
    assert "report must not overwrite" in result.output
    assert not world[3].enrichments_path.exists()


@pytest.mark.parametrize(
    "malformed",
    ["version", "duplicate", "unknown-field", "raw-evidence", "bool", "polarity"],
)
def test_public_reader_rejects_invalid_contract(world, malformed):
    save(world, patch_clause(world[4], fields={"applicability_present": True}))
    export(world)

    def damage(payload):
        a = payload["clauses"][0]["attributes"][0]
        if malformed == "version":
            payload["schema_version"] = "999.0"
        elif malformed == "duplicate":
            payload["clauses"][0]["attributes"].append(dict(a))
        elif malformed == "unknown-field":
            a["prompt_response"] = SECRET
        elif malformed == "raw-evidence":
            a["generated"]["evidence"] = [SECRET]
        elif malformed == "bool":
            a["value"] = 1
        else:
            a["value"] = "included"

    replace_record(world, damage)
    with pytest.raises(ValueError):
        record(world)


def test_public_reader_rejects_duplicate_yaml_keys(world):
    save(world, patch_clause(world[4], fields={"applicability_present": True}))
    export(world)
    with world[3].enrichments_path.open("a") as stream:
        stream.write("document_key: OTHER\n")
    with pytest.raises(ValueError, match="duplicate key"):
        record(world)


def test_private_store_cannot_be_inside_public_directory(world):
    service = AtlasDataKnowledgeService(
        documents=world[1], bindings=world[2].bindings, evidence_root=world[0] / "data/evidence"
    )
    with pytest.raises(ValueError, match="outside the public"):
        service.export(write=True)


def _second_document(world):
    from dataclasses import replace

    root, repo, service, binding, _ = world
    source = binding.source.with_name("OTHER")
    source.write_text(binding.source.read_text().replace("Example", "Other"))
    other = replace(binding, document_key="OTHER", family_key="OTHER", source=source)
    service.bindings["OTHER"] = other
    document = service._skeleton(other)
    repo.save(document)
    return other, document


def test_export_preflights_all_documents_before_any_public_or_private_write(world):
    _, repo, service, binding, document = world
    _, other = _second_document(world)
    repo.save(patch_clause(document, fields={"applicability_present": True}, secret=True))
    other = patch_clause(other, fields={"applicability_present": True})
    wrong = other.clauses[0].model_copy(
        update={
            "reference": other.clauses[0].reference.model_copy(update={"year": 1999}),
        }
    )
    repo.save(other.model_copy(update={"clauses": (wrong, *other.clauses[1:])}))
    with pytest.raises(ValueError, match="reference/heading mismatch"):
        service.export(write=True)
    assert not binding.enrichments_path.parent.exists()
    assert not service.evidence_root.exists()


def test_import_preflights_all_documents_before_creating_the_first_one(world):
    _, repo, service, _, document = world
    other_binding, other = _second_document(world)
    repo.save(patch_clause(document, fields={"applicability_present": True}))
    repo.save(patch_clause(other, fields={"applicability_present": True}))
    service.export(write=True)
    repo.delete(document.key)
    repo.delete(other.key)
    content = yaml.safe_load(other_binding.enrichments_path.read_text())
    content["structure_sha256"] = "0" * 64
    other_binding.enrichments_path.write_text(yaml.safe_dump(content))
    with pytest.raises(ValueError, match="identity/edition/structure mismatch"):
        service.import_(write=True)
    assert not repo.exists(document.key)
    assert not repo.exists(other.key)


def test_distinct_source_and_atlasdata_headings_keep_independent_fingerprints(world):
    _, repo, service, binding, document = world
    document = patch_clause(document, fields={"applicability_present": True})
    clause = document.clauses[0].with_baseline_updates(
        heading="Normalized source heading",
        content=(TextBlock(id="s", text=SECRET),),
    )
    repo.save(document.model_copy(update={"clauses": (clause, *document.clauses[1:])}))
    export(world)
    original = binding.enrichments_path.read_bytes()
    first = record(world).clauses[0]
    assert first.heading_sha256 != first.atlasdata_heading_sha256
    repo.delete(document.key)
    result = service.import_(write=True)
    assert result.content_unverified_clauses == 1
    assert repo.load(document.key).clauses[0].heading == "One"
    assert service.export(write=True).written_targets == ()
    assert binding.enrichments_path.read_bytes() == original


def test_unknown_export_preserves_known_public_value(world):
    _, repo, service, binding, document = world
    save(world, patch_clause(document, fields={"knowledge_kinds": ("process",)}))
    export(world)
    before = binding.enrichments_path.read_bytes()
    save(world, patch_clause(document, unknown=("knowledge_kinds",)))
    result = service.export(write=True)
    assert result.written_targets == ()
    assert binding.enrichments_path.read_bytes() == before


def test_referenced_empty_context_needs_no_protected_blob_for_restore(world):
    root, repo, service, _, document = world
    document = patch_clause(
        document,
        context={
            "subject_context": ClauseSubjectContext(),
            "context_routing": ContextRouting(),
        },
    )
    save(world, document)
    export(world)
    repo.delete(document.key)
    empty_store = AtlasDataKnowledgeService(
        documents=repo,
        bindings=service.bindings,
        evidence_root=root / "no-evidence",
    )
    result = empty_store.import_(write=True, strict_evidence=True)
    assert "deferred" not in result.status_counts
    actual = repo.load(document.key).clauses[0]
    assert actual.provenance == document.clauses[0].provenance
    assert actual.provenance.availability("enrichments.context_routing") == "known"


def test_negative_confirmation_preserves_private_authority_and_blocks_regeneration(world):
    _, repo, service, _, document = world
    document = patch_clause(document, fields={"applicability_present": False})
    confirmed = document.clauses[0].confirm_authoritative(
        S + "applicability_present",
        authority=SECRET,
    )
    save(world, document.model_copy(update={"clauses": (confirmed, *document.clauses[1:])}))
    export(world)
    repo.delete(document.key)
    service.import_(write=True, strict_evidence=True)
    imported = repo.load(document.key)
    assert imported.clauses[0].provenance == confirmed.provenance
    regenerated = patch_clause(imported, fields={"applicability_present": True})
    assert regenerated.clauses[0].semantic_classification.applicability_present is False


def test_unmarked_populated_attribute_stays_unattributed_not_confirmed(world):
    _, repo, service, _, document = world
    document = patch_clause(document, fields={"role_semantics_present": True})
    clause = document.clauses[0]
    state = clause.provenance.model_copy(
        update={
            "generated_attributes": tuple(
                a
                for a in clause.provenance.generated_attributes
                if a.path != S + "role_semantics_present"
            )
        }
    )
    clause = clause.model_copy(update={"provenance": state})
    save(world, document.model_copy(update={"clauses": (clause, *document.clauses[1:])}))
    export(world)
    assert record(world).clauses[0].attributes[0].origin == "unattributed"
    repo.delete(document.key)
    service.import_(write=True)
    restored = repo.load(document.key)
    assert restored.clauses[0].provenance.protection(S + "role_semantics_present") == "unattributed"
    assert patch_clause(restored, fields={"role_semantics_present": False}) == restored


def test_atomic_writer_keeps_original_and_removes_temporary_on_replace_failure(
    tmp_path,
    monkeypatch,
):
    from standards_atlas.adapters.atlasdata import knowledge_evidence

    target = tmp_path / "original.yaml"
    target.write_bytes(b"original")

    def fail_replace(*args):
        raise OSError("synthetic write failure")

    monkeypatch.setattr(knowledge_evidence.os, "replace", fail_replace)
    with pytest.raises(OSError, match="synthetic write failure"):
        knowledge_evidence.atomic_write(target, b"replacement")
    assert target.read_bytes() == b"original"
    assert list(tmp_path.iterdir()) == [target]


def test_manifest_mapping_keeps_parts_supplements_and_unspecified_years_distinct():
    from standards_atlas.adapters.catalog import YamlStandardCatalogReader

    root = Path(__file__).resolve().parents[3]
    catalog = YamlStandardCatalogReader().read(root / "manifests/standards.yaml")
    bindings = atlasdata_bindings(catalog, root=root)
    assert bindings["ISO26262-11"].selection_part == "11"
    assert bindings["ISO26262-11"].publication_year == 2018
    assert bindings["ISO26262-11"].source == root / "data/ISO26262"
    assert bindings["IEC61508-3-1"].selection_part is None
    assert bindings["IEC61508-3-1"].publication_year is None
    assert bindings["IEC61508-3-1"].source == root / "data/IEC61508-3-1"
