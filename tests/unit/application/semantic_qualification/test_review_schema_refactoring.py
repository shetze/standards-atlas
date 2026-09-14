"""R2: current review contracts and explicit evidence levels; only synthetic decisions.

No real model calls or human annotations are made here. Rehashed-tampering tests
exercise semantic bindings, not a claim that local hashes authenticate an author.
"""

import copy
import hashlib
import json
import shutil

import pytest
import yaml
from test_partial_observations import RESOURCES
from test_qualification_campaign import source_files
from test_review_handoff import ready
from test_review_package import complete, make_review, publish

from standards_atlas.application.model.source_structure import structure_fingerprint
from standards_atlas.application.schema import (
    SCHEMA_POLICIES,
    SchemaPolicy,
    require_current_schema,
    require_supported_schema,
)
from standards_atlas.application.semantic_qualification.campaign_contract import (
    CAMPAIGN_SCHEMA_VERSION,
    REVIEW_ARCHIVE_NAME,
    REVIEW_BINDINGS_NAME,
    CampaignReviewEvidence,
    QualificationCampaignArtifact,
)
from standards_atlas.application.semantic_qualification.campaign_evaluation import evaluate_campaign
from standards_atlas.application.semantic_qualification.campaign_selection import (
    load_campaign,
    prepare_campaign,
    verify_prepared_campaign,
)
from standards_atlas.application.semantic_qualification.qualification_campaign_model import (
    QUALIFICATION_MANIFEST_SCHEMA_VERSION,
    QualificationCampaign,
)
from standards_atlas.application.semantic_qualification.review_package.build import (
    build_review_package,
)
from standards_atlas.application.semantic_qualification.review_package.handoff import (
    create_review_handoff,
    load_review_handoff,
)
from standards_atlas.application.semantic_qualification.review_package.model import (
    REVIEW_PUBLICATION_SCHEMA_VERSION,
    ReviewPublication,
)
from standards_atlas.application.semantic_qualification.review_package.publication import (
    load_bound_suite,
    publication_files,
    verify_publication,
)
from standards_atlas.application.semantic_qualification.review_package.workbench import (
    workbench_summary,
)
from standards_atlas.application.workflow.partial_qualification_plan import (
    plan_partial_qualification,
)

pytestmark = pytest.mark.filterwarnings(
    "error:partial-(qualification-manifest|qualification-campaign|review-publication)"
    " schema version"
    ":standards_atlas.application.schema.policy.SchemaDeprecationWarning"
)

KINDS = ("external_suites", "atlas_publication", "archived_handoff")
FAMILIES = {
    "partial-qualification-manifest": QUALIFICATION_MANIFEST_SCHEMA_VERSION,
    "partial-review-publication": REVIEW_PUBLICATION_SCHEMA_VERSION,
    "partial-qualification-campaign": CAMPAIGN_SCHEMA_VERSION,
}
BAD = ("1.0", "9.9", None, 1.1, True)


def hashes(root):
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob("*")
        if p.is_file()
    }


def reseal_plan(root, change):
    path = root / "campaign-plan.json"
    data = json.loads(path.read_bytes())
    change(data)
    data["campaign_sha256"] = structure_fingerprint(
        {k: v for k, v in data.items() if k != "campaign_sha256"}
    )
    path.write_text(json.dumps(data))
    return data


@pytest.fixture(scope="module")
def fixtures(tmp_path_factory):
    root = tmp_path_factory.mktemp("r2-current")
    result = {}
    for kind in KINDS:
        folder = root / kind
        folder.mkdir()
        if kind == "external_suites":
            manifest, _, _ = source_files(folder / "inputs", count=6, reviews=True)
        elif kind == "atlas_publication":
            package, manifest, _, spec = make_review(folder)
            complete(package)
            output = folder / "publication"
            publish(package, output)
            spec["semantic_suites"] = [
                str(output / f"{split}.yaml") for split in ("development", "holdout")
            ]
            manifest.write_text(yaml.safe_dump(spec))
        else:
            ready(folder, exposures=True)
            manifest = folder / "handoff/campaign.yaml"
        campaign = folder / "campaign"
        definition = prepare_campaign(manifest=manifest, output=campaign, resources=RESOURCES)
        result[kind] = (folder, manifest, campaign, definition)
    return result


