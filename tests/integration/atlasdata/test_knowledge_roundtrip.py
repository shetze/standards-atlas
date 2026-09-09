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
        "TOC;aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa;Example:2025 1;One;r\n"
        "TOC;bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb;Example:2025 2;Two;r\n"
        "TOC;cccccccccccccccccccccccccccccccc;Example:2025 3;Three;r\n"
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
    value = yaml.safe_load(world[3].enrichments_path.read_text())
    update(value)
    world[3].enrichments_path.write_text(yaml.safe_dump(value, sort_keys=False))


def test_schema_1_1_is_readable_naturally_ordered_and_centralizes_fingerprints(world):
    root, repo, _, binding, document = world
    document = patch_clause(
        document,
        0,
        fields={"applicability_present": True},
        secret=True,
    )
    document = patch_clause(document, 1, fields={"applicability_present": False})
    document = patch_clause(document, 2, unknown=("knowledge_kinds",))
    first = document.clauses[0].with_baseline_updates(heading="Internal normalized heading")
    document = document.model_copy(update={"clauses": (first, *document.clauses[1:])})
    repo.save(document)

    export(world)
    payload = yaml.safe_load(binding.enrichments_path.read_text())

    assert payload["schema_version"] == "1.1"
    assert payload["fingerprints"].keys() == {"structure"}
    assert payload["fingerprints"]["structure"].startswith("sha256:")
    assert "structure_sha256" not in payload
    assert [item["reference"]["clause"] for item in payload["clauses"]] == ["1", "2", "3"]
    assert [item["atlasdata_md5"] for item in payload["clauses"]] == [
        "a" * 32,
        "b" * 32,
        "c" * 32,
    ]

    clause = payload["clauses"][0]
    assert clause["heading"] == "Internal normalized heading"
    assert set(clause["fingerprints"]) >= {"heading", "atlasdata_heading", "attributes"}
    assert clause["fingerprints"]["heading"] != clause["fingerprints"]["atlasdata_heading"]
    assert not any(key.endswith("_sha256") for key in clause)
    attribute = next(
        item for item in clause["attributes"] if item["path"] == S + "applicability_present"
    )
    assert "availability" not in attribute
    assert "path" not in attribute["generated"]
    assert "availability" not in attribute["generated"]
    assert "evidence" not in attribute["generated"]
    fingerprints = clause["fingerprints"]["attributes"][attribute["path"]]
    assert fingerprints["decision_source"].startswith("sha256:")
    assert fingerprints["evidence"] and all(
        value.startswith("sha256:") for value in fingerprints["evidence"]
    )
    unknown = payload["clauses"][2]["attributes"][0]
    assert unknown["availability"] == "unknown"
    assert unknown["value"] is None
    assert SECRET not in binding.enrichments_path.read_text()
    assert root.joinpath("data/EXAMPLE").read_text().startswith('name="Example"')


def test_atlasdata_md5_is_validated_against_the_existing_toc_record(world):
    save(world, patch_clause(world[4], fields={"applicability_present": True}))
    export(world)

    def damage(payload):
        payload["clauses"][0]["atlasdata_md5"] = "0" * 32

    replace_record(world, damage)
    with pytest.raises(ValueError, match="AtlasData record MD5 mismatch"):
        world[2].import_(write=True)


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
                payload["clauses"][0]["fingerprints"]["heading"] = "sha256:" + "a" * 64
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
            path = a["path"]
            payload["clauses"][0]["fingerprints"].setdefault("attributes", {}).setdefault(path, {})[
                "evidence"
            ] = [SECRET]
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
    content["fingerprints"]["structure"] = "sha256:" + "0" * 64
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


