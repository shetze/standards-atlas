"""Private baselines freeze evidence and refuse incomplete/corrupt source collections."""

import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

import pytest
import yaml

from standards_atlas.adapters.evaluation.archive_receipt import write_archive_receipt
from standards_atlas.adapters.workflow.baseline_archive import archive_enrichment_baseline


def setup_project(root: Path, *, failures=1):
    def write(name, text):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    manifest = {
        "schema_version": 2,
        "manifest_type": "standards",
        "knowledge_domains": [],
        "industry_sectors": [],
        "families": [
            {
                "key": "EXAMPLE",
                "name": "Example",
                "organization": "Test",
                "publication_year": 2025,
                "source": {"pdf": "local/example.pdf"},
                "atlasdata": {"path": "data/EXAMPLE"},
            }
        ],
    }
    write("manifests/standards.yaml", yaml.safe_dump(manifest))
    write("data/EXAMPLE", "reviewed structure")
    write(".atlas/data/documents/EXAMPLE.json", '{"document": "canonical"}')
    write("cfg/context-enrichment.yaml", "test configuration")
    write("src/standards_atlas/dummy.py", "# frozen code\n")
    ledger = {
        "schema_version": 1,
        "document_key": "EXAMPLE",
        "completed_at": "2026-09-09T20:00:00Z",
        "status": "partial" if failures else "completed",
        "outcomes_complete": True,
        "config": "cfg/context-enrichment.yaml",
        "config_sha256": hashlib.sha256(b"test configuration").hexdigest(),
        "summary": {
            "candidates": 2,
            "succeeded": 2 - failures,
            "reused": 0,
            "protected": 0,
            "failed": failures,
            "not_candidate": 0,
            "failed_with_retained_value": failures,
            "unresolved_scope_targets": 0,
            "unresolved_reference_targets": 1,
            "routing_corrections": 0,
        },
    }
    write(".atlas/data/evaluation/context-routing/EXAMPLE-run.json", json.dumps(ledger))
    write(".atlas/data/evaluation/context-routing/EXAMPLE-failures.json", '{"failures": ["bad"]}')
    write(".atlas/data/evaluation/context-routing/EXAMPLE-unresolved-targets.json", "{}")
    return {
        "project_root": root,
        "workspace": Path(".atlas/data"),
        "document_keys": ("EXAMPLE",),
        "manifest_paths": (Path("manifests/standards.yaml"),),
        "selection": "test",
        "phase": "context",
        "reports_root": Path("local/review/test"),
        "output": Path("local/review/test/context-baseline.json"),
    }


def test_receipt_and_all_members_have_verified_bytes_without_overwrites(tmp_path):
    args = setup_project(tmp_path)
    first = archive_enrichment_baseline(**args)
    data = Path(first["archive"]).read_bytes()
    assert hashlib.sha256(data).hexdigest() == first["archive_sha256"]
    assert Path(first["archive"]).stat().st_mode & 0o077 == 0
    assert first["summary"]["failed_with_retained_value"] == 1
    assert first["status"] == "completed_with_context_failures"
    second = archive_enrichment_baseline(**args)
    assert first["archive"] != second["archive"]
    assert Path(first["archive"]).read_bytes() == data
    with ZipFile(first["archive"]) as zipped:
        members = json.loads(zipped.read("manifest.json"))["files"]
        assert set(zipped.namelist()) == {m["path"] for m in members} | {"manifest.json"}
        for item in members:
            assert hashlib.sha256(zipped.read(item["path"])).hexdigest() == item["sha256"]
        assert zipped.read("code/src/standards_atlas/dummy.py") == b"# frozen code\n"
    assert json.loads((tmp_path / args["output"]).read_text())["archive"] == second["archive"]


@pytest.mark.parametrize(
    "name", ["EXAMPLE-run.json", "EXAMPLE-failures.json", "EXAMPLE-unresolved-targets.json"]
)
def test_missing_required_diagnostics_are_not_a_successful_baseline(tmp_path, name):
    args = setup_project(tmp_path)
    (tmp_path / ".atlas/data/evaluation/context-routing" / name).unlink()
    with pytest.raises(ValueError, match="missing baseline input"):
        archive_enrichment_baseline(**args)
    assert not (tmp_path / args["output"]).exists()


