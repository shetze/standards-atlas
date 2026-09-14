"""Slice-4 end-to-end evidence, exclusively synthetic sources/reviewers/model proposals."""

import copy
import hashlib
import io
import json
import shutil
import stat
from pathlib import Path
from zipfile import ZipFile, ZipInfo

import pytest
import yaml
from test_partial_observations import RESOURCES
from test_review_package import complete, decide, make_review, publish, write_dataset
from test_review_preparation import selected
from test_review_workbench import correction, fixture, model_proposal, submit, view
from typer.testing import CliRunner

from standards_atlas.adapters.workflow.cli_renderer import CliWorkflowOperationRenderer
from standards_atlas.application.model.source_structure import structure_fingerprint
from standards_atlas.application.review_workbench.journal import reveal
from standards_atlas.application.semantic_qualification.campaign_activation import (
    activate_campaign,
    archive_campaign,
)
from standards_atlas.application.semantic_qualification.campaign_evaluation import evaluate_campaign
from standards_atlas.application.semantic_qualification.campaign_execution import run_campaign
from standards_atlas.application.semantic_qualification.campaign_selection import (
    load_campaign,
    prepare_campaign,
    verify_prepared_campaign,
)
from standards_atlas.application.semantic_qualification.qualification_campaign_model import (
    QualificationCampaign,
)
from standards_atlas.application.semantic_qualification.review_package.archive import (
    archive_review_package,
    encode_archive,
    verify_archive_bytes,
    verify_review_archive,
)
from standards_atlas.application.semantic_qualification.review_package.candidates import (
    build_candidate_index,
    load_candidate_index,
)
from standards_atlas.application.semantic_qualification.review_package.handoff import (
    create_review_handoff,
    load_review_handoff,
)
from standards_atlas.application.semantic_qualification.review_package.model import (
    ReviewPublication,
    WorkbenchState,
)
from standards_atlas.application.semantic_qualification.review_package.publication import (
    verify_publication,
)
from standards_atlas.application.semantic_qualification.review_package.service import load_review
from standards_atlas.application.semantic_qualification.review_package.validation import seal
from standards_atlas.application.semantic_qualification.review_package.workbench import (
    capture_workbench,
    workbench_summary,
)
from standards_atlas.application.workflow.models import WorkflowStage
from standards_atlas.application.workflow.partial_qualification_plan import (
    plan_partial_qualification,
)
from standards_atlas.cli import app

DECLARATION = "Synthetic fixture review only; no claim about production independence."
VALUES = {
    "primary_function": None,
    "primary_knowledge_kind": None,
    "role_semantics_present": False,
    "process_functions": [],
}


def expose(root):
    package, _ = load_review(root)
    case = next(c for c in package.cases if c.split == "holdout")
    model_proposal(root, case.example_id)
    package, state = load_review(root)
    reveal(
        root,
        view={
            "package_sha256": package.package_sha256,
            "revision": state.revision,
            "state_sha256": state.state_sha256,
            "example_id": case.example_id,
            "reviewer": "Synthetic human",
        },
        assessment="Independent synthetic initial assessment before seeing the recommendation.",
    )
    return case.example_id


def ready(tmp_path, *, exposures=False):
    root, manifest, items, spec = make_review(tmp_path)
    if exposures:
        expose(root)
    complete(root)
    output = tmp_path / "handoff"
    create_review_handoff(
        package=root,
        manifest=manifest,
        output=output,
        resources=RESOURCES,
        holdout_declaration=DECLARATION,
    )
    return root, manifest, output, items, spec