@pytest.fixture(scope="module")
def payloads(fixtures):
    folder, manifest, _, artifact = fixtures["atlas_publication"]
    return {
        "manifest": (QualificationCampaign, yaml.safe_load(manifest.read_bytes())),
        "publication": (
            ReviewPublication,
            json.loads((folder / "publication/review-evidence.json").read_bytes()),
        ),
        "campaign": (QualificationCampaignArtifact, artifact),
    }


@pytest.mark.parametrize("family", FAMILIES)
def test_r2_reader_and_writer_contracts_are_current_only(family):
    current = FAMILIES[family]
    assert SCHEMA_POLICIES[family].current == current
    assert SCHEMA_POLICIES[family].readable == (current,)
    require_current_schema(family, current)
    require_supported_schema(family, current)
    for obsolete in BAD:
        with pytest.raises(ValueError):
            require_supported_schema(family, obsolete)
        with pytest.raises(ValueError):
            require_current_schema(family, obsolete)


@pytest.mark.parametrize("name", ("manifest", "publication", "campaign"))
@pytest.mark.parametrize("marker", BAD)
@pytest.mark.parametrize("encoding", ("mapping", "json", "instance"))
def test_obsolete_markers_fail_direct_and_serialized_reads(payloads, name, marker, encoding):
    cls, original = payloads[name]
    raw = copy.deepcopy(original)
    raw["schema_version"] = marker
    with pytest.raises(ValueError):
        if encoding == "mapping":
            cls.model_validate(raw)
        elif encoding == "json":
            cls.model_validate_json(json.dumps(raw))
        else:
            cls.model_validate(cls.model_validate(original).model_copy(update=raw))


@pytest.mark.parametrize("name", ("manifest", "publication", "campaign"))
def test_version_is_required_not_defaulted(payloads, name):
    cls, original = payloads[name]
    raw = copy.deepcopy(original)
    del raw["schema_version"]
    with pytest.raises(ValueError):
        cls.model_validate(raw)
    with pytest.raises(ValueError):
        cls.model_validate_json(json.dumps(raw))


@pytest.mark.parametrize("marker", (*BAD, "missing"))
def test_obsolete_embedded_manifest_is_not_upgraded(payloads, marker):
    cls, raw = payloads["campaign"]
    raw = copy.deepcopy(raw)
    if marker == "missing":
        del raw["specification"]["schema_version"]
    else:
        raw["specification"]["schema_version"] = marker
    with pytest.raises(ValueError):
        cls.model_validate(raw)


@pytest.mark.parametrize("kind", KINDS)
def test_current_wire_contract_roundtrips_without_evidence_becoming_targets(fixtures, kind):
    _, manifest, root, definition = fixtures[kind]
    assert definition["schema_version"] == "2.0"
    assert definition["review_evidence"] == {"kind": kind}
    assert QualificationCampaignArtifact.model_validate(definition).model_dump(mode="json") == (
        definition
    )
    assert load_campaign(root, RESOURCES)[0] == definition
    assert verify_prepared_campaign(manifest=manifest, campaign=root, resources=RESOURCES)
    assert (REVIEW_BINDINGS_NAME in definition["files"]) == (kind != "external_suites")
    assert (REVIEW_ARCHIVE_NAME in definition["files"]) == (kind == "archived_handoff")
    source = json.loads((root / "inputs/population.json").read_bytes())
    assert all(set(item) == {"id", "input"} for item in source)
    assert "review_evidence" not in json.dumps(source)
    before = hashes(root)
    report = evaluate_campaign(campaign=root, resources=RESOURCES)
    assert not report["activation_eligible"]
    # Evaluation may create its own report, but cannot modify any frozen input.
    for name, digest in before.items():
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == digest