def test_source_changes_after_the_document_run_require_a_new_report(tmp_path):
    args = setup_project(tmp_path)
    (tmp_path / "cfg/context-enrichment.yaml").write_text("different configuration")
    with pytest.raises(ValueError, match="configuration changed"):
        archive_enrichment_baseline(**args)


@pytest.mark.parametrize(
    "output",
    [
        "data/enrichments/baseline.json",
        ".atlas/data/documents/EXAMPLE.json",
        "cfg/context-enrichment.yaml",
    ],
)
def test_receipt_cannot_overwrite_inputs_or_publish_private_diagnostics(tmp_path, output):
    args = setup_project(tmp_path)
    args["output"] = Path(output)
    with pytest.raises(ValueError, match="private|overwrite"):
        archive_enrichment_baseline(**args)


def test_zero_failures_with_unresolved_targets_is_completed_not_verified(tmp_path):
    args = setup_project(tmp_path, failures=0)
    result = archive_enrichment_baseline(**args, corpus_count=50, limit=10)
    assert result["status"] == "completed"
    assert result["semantically_verified"] is False
    assert result["summary"]["unresolved_reference_targets"] == 1
    assert result["coverage"] == {
        "context": "all context candidates of selected documents",
        "semantic": "sampled",
        "corpus_count": 50,
        "limit": 10,
    }


def _published(root, args):
    reports = root / args["reports_root"]
    archive_enrichment_baseline(**args)
    for name in ("adopt", "export", "reimport", "cbox"):
        (reports / f"{name}.json").write_text("{}")
    run = root / "qualification.zip"
    with ZipFile(run, "w") as zipped:
        zipped.writestr("archive-manifest.json", json.dumps({"matrix_id": "test"}))
    write_archive_receipt(reports / "archive.json", archive=run, matrix_id="test")
    companion = root / "data/enrichments/EXAMPLE.yaml"
    companion.parent.mkdir(parents=True, exist_ok=True)
    payload = b'{"private": "source"}\n'
    digest = hashlib.sha256(payload).hexdigest()
    evidence = root / f".atlas/data/knowledge-evidence/{digest}.json"
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_bytes(payload)
    (evidence.parent / "unrelated.json").write_text("unrelated")
    companion.write_text(yaml.safe_dump({"fingerprints": {"private_value": f"sha256:{digest}"}}))
    return {**args, "phase": "published", "output": reports / "published-baseline.json"}, evidence


def test_published_archive_includes_only_referenced_private_blobs(tmp_path):
    args, evidence = _published(tmp_path, setup_project(tmp_path))
    result = archive_enrichment_baseline(**args)
    with ZipFile(result["archive"]) as zipped:
        assert f"knowledge-evidence/{evidence.name}" in zipped.namelist()
        assert "knowledge-evidence/unrelated.json" not in zipped.namelist()
        assert "qualification/run.zip" in zipped.namelist()


def test_corrupt_private_evidence_or_qualification_is_fatal(tmp_path):
    args, evidence = _published(tmp_path, setup_project(tmp_path))
    original = evidence.read_bytes()
    evidence.write_text("corrupt")
    with pytest.raises(ValueError, match="corrupt private evidence"):
        archive_enrichment_baseline(**args)
    evidence.write_bytes(original)
    with (tmp_path / "qualification.zip").open("ab") as stream:
        stream.write(b"changed")
    with pytest.raises(ValueError, match="checksum"):
        archive_enrichment_baseline(**args)
    assert not args["output"].exists()


def _resume_args(args):
    return {
        key: value
        for key, value in {
            **args,
            "receipt": args["output"],
        }.items()
        if key not in {"phase", "reports_root", "output"}
    }