def archive_members(raw):
    with ZipFile(io.BytesIO(raw)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


_RENDERER = CliWorkflowOperationRenderer()


def _command(step) -> tuple[str, ...]:
    return _RENDERER.render(step.operation)


def test_unfinished_review_can_be_archived_but_never_handed_off(tmp_path):
    root, manifest, *_ = make_review(tmp_path)
    before = (root / "review-state.json").read_bytes()
    result = create_review_handoff(
        package=root,
        manifest=manifest,
        output=tmp_path / "handoff",
        resources=RESOURCES,
        holdout_declaration=DECLARATION,
        dry_run=True,
    )
    assert not result["importable"]
    with pytest.raises(ValueError, match="blocked"):
        create_review_handoff(
            package=root,
            manifest=manifest,
            output=tmp_path / "handoff",
            resources=RESOURCES,
            holdout_declaration=DECLARATION,
        )
    archive = archive_review_package(package=root, output=tmp_path / "unfinished.zip")
    assert archive["human_decisions_added"] == 0
    assert not archive["report"]["ready_for_publication"]
    assert (root / "review-state.json").read_bytes() == before
    assert not (tmp_path / "handoff").exists()


def test_publication_captures_reveals_and_distinguishes_absent_journal(tmp_path):
    root, _, *_ = make_review(tmp_path)
    complete(root)
    first = tmp_path / "first"
    publish(root, first)
    original = ReviewPublication.model_validate_json((first / "review-evidence.json").read_bytes())
    assert original.schema_version == "1.1"
    assert workbench_summary(original.workbench)["status"] == "not-recorded"
    case = expose(root)
    second = tmp_path / "second"
    publish(root, second)
    latest = ReviewPublication.model_validate_json((second / "review-evidence.json").read_bytes())
    assert latest.workbench.journal_present
    assert len(latest.workbench.history) == latest.workbench.state.revision
    assert latest.workbench.state.exposures[0].example_id == case
    assert latest.workbench.state.exposures[0].proposal_sha256s
    assert original.evidence_sha256 != latest.evidence_sha256
    assert verify_publication(original)  # Later live reveals cannot modify a published snapshot.


def test_obsolete_publication_cannot_be_revived_by_rehashing_without_evidence(tmp_path):
    root, *_ = make_review(tmp_path)
    complete(root)
    output = tmp_path / "published"
    publish(root, output)
    raw = json.loads((output / "review-evidence.json").read_bytes())
    raw.pop("workbench")
    raw["schema_version"] = "1.0"
    raw["evidence_sha256"] = structure_fingerprint(
        {k: v for k, v in raw.items() if k != "evidence_sha256"}
    )
    with pytest.raises(ValueError):
        ReviewPublication.model_validate(raw)


@pytest.mark.parametrize("change", ["missing-state", "missing-history", "source", "proposal"])
def test_invalid_exposure_history_blocks_publication_without_partial_output(tmp_path, change):
    root, *_ = make_review(tmp_path)
    expose(root)
    complete(root)
    if change == "missing-state":
        (root / "workbench/state.json").unlink()
    elif change == "missing-history":
        next((root / "workbench/history").glob("*.json")).unlink()
    else:
        path = root / "workbench/state.json"
        raw = json.loads(path.read_bytes())
        if change == "source":
            raw["exposures"][0]["source_sha256"] = "0" * 64
        else:
            raw["exposures"][0]["proposal_sha256s"] = ["0" * 64]
        forged = seal(WorkbenchState, raw, "workbench_sha256")
        path.write_text(forged.model_dump_json())
    with pytest.raises(ValueError):
        publish(root, tmp_path / "published")
    assert not (tmp_path / "published").exists()


def test_selection_preserves_entire_holdout_audit_and_human_history(tmp_path):
    root, *_ = make_review(tmp_path)
    expose(root)
    complete(root)
    package, state = load_review(root)
    before = capture_workbench(root, package, state)
    receipt = build_candidate_index(root)
    _, _, index = load_candidate_index(root, receipt["index_sha256"])
    derived, _ = selected(root, index, tmp_path)
    newer, new_state = load_review(derived)
    after = capture_workbench(derived, newer, new_state)
    assert before.state.exposures == after.state.exposures
    assert before.state.revision == after.state.revision
    assert before.state.package_sha256 != after.state.package_sha256
    assert state.decisions == new_state.decisions
    assert {c.example_id for c in package.cases if c.split == "holdout"} == {
        c.example_id for c in newer.cases if c.split == "holdout"
    }
    archived = archive_review_package(package=derived, output=tmp_path / "selected.zip")
    assert archived["workbench"]["reveal_count"] == 1
    assert not archived["report"]["ready_for_publication"]  # Newly selected tasks remain open.


def test_archive_is_deterministic_idempotent_and_offline(tmp_path, monkeypatch):
    root, _, *_ = make_review(tmp_path)
    expose(root)
    complete(root)
    archive = tmp_path / "review.zip"
    first = archive_review_package(package=root, output=archive)
    raw = archive.read_bytes()
    assert archive_review_package(package=root, output=archive) == first
    assert archive.read_bytes() == raw
    shutil.rmtree(root)
    shutil.rmtree(tmp_path / "inputs")
    monkeypatch.chdir(tmp_path)
    assert verify_review_archive(archive)["frozen_evidence_verified"]
    snapshot = verify_archive_bytes(raw)
    assert len(snapshot.workbench.state.exposures) == 1
    assert not snapshot.summary()["live_sources_verified"]
    assert all(".lock" not in name for name in archive_members(raw))


def test_archive_does_not_overwrite_newer_or_changed_review(tmp_path):
    root, *_ = make_review(tmp_path)
    archive = tmp_path / "review.zip"
    archive_review_package(package=root, output=archive)
    before = archive.read_bytes()
    complete(root)
    with pytest.raises(ValueError, match="different evidence"):
        archive_review_package(package=root, output=archive)
    assert archive.read_bytes() == before


@pytest.mark.parametrize("member", ["review-state.json", "history", "symlink", "writer", "unknown"])
def test_archive_rejects_unsafe_or_mutated_live_package(tmp_path, member):
    root, *_ = make_review(tmp_path)
    complete(root)
    if member == "review-state.json":
        path = root / member
        value = json.loads(path.read_bytes())
        value["decisions"][0]["reviewer"] = "forged"
        path.write_text(json.dumps(value))
    elif member == "history":
        path = next((root / "history").glob("*.json"))
        value = json.loads(path.read_bytes())
        value["revision"] = 999
        path.write_text(json.dumps(value))
    elif member == "symlink":
        (root / "injected").symlink_to(tmp_path / "inputs")
    elif member == "writer":
        (root / "preparation").mkdir()
        (root / "preparation/.index.review-write.lock").write_text("123")
    else:
        (root / "secret.env").write_text("not automatically exported")
    with pytest.raises(ValueError):
        archive_review_package(package=root, output=tmp_path / "review.zip")
    assert not (tmp_path / "review.zip").exists()


@pytest.mark.parametrize("name", ["../escape", "/absolute", "a\\b", "a/./b", "a//b"])
def test_untrusted_archive_paths_are_rejected_without_extraction(tmp_path, name):
    stream = io.BytesIO()
    with ZipFile(stream, "w") as archive:
        archive.writestr(name, "untrusted")
    with pytest.raises(ValueError, match="unsafe"):
        verify_archive_bytes(stream.getvalue())
    assert not (tmp_path / "escape").exists()


def test_archive_duplicate_symlink_and_expanded_size_limits(tmp_path, monkeypatch):
    root, *_ = make_review(tmp_path)
    archive_path = tmp_path / "review.zip"
    archive_review_package(package=root, output=archive_path)
    raw = archive_path.read_bytes()
    stream = io.BytesIO(raw)
    with pytest.warns(UserWarning, match="Duplicate"):
        with ZipFile(stream, "a") as archive:
            archive.writestr("package/review-state.json", "{}")
    with pytest.raises(ValueError, match="duplicate"):
        verify_archive_bytes(stream.getvalue())
    stream = io.BytesIO()
    with ZipFile(stream, "w") as archive:
        info = ZipInfo("package/link")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(info, "outside")
    with pytest.raises(ValueError, match="unsafe"):
        verify_archive_bytes(stream.getvalue())
    import standards_atlas.application.semantic_qualification.review_package.archive as module

    monkeypatch.setattr(module, "MAX_MEMBER_BYTES", 100)
    with pytest.raises(ValueError, match="oversized"):
        verify_archive_bytes(raw)


def test_archive_inventory_and_review_tampering_are_independently_detected(tmp_path):
    root, *_ = make_review(tmp_path)
    archive = tmp_path / "review.zip"
    archive_review_package(package=root, output=archive)
    files = archive_members(archive.read_bytes())
    files["package/review-state.json"] += b" "
    with pytest.raises(ValueError, match="fingerprint"):
        verify_archive_bytes(encode_archive(files))
    # Rehashing the transport inventory cannot make forged semantic review evidence valid.
    value = json.loads(files["package/review-state.json"])
    value["revision"] = 999
    files["package/review-state.json"] = json.dumps(value).encode()
    manifest = json.loads(files["archive-manifest.json"])
    raw = files["package/review-state.json"]
    manifest["files"]["package/review-state.json"] = {
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size": len(raw),
    }
    manifest["archive_sha256"] = structure_fingerprint(
        {k: v for k, v in manifest.items() if k != "archive_sha256"}
    )
    files["archive-manifest.json"] = json.dumps(manifest).encode()
    with pytest.raises(ValueError, match="state/package"):
        verify_archive_bytes(encode_archive(files))


def test_handoff_is_atomic_idempotent_and_does_not_change_the_source_manifest(tmp_path):
    root, manifest, *_ = make_review(tmp_path)
    complete(root)
    before = manifest.read_bytes()
    output = tmp_path / "handoff"
    kwargs = dict(
        package=root,
        manifest=manifest,
        output=output,
        resources=RESOURCES,
        holdout_declaration=DECLARATION,
        campaign_id="reviewed-campaign",
    )
    first = create_review_handoff(**kwargs)
    assert create_review_handoff(**kwargs) == first
    assert manifest.read_bytes() == before
    assert not first["models_started"] and not first["activation_performed"]
    generated = QualificationCampaign.load(output / "campaign.yaml")
    original = QualificationCampaign.load(manifest)
    assert generated.id == "reviewed-campaign"
    assert generated.review_bundle == output
    assert generated.semantic_suites == ()
    for field in (
        "golden",
        "variants",
        "baseline",
        "candidate",
        "sample_size",
        "seed",
        "repetitions",
        "minimum_published_golden_cases",
        "required_semantic_attributes",
        "max_semantic_errors",
        "max_semantic_unavailable",
        "max_request_ratio",
        "efficient_target",
    ):
        assert getattr(generated, field) == getattr(original, field)


def test_handoff_does_not_overwrite_previous_exposure_snapshot(tmp_path):
    root, manifest, output, *_ = ready(tmp_path)
    before = (output / "review-handoff.json").read_bytes()
    expose(root)
    with pytest.raises(ValueError, match="never overwritten"):
        create_review_handoff(
            package=root,
            manifest=manifest,
            output=output,
            resources=RESOURCES,
            holdout_declaration=DECLARATION,
        )
    assert (output / "review-handoff.json").read_bytes() == before
    assert load_review_handoff(output).publication.workbench.state.exposures == ()


def test_missing_holdout_declaration_never_creates_a_publication(tmp_path):
    root, manifest, *_ = make_review(tmp_path)
    complete(root)
    result = create_review_handoff(
        package=root,
        manifest=manifest,
        output=None,
        resources=RESOURCES,
        dry_run=True,
    )
    assert result["import_blockers"] == [
        "publication needs an explicit human holdout-use declaration"
    ]


def test_handoff_io_failure_leaves_no_half_published_pair(tmp_path, monkeypatch):
    root, manifest, *_ = make_review(tmp_path)
    complete(root)
    import standards_atlas.application.semantic_qualification.review_package.storage as storage

    def fail(*args):
        raise OSError("synthetic directory commit failure")

    monkeypatch.setattr(storage.os, "rename", fail)
    output = tmp_path / "handoff"
    with pytest.raises(OSError, match="commit failure"):
        create_review_handoff(
            package=root,
            manifest=manifest,
            output=output,
            resources=RESOURCES,
            holdout_declaration=DECLARATION,
        )
    assert not output.exists()
    assert not list(tmp_path.glob(".handoff*"))


@pytest.mark.parametrize("change", ["text", "context", "golden-input", "new-golden-overlap"])
def test_source_and_reference_drift_block_handoff_before_campaign_start(tmp_path, change):
    root, manifest, _, _, spec = ready(tmp_path)
    if change in {"text", "context"}:

        def mutate(data):
            case = data["examples"][0]
            if change == "context":
                case["input"]["context"]["heading"] = "Different source heading"
            else:
                case["input"]["content"]["text"] += " changed"

        write_dataset(spec, mutate)
    elif change == "golden-input":
        path = Path(spec["golden"])
        path.write_text(path.read_text() + "\n# changed input bytes\n")
    else:
        package, _ = load_review(root)
        case = next(c for c in package.cases if c.split == "holdout")
        source = next(s for s in package.population if s.example_id == case.example_id)
        golden = yaml.safe_load(Path(spec["golden"]).read_bytes())
        extra = copy.deepcopy(golden["cases"][0])
        extra.update(
            clause_id=source.clause_id, reference=source.reference, text=source.text, status="draft"
        )
        golden["cases"].append(extra)
        path = tmp_path / "new-golden.yaml"
        path.write_text(yaml.safe_dump(golden))
        spec["golden"] = str(path)
        manifest.write_text(yaml.safe_dump(spec))
    with pytest.raises(ValueError):
        create_review_handoff(
            package=root,
            manifest=manifest,
            output=tmp_path / "second",
            resources=RESOURCES,
            holdout_declaration=DECLARATION,
        )
    assert not (tmp_path / "second").exists()


def test_workflow_preflight_precedes_freeze_and_never_runs_an_approval_command(tmp_path):
    _, manifest, output, *_ = ready(tmp_path)
    plan = plan_partial_qualification(output / "campaign.yaml", tmp_path / "evaluations")
    commands = [_command(step)[4] for step in plan.steps]
    assert commands == [
        "partial-review-check-handoff",
        "partial-qualification-prepare",
        "partial-qualification-run",
        "partial-qualification-evaluate",
    ]
    assert plan.steps[0].stage == WorkflowStage.REVIEW
    assert not any(step.manual_gate for step in plan.steps)
    assert len(plan_partial_qualification(manifest, tmp_path / "legacy").steps) == 3


def test_bundle_relocation_keeps_hashes_and_resolves_only_new_manifest_pointer(tmp_path):
    _, _, output, *_ = ready(tmp_path)
    moved = tmp_path / "moved"
    shutil.copytree(output, moved)
    original = load_review_handoff(output)
    current = load_review_handoff(moved, live=True, resources=RESOURCES)
    assert current.definition == original.definition
    assert current.specification.review_bundle == moved
    assert QualificationCampaign.load(moved / "campaign.yaml") == current.specification


def test_frozen_campaign_is_independent_of_live_review_and_contains_no_labels_in_requests(tmp_path):
    root, _, output, *_ = ready(tmp_path, exposures=True)
    campaign = tmp_path / "campaign"
    definition = prepare_campaign(
        manifest=output / "campaign.yaml",
        output=campaign,
        resources=RESOURCES,
    )
    assert definition["schema_version"] == "2.0"
    assert definition["review_evidence"] == {"kind": "archived_handoff"}
    assert "inputs/review-package.zip" in definition["files"]
    frozen_bytes = (campaign / "inputs/review-package.zip").read_bytes()
    assert verify_archive_bytes(frozen_bytes).workbench.state.exposures
    for path in (campaign / "datasets").glob("*.json"):
        raw = path.read_text()
        assert "SENTINEL-MODEL-RATIONALE" not in raw
        assert "Synthetic human" not in raw
        assert "reviewer" not in raw
        assert all(not e["expected"] for e in json.loads(raw)["examples"])
    shutil.rmtree(root)
    shutil.rmtree(output)
    shutil.rmtree(tmp_path / "inputs")
    assert load_campaign(campaign, RESOURCES)[0] == definition
    planned = run_campaign(campaign=campaign, resources=RESOURCES, execute=False)
    assert planned["jobs"]
    evaluation = evaluate_campaign(campaign=campaign, resources=RESOURCES)
    assert not evaluation["activation_eligible"]
    with pytest.raises(ValueError, match="activation blocked"):
        activate_campaign(
            campaign=campaign,
            output=tmp_path / "activation",
            resources=RESOURCES,
            reviewer="Synthetic human",
            review_reference="fixture-only",
        )
    assert not (tmp_path / "activation").exists()


def test_final_qualification_archive_retains_the_nested_review_zip(tmp_path):
    _, _, output, *_ = ready(tmp_path, exposures=True)
    campaign = tmp_path / "campaign"
    prepare_campaign(manifest=output / "campaign.yaml", output=campaign, resources=RESOURCES)
    result = archive_campaign(campaign=campaign, output=tmp_path / "archives", resources=RESOURCES)
    with ZipFile(result) as archive:
        member = next(n for n in archive.namelist() if n.endswith("inputs/review-package.zip"))
        frozen = verify_archive_bytes(archive.read(member))
        assert len(frozen.workbench.state.exposures) == 1
        assert any(n.endswith("semantic-review-bindings.json") for n in archive.namelist())


@pytest.mark.parametrize(
    "name",
    [
        "review/development.yaml",
        "review/holdout.yaml",
        "review/review-evidence.json",
        "review/review-report.json",
        "review-package.zip",
        "source-campaign.yaml",
        "campaign.yaml",
    ],
)
def test_tampered_handoff_members_block_preflight_and_frozen_reuse(tmp_path, name):
    _, _, output, *_ = ready(tmp_path)
    campaign = tmp_path / "campaign"
    prepare_campaign(manifest=output / "campaign.yaml", output=campaign, resources=RESOURCES)
    path = output / name
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="changed"):
        load_review_handoff(output, resources=RESOURCES, live=True)
    with pytest.raises(ValueError):
        verify_prepared_campaign(
            manifest=output / "campaign.yaml",
            campaign=campaign,
            resources=RESOURCES,
        )
    assert load_campaign(campaign, RESOURCES)  # Frozen bytes were not retroactively changed.