@pytest.mark.parametrize("original,new", [(a, b) for a in KINDS for b in KINDS if a != b])
def test_rehashed_kind_change_never_reinterprets_evidence(fixtures, tmp_path, original, new):
    root = tmp_path / "campaign"
    shutil.copytree(fixtures[original][2], root)
    reseal_plan(root, lambda d: d.update(review_evidence={"kind": new}))
    before = hashes(root)
    with pytest.raises(ValueError):
        load_campaign(root, RESOURCES)
    assert hashes(root) == before


@pytest.mark.parametrize(
    "evidence", [None, {}, {"kind": "unknown"}, {"kind": "external_suites", "skip": True}]
)
def test_review_evidence_is_an_explicit_closed_contract(payloads, evidence):
    cls, raw = payloads["campaign"]
    with pytest.raises(ValueError):
        cls.model_validate({**raw, "review_evidence": evidence})
    omitted = {k: v for k, v in raw.items() if k != "review_evidence"}
    with pytest.raises(ValueError):
        cls.model_validate(omitted)


@pytest.mark.parametrize("name", [REVIEW_BINDINGS_NAME, REVIEW_ARCHIVE_NAME])
@pytest.mark.parametrize("remove_inventory", [False, True])
def test_missing_archive_or_binding_fails_even_after_resealing(
    fixtures, tmp_path, name, remove_inventory
):
    root = tmp_path / "campaign"
    shutil.copytree(fixtures["archived_handoff"][2], root)
    (root / name).unlink()
    if remove_inventory:
        reseal_plan(root, lambda d: d["files"].pop(name))
    with pytest.raises(ValueError):
        load_campaign(root, RESOURCES)


@pytest.mark.parametrize("retain_file", [False, True])
def test_handoff_cannot_drop_archive_by_changing_kind(fixtures, tmp_path, retain_file):
    root = tmp_path / "campaign"
    shutil.copytree(fixtures["archived_handoff"][2], root)
    if not retain_file:
        (root / REVIEW_ARCHIVE_NAME).unlink()

    def mutate(data):
        data["review_evidence"] = {"kind": "atlas_publication"}
        data["files"].pop(REVIEW_ARCHIVE_NAME)

    reseal_plan(root, mutate)
    with pytest.raises(ValueError, match="handoff"):
        load_campaign(root, RESOURCES)


@pytest.mark.parametrize(
    "name", [REVIEW_BINDINGS_NAME, REVIEW_ARCHIVE_NAME, "inputs/unlisted.json"]
)
def test_unlisted_physical_evidence_is_not_ignored(fixtures, tmp_path, name):
    root = tmp_path / "campaign"
    shutil.copytree(fixtures["external_suites"][2], root)
    (root / name).write_bytes(b"unlisted")
    with pytest.raises(ValueError, match="inventory"):
        load_campaign(root, RESOURCES)


@pytest.mark.parametrize("marker", ["1.0", "1.1", "1.2", None, "missing"])
def test_obsolete_campaign_fails_before_replay_or_resume_mutates_it(fixtures, tmp_path, marker):
    root = tmp_path / "campaign"
    shutil.copytree(fixtures["archived_handoff"][2], root)

    def mutate(data):
        if marker == "missing":
            data.pop("schema_version")
        else:
            data["schema_version"] = marker

    reseal_plan(root, mutate)
    before = hashes(root)
    with pytest.raises(ValueError, match="Unsupported partial qualification campaign schema"):
        evaluate_campaign(campaign=root, resources=RESOURCES)
    with pytest.raises(ValueError):
        verify_prepared_campaign(
            manifest=fixtures["archived_handoff"][1], campaign=root, resources=RESOURCES
        )
    assert hashes(root) == before


