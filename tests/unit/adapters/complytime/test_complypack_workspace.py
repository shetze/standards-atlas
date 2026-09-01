from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from standards_atlas.adapters.complytime import (
    ComplyPackCli,
    ComplyPackConfig,
    ComplyPackWorkspaceExporter,
)
from standards_atlas.application.model import PublicationDocument
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    DocumentKey,
    DocumentType,
    EngineeringDocument,
    SemanticClassification,
    StandardReference,
    StatementFunction,
    TextBlock,
)


def _document() -> PublicationDocument:
    objective = Clause(
        id=ClauseId(value="obj-1"),
        reference=StandardReference(standard="SAMPLE", year=2026, clause="4.1"),
        clause_type=ClauseType.OBJECTIVE,
        heading="Objective",
        content=(TextBlock(id="obj-text", text="The system shall be controlled."),),
    ).with_semantic_classification(
        SemanticClassification(statement_functions=(StatementFunction.OBJECTIVE,))
    )
    requirement = Clause(
        id=ClauseId(value="req-1"),
        reference=StandardReference(standard="SAMPLE", year=2026, clause="4.1.1"),
        clause_type=ClauseType.CLAUSE,
        heading="Requirement",
        parent_id=objective.id,
        content=(TextBlock(id="req-text", text="The system shall record evidence."),),
    ).with_semantic_classification(
        SemanticClassification(statement_functions=(StatementFunction.REQUIREMENT,))
    )
    engineering = EngineeringDocument(
        key=DocumentKey(value="SAMPLE-1"),
        title="Sample Standard",
        document_type=DocumentType.STANDARD,
        year=2026,
        version="1.0.0",
        clauses=(objective, requirement),
    )
    return PublicationDocument.from_engineering_document(engineering)


def _policy_content(tmp_path: Path) -> Path:
    content = tmp_path / "input-policy"
    content.mkdir()
    (content / "policy.rego").write_text("package sample\nallow := true\n", encoding="utf-8")
    return content


def test_complypack_workspace_contains_explicit_policy_and_governance_sources(
    tmp_path: Path,
) -> None:
    target = tmp_path / "workspace"
    result = ComplyPackWorkspaceExporter().export(
        _document(),
        target,
        policy_content=_policy_content(tmp_path),
        pack_id="org.example.sample",
        evaluator_id="opa",
        pack_version="0.1.0",
        gemara_source="oci://ghcr.io/example/sample-policy:v1",
        schemas=("kubernetes-deployment",),
    )

    assert result == target
    assert (target / "governance" / "guidance.yaml").is_file()
    assert (target / "governance" / "controls.yaml").is_file()
    assert (target / "policy" / "policy.rego").read_text(encoding="utf-8") == (
        "package sample\nallow := true\n"
    )

    config = yaml.safe_load((target / "complypack.yaml").read_text(encoding="utf-8"))
    assert config == {
        "id": "org.example.sample",
        "evaluator-id": "opa",
        "version": "0.1.0",
        "gemara": {
            "sources": [{"source": "oci://ghcr.io/example/sample-policy:v1"}],
        },
        "schemas": [{"platform": "kubernetes-deployment"}],
    }
    assert (target / "workspace-manifest.yaml").is_file()
    assert (target / "lineage.json").is_file()


def test_complypack_workspace_manifest_binds_config_policy_and_governance(
    tmp_path: Path,
) -> None:
    target = tmp_path / "workspace"
    ComplyPackWorkspaceExporter().export(
        _document(),
        target,
        policy_content=_policy_content(tmp_path),
        pack_id="org.example.sample",
        evaluator_id="opa",
        pack_version="0.1.0",
        gemara_source="file:///tmp/sample-policy.yaml",
    )

    manifest = yaml.safe_load((target / "workspace-manifest.yaml").read_text(encoding="utf-8"))
    governance_manifest = target / "governance" / "manifest.yaml"
    config = target / "complypack.yaml"
    assert (
        manifest["governance-manifest-sha256"]
        == hashlib.sha256(governance_manifest.read_bytes()).hexdigest()
    )
    assert manifest["complypack-config-sha256"] == hashlib.sha256(config.read_bytes()).hexdigest()
    assert len(manifest["policy-content-sha256"]) == 64


def test_complypack_workspace_rejects_empty_or_symlinked_policy_content(
    tmp_path: Path,
) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(ValueError, match="empty"):
        ComplyPackWorkspaceExporter().export(
            _document(),
            tmp_path / "empty-output",
            policy_content=empty,
            pack_id="org.example.sample",
            evaluator_id="opa",
            pack_version="0.1.0",
            gemara_source="oci://ghcr.io/example/sample-policy:v1",
        )

    source = _policy_content(tmp_path)
    (source / "linked.rego").symlink_to(source / "policy.rego")
    with pytest.raises(ValueError, match="symbolic links"):
        ComplyPackWorkspaceExporter().export(
            _document(),
            tmp_path / "link-output",
            policy_content=source,
            pack_id="org.example.sample",
            evaluator_id="opa",
            pack_version="0.1.0",
            gemara_source="oci://ghcr.io/example/sample-policy:v1",
        )


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"id": "sample"}, "reverse-domain"),
        ({"version": "v1"}, "semantic versioning"),
        ({"source": "relative/policy.yaml"}, "URI scheme"),
    ],
)
def test_complypack_configuration_rejects_ambiguous_identity(
    kwargs: dict[str, str],
    message: str,
) -> None:
    values = {
        "id": "org.example.sample",
        "evaluator_id": "opa",
        "version": "0.1.0",
        "gemara": {"sources": [{"source": "file:///tmp/policy.yaml"}]},
    }
    if "source" in kwargs:
        values["gemara"] = {"sources": [{"source": kwargs["source"]}]}
    else:
        values.update(kwargs)
    with pytest.raises(ValueError, match=message):
        ComplyPackConfig.model_validate(values)


def test_complypack_cli_invokes_validate_and_pack_without_shell(tmp_path: Path) -> None:
    cli = ComplyPackCli(executable="complypack")
    completed = type(
        "Completed",
        (),
        {"returncode": 0, "stdout": "ok\n", "stderr": ""},
    )()
    with (
        patch(
            "standards_atlas.adapters.complytime.complypack.shutil.which",
            return_value="/bin/complypack",
        ),
        patch(
            "standards_atlas.adapters.complytime.complypack.subprocess.run",
            return_value=completed,
        ) as run,
    ):
        cli.validate(tmp_path)
        cli.pack(tmp_path, "localhost:5001/sample:v1", plain_http=True)

    validate_call = run.call_args_list[0]
    assert validate_call.args[0] == (
        "complypack",
        "config",
        "validate",
        "complypack.yaml",
        "--unknown-fields=error",
        "--scope",
        "pack",
    )
    assert validate_call.kwargs["cwd"] == tmp_path
    assert "shell" not in validate_call.kwargs

    pack_call = run.call_args_list[1]
    assert pack_call.args[0] == (
        "complypack",
        "pack",
        "policy/",
        "localhost:5001/sample:v1",
        "--plain-http",
    )


def test_complypack_cli_fails_cleanly_without_external_binary(tmp_path: Path) -> None:
    with patch(
        "standards_atlas.adapters.complytime.complypack.shutil.which",
        return_value=None,
    ):
        with pytest.raises(FileNotFoundError, match="not available"):
            ComplyPackCli().validate(tmp_path)