def test_frozen_archive_tampering_blocks_evaluation_even_with_recomputed_plan_hash(tmp_path):
    _, _, output, *_ = ready(tmp_path)
    campaign = tmp_path / "campaign"
    prepare_campaign(manifest=output / "campaign.yaml", output=campaign, resources=RESOURCES)
    archive_path = campaign / "inputs/review-package.zip"
    files = archive_members(archive_path.read_bytes())
    files.pop("package/review-state.json")
    raw = encode_archive(files)
    archive_path.write_bytes(raw)
    path = campaign / "campaign-plan.json"
    definition = json.loads(path.read_bytes())
    definition["files"]["inputs/review-package.zip"] = hashlib.sha256(raw).hexdigest()
    definition["campaign_sha256"] = structure_fingerprint(
        {k: v for k, v in definition.items() if k != "campaign_sha256"}
    )
    path.write_text(json.dumps(definition))
    with pytest.raises(ValueError, match="inventory"):
        evaluate_campaign(campaign=campaign, resources=RESOURCES)


def test_browser_to_handoff_to_campaign_full_human_path(tmp_path):
    root, _, client = fixture(tmp_path)
    package, _ = load_review(root)
    holdout = next(c for c in package.cases if c.split == "holdout")
    model_proposal(root, holdout.example_id)
    data = view(client, holdout.example_id)
    assert not data["proposals"]
    assert (
        client.post(
            "/api/packages/review/reveal",
            json={
                "view_token": data["view_token"],
                "assessment": "Synthetic first independent assessment",
            },
        ).status_code
        == 200
    )
    for case in package.cases:
        data = view(client, case.example_id)
        response = submit(
            client, data, [correction(data, attribute=a, value=VALUES[a]) for a in case.attributes]
        )
        assert response.status_code == 200, response.text
    output = tmp_path / "handoff"
    result = create_review_handoff(
        package=root,
        manifest=tmp_path / "inputs/campaign.yaml",
        output=output,
        resources=RESOURCES,
        holdout_declaration=DECLARATION,
    )
    assert result["workbench"]["reveal_count"] == 1
    campaign = tmp_path / "campaign"
    prepare_campaign(manifest=output / "campaign.yaml", output=campaign, resources=RESOURCES)
    suites = load_campaign(campaign, RESOURCES)[4]
    assert all(s.status == "published" for s in suites)
    assert all(
        c.attributes["role_semantics_present"].equals is False for s in suites for c in s.cases
    )
    assert all(c.attributes["process_functions"].equals == [] for s in suites for c in s.cases)
    assert not evaluate_campaign(campaign=campaign, resources=RESOURCES)["activation_eligible"]