@pytest.mark.parametrize("marker", ["1.0", None, "missing"])
def test_obsolete_manifest_blocks_all_entrypoints_without_writes(fixtures, tmp_path, marker):
    folder, _, _, _ = fixtures["atlas_publication"]
    source = folder / "inputs/campaign.yaml"
    raw = yaml.safe_load(source.read_bytes())
    if marker == "missing":
        raw.pop("schema_version")
    else:
        raw["schema_version"] = marker
    manifest = tmp_path / "obsolete.yaml"
    manifest.write_text(yaml.safe_dump(raw))
    before = hashes(tmp_path)
    for operation in (
        lambda: QualificationCampaign.load(manifest),
        lambda: prepare_campaign(
            manifest=manifest, output=tmp_path / "campaign", resources=RESOURCES
        ),
        lambda: plan_partial_qualification(manifest, tmp_path / "workflow"),
        lambda: build_review_package(
            manifest=manifest, output=tmp_path / "review", resources=RESOURCES
        ),
        lambda: create_review_handoff(
            package=folder / "review",
            manifest=manifest,
            output=tmp_path / "handoff",
            resources=RESOURCES,
            holdout_declaration="Synthetic test only.",
        ),
    ):
        with pytest.raises(ValueError):
            operation()
    assert hashes(tmp_path) == before


@pytest.mark.parametrize("workbench", [None, "missing"])
def test_publication_cannot_omit_workbench_by_rehashing(payloads, workbench):
    cls, original = payloads["publication"]
    raw = copy.deepcopy(original)
    if workbench == "missing":
        del raw["workbench"]
    else:
        raw["workbench"] = workbench
    raw["evidence_sha256"] = structure_fingerprint(
        {k: v for k, v in raw.items() if k != "evidence_sha256"}
    )
    with pytest.raises(ValueError):
        cls.model_validate(raw)
    unsafe = cls.model_validate(original).model_copy(update={"workbench": None})
    with pytest.raises(ValueError):
        verify_publication(unsafe)
    with pytest.raises(ValueError):
        publication_files(unsafe, {})


def test_current_publication_distinguishes_no_journal_from_recorded_exposure(fixtures, payloads):
    cls, raw = payloads["publication"]
    publication = cls.model_validate(raw)
    assert not publication.workbench.journal_present
    assert workbench_summary(publication.workbench)["status"] == "not-recorded"
    assert workbench_summary(publication.workbench)["independence_proven"] is False
    handoff = load_review_handoff(fixtures["archived_handoff"][0] / "handoff")
    assert handoff.publication.workbench.journal_present
    assert workbench_summary(handoff.publication.workbench)["reveal_count"] == 1
    assert handoff.publication.schema_version == "1.1"


def test_obsolete_bound_publication_rejected_with_unchanged_suites(fixtures, tmp_path):
    root = tmp_path / "publication"
    shutil.copytree(fixtures["atlas_publication"][0] / "publication", root)
    path = root / "review-evidence.json"
    raw = json.loads(path.read_bytes())
    raw["schema_version"] = "1.0"
    path.write_text(json.dumps(raw))
    before = hashes(root)
    with pytest.raises(ValueError):
        load_bound_suite(root / "development.yaml", None, resources=RESOURCES)
    assert hashes(root) == before


@pytest.mark.parametrize("family", FAMILIES)
def test_writer_checks_registry_before_creating_output(fixtures, tmp_path, monkeypatch, family):
    # R4 does not permit synthetic legacy windows in the concrete registry.
    monkeypatch.setitem(SCHEMA_POLICIES, family, SchemaPolicy(family, "9.9", ("9.9",), "test"))
    folder, manifest, _, _ = fixtures["atlas_publication"]
    output = tmp_path / "output"
    with pytest.raises(ValueError, match="writers may only emit|Unsupported .* schema version"):
        if family == "partial-qualification-campaign":
            prepare_campaign(manifest=manifest, output=output, resources=RESOURCES)
        elif family == "partial-review-publication":
            publish(folder / "review", output)
        else:
            create_review_handoff(
                package=folder / "review",
                manifest=manifest,
                output=output,
                resources=RESOURCES,
                holdout_declaration="Synthetic test only.",
            )
    assert not output.exists()


def test_other_families_and_r1_guards_are_not_reopened():
    for family in (
        "partial-request-plan",
        "partial-semantic-observation",
        "partial-cascade-report",
    ):
        assert SCHEMA_POLICIES[family].readable == ("1.1",)
    assert SCHEMA_POLICIES["partial-semantic-reference"].current == "1.0"
    assert SCHEMA_POLICIES["partial-review-archive"].current == "1.0"
    assert SCHEMA_POLICIES["partial-review-handoff"].current == "1.0"
    assert CampaignReviewEvidence(kind="external_suites").input_names