def test_effective_cbox_roundtrip_matches_workbench_report_and_fresh_projection(world):
    from standards_atlas.adapters.evaluation.engineering_document_clause_provider import (
        EngineeringDocumentClauseProvider,
    )
    from standards_atlas.application.context.canonical_cbox import project_clause_enrichments
    from standards_atlas.application.prompt_workbench.context import ClausePromptContextAssembler
    from standards_atlas.application.services.cbox_report_service import CBoxReportService

    root, repository, service, binding, document = world
    document = patch_clause(
        document,
        fields={
            "applicability_present": True,
            "applicability_functions": [],
            "role_semantics_present": False,
            "knowledge_kinds": [],
        },
        unknown=("primary_function",),
        context=contexts(document.clauses[0].id.value),
    )
    repository.save(document)
    provider = EngineeringDocumentClauseProvider(root / ".atlas/data")
    before = CBoxReportService(provider).build(document_keys=(binding.document_key,))
    # Clause order is stable by identity, not TOC order; locate the patched clause.
    record = next(
        item for item in before.clauses if item["clause_id"] == document.clauses[0].id.value
    )
    sources = record["canonical"]["attribute_sources"]
    assert sources[S + "primary_function"]["availability"] == "unknown"
    assert sources[S + "process_functions"]["availability"] == "not_evaluated"
    assert record["framed"]["semantic"]["applicability_present"] is True
    assert record["framed"]["semantic"]["role_semantics_present"] is False
    assert record["framed"]["semantic"]["knowledge_kinds"] == []
    assert "primary_function" not in record["framed"]["semantic"]
    descriptor = next(item for item in provider.list_clauses() if item.id == record["clause_id"])
    workbench = ClausePromptContextAssembler().assemble(
        descriptor,
        variant_id="effective-context-v1",
    )
    assert workbench.canonical_context == record["canonical"]
    assert dict(workbench.selected_context) == record["framed"]
    assert workbench.context_text == record["rendered"]
    service.export(write=True)
    for path in (root / ".atlas/data/documents").glob("*.json"):
        path.unlink()
    service.import_(write=True, strict_evidence=True)
    restored = repository.load(document.key)
    assert project_clause_enrichments(restored.clauses[0]) == project_clause_enrichments(
        document.clauses[0]
    )
    after = CBoxReportService(EngineeringDocumentClauseProvider(root / ".atlas/data")).build(
        document_keys=(binding.document_key,)
    )
    assert before == after


def test_cbox_report_cli_is_local_read_only_and_stable(world, monkeypatch):
    import json

    root, repository, _, _, document = world
    monkeypatch.chdir(root)
    runner = CliRunner()
    before = {p: p.read_bytes() for p in (root / ".atlas/data/documents").glob("*.json")}
    output = root / "local/review/cbox.json"
    args = ["document", "cbox-report", "--document", "EXAMPLE", "--output", str(output)]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    payload = json.loads(output.read_text())
    assert payload["clause_count"] == len(document.clauses)
    assert payload["frame"] == "effective-context-v1"
    first_mtime = output.stat().st_mtime_ns
    assert runner.invoke(app, args).exit_code == 0
    assert output.stat().st_mtime_ns == first_mtime
    assert {p: p.read_bytes() for p in before} == before
    result = runner.invoke(app, [*args[:-1], str(root / "data/public.json")])
    assert result.exit_code != 0
    assert not (root / "data/public.json").exists()