def test_cli_handoff_preflight_archive_and_workflow_have_no_manual_hash_fields(tmp_path):
    root, manifest, *_ = make_review(tmp_path)
    runner = CliRunner()
    for command in (
        "partial-review-archive",
        "partial-review-verify-archive",
        "partial-review-handoff",
        "partial-review-check-handoff",
    ):
        assert runner.invoke(app, ["evaluation", command, "--help"]).exit_code == 0
    args = [
        "evaluation",
        "partial-review-handoff",
        "--package",
        str(root),
        "--manifest",
        str(manifest),
        "--dry-run",
    ]
    result = runner.invoke(app, args)
    assert result.exit_code == 1
    complete(root)
    output = tmp_path / "handoff"
    result = runner.invoke(
        app, [*args[:-1], "--output", str(output), "--holdout-declaration", DECLARATION]
    )
    assert result.exit_code == 0, result.output
    checked = runner.invoke(
        app, ["evaluation", "partial-review-check-handoff", "--bundle", str(output)]
    )
    assert checked.exit_code == 0, checked.output
    verified = runner.invoke(
        app,
        [
            "evaluation",
            "partial-review-verify-archive",
            "--archive",
            str(output / "review-package.zip"),
        ],
    )
    assert verified.exit_code == 0, verified.output
    planned = runner.invoke(
        app,
        [
            "workflow",
            "plan",
            "--task",
            "qualification",
            "--manifests",
            str(output / "campaign.yaml"),
        ],
    )
    assert planned.exit_code == 0, planned.output
    assert planned.output.index("partial-review-check-handoff") < planned.output.index(
        "partial-qualification-prepare"
    )
    assert "partial-qualification-activate" not in planned.output


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_semantic_errors", 99),
        ("max_request_ratio", 9.0),
        ("seed", 111),
    ],
)
def test_rehashed_handoff_cannot_silently_change_comparison_or_quality_policy(
    tmp_path, field, value
):
    _, _, output, *_ = ready(tmp_path)
    path = output / "campaign.yaml"
    spec = yaml.safe_load(path.read_bytes())
    spec[field] = value
    path.write_text(yaml.safe_dump(spec))
    definition_path = output / "review-handoff.json"
    definition = json.loads(definition_path.read_bytes())
    raw = path.read_bytes()
    definition["files"]["campaign.yaml"] = {
        "size": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }
    definition["handoff_sha256"] = structure_fingerprint(
        {k: v for k, v in definition.items() if k != "handoff_sha256"}
    )
    definition_path.write_text(json.dumps(definition))
    with pytest.raises(ValueError, match="changed campaign"):
        load_review_handoff(output)