def test_atlas_publication_can_coexist_with_explicit_external_development(fixtures, tmp_path):
    folder, _, campaign, _ = fixtures["atlas_publication"]
    spec = yaml.safe_load((folder / "inputs/campaign.yaml").read_bytes())
    population = json.loads((campaign / "inputs/population.json").read_bytes())
    case = population[0]
    external = {
        "schema_version": "1.0",
        "kind": "partial-semantic-reference",
        "id": "external-additional-development",
        "version": "1.0.0",
        "split": "development",
        "status": "published",
        "reviewed_by": "synthetic external reviewer",
        "review_reference": "synthetic independent external review",
        "cases": [
            {
                "example_id": case["id"],
                "document_key": case["input"]["context"]["document_key"],
                "content_hash": case["input"]["content"]["hash"],
                "attributes": {"role_semantics_present": {"equals": False}},
            }
        ],
    }
    path = tmp_path / "external.yaml"
    path.write_text(yaml.safe_dump(external))
    spec["semantic_suites"].append(str(path))
    manifest = tmp_path / "campaign.yaml"
    manifest.write_text(yaml.safe_dump(spec))
    root = tmp_path / "campaign"
    definition = prepare_campaign(manifest=manifest, output=root, resources=RESOURCES)
    assert definition["review_evidence"] == {"kind": "atlas_publication"}
    assert len(load_campaign(root, RESOURCES)[4]) == 3


@pytest.mark.parametrize("part", ["source-campaign.yaml", "campaign.yaml"])
def test_rehashed_handoff_with_embedded_obsolete_manifest_is_rejected(fixtures, tmp_path, part):
    root = tmp_path / "handoff"
    shutil.copytree(fixtures["archived_handoff"][0] / "handoff", root)
    path = root / part
    source = yaml.safe_load(path.read_bytes())
    source["schema_version"] = "1.0"
    raw = yaml.safe_dump(source).encode()
    path.write_bytes(raw)
    definition_path = root / "review-handoff.json"
    definition = json.loads(definition_path.read_bytes())
    definition["files"][part] = {"sha256": hashlib.sha256(raw).hexdigest(), "size": len(raw)}
    definition["handoff_sha256"] = structure_fingerprint(
        {k: v for k, v in definition.items() if k != "handoff_sha256"}
    )
    definition_path.write_text(json.dumps(definition))
    before = hashes(root)
    with pytest.raises(ValueError):
        load_review_handoff(root)
    assert hashes(root) == before


@pytest.mark.parametrize("target", ["inputs", "campaign-plan.json", "inputs/golden.json"])
def test_campaign_input_symlinks_never_bypass_inventory(fixtures, tmp_path, target):
    root = tmp_path / "campaign"
    shutil.copytree(fixtures["external_suites"][2], root)
    path = root / target
    outside = tmp_path / "linked"
    path.rename(outside)
    path.symlink_to(outside, target_is_directory=outside.is_dir())
    with pytest.raises(ValueError, match="unsafe"):
        load_campaign(root, RESOURCES)


@pytest.mark.parametrize("mutate", ["empty", "obsolete", "missing-workbench"])
def test_frozen_publication_replay_is_mandatory_even_after_rehash(fixtures, tmp_path, mutate):
    root = tmp_path / "campaign"
    shutil.copytree(fixtures["atlas_publication"][2], root)
    path = root / REVIEW_BINDINGS_NAME
    bindings = json.loads(path.read_bytes())
    if mutate == "empty":
        bindings.clear()
    elif mutate == "obsolete":
        bindings[0]["schema_version"] = "1.0"
    else:
        del bindings[0]["workbench"]
    raw = json.dumps(bindings).encode()
    path.write_bytes(raw)
    reseal_plan(
        root, lambda d: d["files"].update({REVIEW_BINDINGS_NAME: hashlib.sha256(raw).hexdigest()})
    )
    with pytest.raises(ValueError):
        load_campaign(root, RESOURCES)