def test_resume_validates_partial_context_without_changing_any_bytes(tmp_path):
    from standards_atlas.adapters.workflow.baseline_resume import verify_context_baseline

    args = setup_project(tmp_path)
    original = archive_enrichment_baseline(**args)
    before = {str(p): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    verified = verify_context_baseline(**_resume_args(args))
    assert verified == original
    assert verified["summary"]["failed"] == 1
    assert before == {str(p): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}


@pytest.mark.parametrize(
    "path",
    [
        ".atlas/data/documents/EXAMPLE.json",
        ".atlas/data/evaluation/context-routing/EXAMPLE-run.json",
        ".atlas/data/evaluation/context-routing/EXAMPLE-failures.json",
        ".atlas/data/evaluation/context-routing/EXAMPLE-unresolved-targets.json",
        "manifests/standards.yaml",
        "data/EXAMPLE",
        "cfg/context-enrichment.yaml",
    ],
)
def test_resume_rejects_drift_instead_of_recomputing_context(tmp_path, path):
    from standards_atlas.adapters.workflow.baseline_resume import verify_context_baseline

    args = setup_project(tmp_path)
    archive_enrichment_baseline(**args)
    target = tmp_path / path
    target.write_bytes(target.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="input changed or missing"):
        verify_context_baseline(**_resume_args(args))


def test_resume_allows_downstream_code_fix_but_keeps_original_code_archive(tmp_path):
    from standards_atlas.adapters.workflow.baseline_resume import verify_context_baseline

    args = setup_project(tmp_path)
    baseline = archive_enrichment_baseline(**args)
    (tmp_path / "src/standards_atlas/dummy.py").write_text("# corrected shutdown\n")
    verify_context_baseline(**_resume_args(args))
    with ZipFile(baseline["archive"]) as archive:
        assert archive.read("code/src/standards_atlas/dummy.py") == b"# frozen code\n"


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"strict_context": True}, "strict context policy"),
        ({"selection": "other"}, "another phase or selection"),
        ({"document_keys": ("OTHER",)}, "document selection"),
        ({"corpus_count": 50}, "sampling settings"),
        ({"limit": 50}, "sampling settings"),
    ],
)
def test_resume_rejects_different_selection_or_strict_failure_policy(tmp_path, changes, message):
    from standards_atlas.adapters.workflow.baseline_resume import verify_context_baseline

    args = setup_project(tmp_path)
    archive_enrichment_baseline(**args)
    with pytest.raises(ValueError, match=message):
        verify_context_baseline(**{**_resume_args(args), **changes})


def test_resume_detects_corrupt_archive_and_forged_summary(tmp_path):
    from standards_atlas.adapters.workflow.baseline_resume import verify_context_baseline

    args = setup_project(tmp_path)
    baseline = archive_enrichment_baseline(**args)
    target = Path(baseline["archive"])
    original = target.read_bytes()
    target.write_bytes(original + b"changed")
    with pytest.raises(ValueError, match="archive checksum"):
        verify_context_baseline(**_resume_args(args))
    target.write_bytes(original)
    baseline["summary"]["failed"] = 0
    (tmp_path / args["output"]).write_text(json.dumps(baseline))
    with pytest.raises(ValueError, match="receipt does not match"):
        verify_context_baseline(**_resume_args(args))


def test_resume_detects_modified_member_even_with_updated_archive_receipt(tmp_path):
    from standards_atlas.adapters.workflow.baseline_resume import verify_context_baseline

    args = setup_project(tmp_path)
    baseline = archive_enrichment_baseline(**args)
    target = Path(baseline["archive"])
    with ZipFile(target) as archive:
        contents = {name: archive.read(name) for name in archive.namelist()}
    contents["documents/EXAMPLE.json"] = b"changed"
    with ZipFile(target, "w") as archive:
        for name, data in contents.items():
            archive.writestr(name, data)
    baseline["archive_sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
    (tmp_path / args["output"]).write_text(json.dumps(baseline))
    with pytest.raises(ValueError, match="corrupt context baseline member"):
        verify_context_baseline(**_resume_args(args))