@pytest.mark.parametrize("schema", ["1.0", "1.1", "1.2"])
def test_downgrade_cannot_discard_frozen_review_archive(tmp_path, schema):
    _, _, output, *_ = ready(tmp_path)
    campaign = tmp_path / "campaign"
    prepare_campaign(manifest=output / "campaign.yaml", output=campaign, resources=RESOURCES)
    path = campaign / "campaign-plan.json"
    definition = json.loads(path.read_bytes())
    definition["schema_version"] = schema
    definition["files"].pop("inputs/review-package.zip")
    (campaign / "inputs/review-package.zip").unlink()
    definition["campaign_sha256"] = structure_fingerprint(
        {k: v for k, v in definition.items() if k != "campaign_sha256"}
    )
    path.write_text(json.dumps(definition))
    with pytest.raises(ValueError):
        load_campaign(campaign, RESOURCES)


def test_deferred_human_attribute_cannot_be_replaced_by_a_model_recommendation(tmp_path):
    root, manifest, output, *_ = ready(tmp_path)
    package, _ = load_review(root)
    case = next(c for c in package.cases if c.split == "holdout")
    decide(
        root,
        case.example_id,
        "role_semantics_present",
        status="deferred",
        comment="Synthetic reviewer explicitly reopens a previously confirmed decision.",
    )
    model_proposal(root, case.example_id, value=False)
    result = create_review_handoff(
        package=root,
        manifest=manifest,
        output=None,
        resources=RESOURCES,
        dry_run=True,
        holdout_declaration=DECLARATION,
    )
    assert not result["importable"]
    assert not result["ready_for_publication"]
    assert load_review_handoff(output).publication.status == "published"