def test_available_only_empty_companion_selection_never_imports_all(world, monkeypatch):
    import json

    root, _, _, _, _ = world
    monkeypatch.chdir(root)
    report = root / "local/import.json"
    result = CliRunner().invoke(
        app,
        [
            "atlasdata",
            "import-enrichments",
            "--document",
            "EXAMPLE",
            "--available-only",
            "--output",
            str(report),
            "--write",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(report.read_text())
    assert not payload["written_targets"]
    assert payload["status_counts"]["missing_document_or_companion"] == 1
    result = CliRunner().invoke(
        app,
        [
            "atlasdata",
            "import-enrichments",
            "--document",
            "UNKNOWN",
            "--available-only",
        ],
    )
    assert result.exit_code != 0


def test_cbox_not_evaluated_and_confirmed_false_are_not_confused(world):
    from standards_atlas.application.context.canonical_cbox import project_clause_enrichments

    _, _, _, _, document = world
    original = document.clauses[0]
    # The source type may carry deterministic values, but unused presence is not negative gold.
    unknown = {item.path: item for item in project_clause_enrichments(original).attributes}
    assert unknown[S + "applicability_present"].availability == "not_evaluated"
    confirmed = original.confirm_authoritative(S + "applicability_present")
    projected = {item.path: item for item in project_clause_enrichments(confirmed).attributes}
    value = projected[S + "applicability_present"]
    assert value.availability == "known"
    assert value.origin == "confirmed"
    assert value.value is False


def test_partial_context_confirmation_does_not_publish_the_whole_object(world):
    from standards_atlas.application.context.canonical_cbox import project_clause_enrichments

    _, _, _, _, document = world
    clause = document.clauses[0].confirm_authoritative(
        "enrichments.subject_context.primary_subject"
    )
    record = next(
        item
        for item in project_clause_enrichments(clause).attributes
        if item.path == "enrichments.subject_context"
    )
    assert record.availability == "partial"
    assert record.value is None


def test_explicit_knowledge_workflow_runs_real_cli_commands_and_revalidates(world, monkeypatch):
    import json

    from standards_atlas.adapters.catalog import YamlStandardCatalogReader
    from standards_atlas.adapters.workflow import FileSystemWorkflowArtifactStore
    from standards_atlas.application.workflow import WorkflowExecutor, WorkflowRecovery
    from standards_atlas.application.workflow.knowledge_plan import knowledge_plan

    root, repository, _, _, document = world
    monkeypatch.chdir(root)
    repository.save(patch_clause(document, fields={"applicability_present": True}))
    manifest = root / "manifests/standards.yaml"
    plan = knowledge_plan(
        YamlStandardCatalogReader().read(manifest),
        family_keys=("EXAMPLE",),
        catalog_root=root,
        manifest=manifest,
        publish=True,
        strict_evidence=True,
    )

    class Runner:
        def __init__(self):
            self.commands = []

        def run(self, command, cwd):
            assert cwd == root
            self.commands.append(command)
            result = CliRunner().invoke(app, list(command[3:]))
            assert result.exit_code == 0, (result.output, result.exception)

    runner = Runner()
    executor = WorkflowExecutor(WorkflowRecovery(FileSystemWorkflowArtifactStore()))
    first = executor.execute(plan, project_root=root, runner=runner)
    assert first.completed
    assert len(first.executed_steps) == 3
    report = json.loads((root / plan.steps[-1].output_paths[0]).read_text())
    assert report["clause_count"] == 3
    assert any(
        item["framed"].get("semantic", {}).get("applicability_present") is True
        for item in report["clauses"]
    )
    public = {
        p: (p.read_bytes(), p.stat().st_mtime_ns) for p in (root / "data").rglob("*") if p.is_file()
    }
    second = executor.execute(plan, project_root=root, runner=runner)
    assert second.completed
    assert len(second.executed_steps) == 3  # inspect current inputs, not a stale success marker
    assert {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in public} == public


def test_corpus_and_workbench_share_canonical_ancestor_and_attribute_values(world):
    import json

    from standards_atlas.adapters.evaluation.engineering_document_clause_provider import (
        EngineeringDocumentClauseProvider,
    )
    from standards_atlas.application.prompt_workbench.context import ClausePromptContextAssembler
    from standards_atlas.application.semantic_qualification.workflow import (
        CorpusBuildConfig,
        EvaluationCorpusBuilder,
    )

    root, repository, _, _, document = world
    parent, child, other = document.clauses
    parent = parent.with_baseline_updates(content=(TextBlock(id="parent", text="Parent content."),))
    child = child.with_baseline_updates(content=(TextBlock(id="child", text="Child content."),))
    child = child.with_baseline_updates(parent_id=parent.id)
    document = document.model_copy(update={"clauses": (parent, child, other)})
    document = patch_clause(document, index=1, fields={"applicability_present": False})
    repository.save(document)
    provider = EngineeringDocumentClauseProvider(root / ".atlas/data")
    built = EvaluationCorpusBuilder(provider).build(
        CorpusBuildConfig(
            task="statement-function-classification",
            version="1.0.0",
            count=2,
            exclude_context_meta=False,
            knowledge_domain="functional-safety",
        ),
        root / "corpus",
    )
    examples = json.loads(built.dataset_path.read_text())["examples"]
    for example in examples:
        workbench = ClausePromptContextAssembler().assemble(
            provider.get_clause(example["id"]),
            variant_id="effective-context-v1",
        )
        actual = dict(example["input"]["context"])
        actual.pop("eligibility")
        assert actual == workbench.canonical_context
    descriptor = provider.get_clause(child.id.value)
    assert descriptor.ancestor_headings == (
        {
            "clause_id": parent.id.value,
            "reference": parent.reference.clause,
            "heading": parent.heading,
        },
    )
    assert not workbench.canonical_context["structural_roles"]