def test_preflight_is_not_cached_as_a_review_marker(tmp_path):
    from standards_atlas.adapters.workflow.artifact_store import FileSystemWorkflowArtifactStore

    _, _, output, *_ = ready(tmp_path)
    plan = plan_partial_qualification(output / "campaign.yaml", tmp_path / "evaluations")
    store = FileSystemWorkflowArtifactStore()
    assert not store.outputs_exist(plan.steps[0], tmp_path)
    store.record_completion(plan.steps[0], tmp_path)
    assert not store.outputs_exist(plan.steps[0], tmp_path)


def test_handoff_dry_run_checks_full_archive_without_writing(tmp_path):
    root, manifest, *_ = make_review(tmp_path)
    complete(root)
    state = (root / "review-state.json").read_bytes()
    kwargs = dict(
        package=root,
        manifest=manifest,
        resources=RESOURCES,
        holdout_declaration=DECLARATION,
    )
    preview = create_review_handoff(**kwargs, output=None, dry_run=True)
    assert preview["handoff_ready"] and preview["frozen_evidence_verified"]
    assert preview["human_decisions_added"] == 0
    assert (root / "review-state.json").read_bytes() == state
    assert not (root / ".handoff-preview").exists()
    result = create_review_handoff(**kwargs, output=tmp_path / "handoff")
    assert result["archive_sha256"] == preview["archive_sha256"]


@pytest.mark.parametrize("unexpected", [".env", "preparation/.selection.lock"])
def test_handoff_dry_run_cannot_ignore_unsafe_or_active_archive_files(tmp_path, unexpected):
    root, manifest, *_ = make_review(tmp_path)
    complete(root)
    extra = root / unexpected
    extra.parent.mkdir(parents=True, exist_ok=True)
    extra.write_text("synthetic unexpected payload")
    with pytest.raises(ValueError, match="unexpected/active-writer"):
        create_review_handoff(
            package=root,
            manifest=manifest,
            output=None,
            resources=RESOURCES,
            holdout_declaration=DECLARATION,
            dry_run=True,
        )


@pytest.mark.parametrize("kind", ["semantic", "sentinel"])
def test_new_source_manifest_cannot_discard_unreviewed_known_cases(tmp_path, kind):
    root, manifest, *_ = make_review(tmp_path)
    complete(root)
    package, _ = load_review(root)
    present = {case.example_id for case in package.cases}
    source = next(s for s in package.population if s.example_id not in present)
    case = dict(
        example_id=source.example_id,
        document_key=source.document_key,
        content_hash=source.content_hash,
    )
    data = yaml.safe_load(manifest.read_bytes())
    if kind == "semantic":
        extra = tmp_path / "additional-semantic.yaml"
        extra.write_text(
            yaml.safe_dump(
                dict(
                    schema_version="1.0",
                    kind="partial-semantic-reference",
                    id="new-known",
                    version="1.0.0",
                    split="development",
                    status="draft",
                    cases=[dict(**case, attributes={"role_semantics_present": {"equals": False}})],
                )
            )
        )
        data["semantic_suites"] = [*data.get("semantic_suites", []), str(extra)]
    else:
        extra = tmp_path / "additional-sentinel.json"
        extra.write_text(json.dumps(dict(cases=[case])))
        data["sentinel_suites"] = [*data.get("sentinel_suites", []), str(extra)]
    other = tmp_path / "new-campaign.yaml"
    other.write_text(yaml.safe_dump(data))
    with pytest.raises(ValueError, match="unreviewed"):
        create_review_handoff(
            package=root,
            manifest=other,
            output=tmp_path / "handoff",
            resources=RESOURCES,
            holdout_declaration=DECLARATION,
        )
    assert not (tmp_path / "handoff").exists()
