"""Prepare and optionally package evaluator-specific ComplyPack workspaces."""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator

from standards_atlas.adapters.artifact_lineage import write_directory_lineage_manifest
from standards_atlas.adapters.complytime.exporter import ComplyTimeGovernanceBundleExporter
from standards_atlas.application.model import PublicationDocument
from standards_atlas.shared.artifacts import write_yaml

_COMPLYPACK_FILE = "complypack.yaml"
_WORKSPACE_MANIFEST_FILE = "workspace-manifest.yaml"
_GOVERNANCE_DIRECTORY = "governance"
_POLICY_DIRECTORY = "policy"
_PACK_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:[.-][a-z0-9]+)+$")
_VERSION_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$")


class ComplyPackSource(BaseModel):
    """One Gemara policy source understood by ComplyPack."""

    model_config = ConfigDict(frozen=True)

    source: str = Field(min_length=1)

    @field_validator("source")
    @classmethod
    def validate_source_uri(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {"file", "http", "https", "oci"}:
            raise ValueError("Gemara source must use file, http, https, or oci URI scheme")
        if parsed.scheme != "file" and not parsed.netloc:
            raise ValueError("Gemara source URI must identify a host or registry")
        if parsed.scheme == "file" and not parsed.path:
            raise ValueError("file Gemara source URI must identify a path")
        return value


class ComplyPackGemaraConfig(BaseModel):
    """Gemara provenance configuration for ComplyPack."""

    model_config = ConfigDict(frozen=True)

    sources: tuple[ComplyPackSource, ...] = Field(min_length=1)


class ComplyPackSchema(BaseModel):
    """One platform schema used while authoring evaluator policy."""

    model_config = ConfigDict(frozen=True)

    platform: str = Field(min_length=1)


class ComplyPackConfig(BaseModel):
    """Strict subset of complypack.yaml emitted by Standards Atlas."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    id: str = Field(min_length=3)
    evaluator_id: str = Field(alias="evaluator-id", min_length=1)
    version: str = Field(min_length=1)
    gemara: ComplyPackGemaraConfig
    schemas: tuple[ComplyPackSchema, ...] | None = None

    @field_validator("id")
    @classmethod
    def validate_pack_id(cls, value: str) -> str:
        if not _PACK_ID_PATTERN.fullmatch(value):
            raise ValueError("ComplyPack id must use reverse-domain style segments")
        return value

    @field_validator("version")
    @classmethod
    def validate_version(cls, value: str) -> str:
        if not _VERSION_PATTERN.fullmatch(value):
            raise ValueError("ComplyPack version must be semantic versioning compatible")
        return value


class ComplyPackWorkspaceManifest(BaseModel):
    """Deterministic hand-off manifest for one ComplyPack authoring workspace."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    schema_version: str = Field(default="1.0", alias="schema-version")
    document_key: str = Field(alias="document-key", min_length=1)
    governance_manifest_sha256: str = Field(
        alias="governance-manifest-sha256", pattern=r"^[0-9a-f]{64}$"
    )
    complypack_config_sha256: str = Field(
        alias="complypack-config-sha256", pattern=r"^[0-9a-f]{64}$"
    )
    policy_content_sha256: str = Field(alias="policy-content-sha256", pattern=r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class ComplyPackExecutionResult:
    """Result returned from an external ComplyPack CLI invocation."""

    command: tuple[str, ...]
    stdout: str
    stderr: str


class ComplyPackCli:
    """Narrow adapter around the external complypack executable."""

    def __init__(self, executable: str = "complypack") -> None:
        self.executable = executable

    def validate(self, workspace: Path) -> ComplyPackExecutionResult:
        return self._run(
            (
                self.executable,
                "config",
                "validate",
                _COMPLYPACK_FILE,
                "--unknown-fields=error",
                "--scope",
                "pack",
            ),
            workspace,
        )

    def pack(
        self,
        workspace: Path,
        target: str,
        *,
        plain_http: bool = False,
    ) -> ComplyPackExecutionResult:
        command = [self.executable, "pack", f"{_POLICY_DIRECTORY}/", target]
        if plain_http:
            command.append("--plain-http")
        return self._run(tuple(command), workspace)

    def _run(self, command: tuple[str, ...], workspace: Path) -> ComplyPackExecutionResult:
        if shutil.which(self.executable) is None:
            raise FileNotFoundError(
                f"ComplyPack executable is not available on PATH: {self.executable}"
            )
        completed = subprocess.run(  # noqa: S603
            command,
            cwd=workspace,
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise RuntimeError(
                f"ComplyPack command failed with exit code {completed.returncode}: {detail}"
            )
        return ComplyPackExecutionResult(
            command=command,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )


class ComplyPackWorkspaceExporter:
    """Prepare a deterministic workspace around explicit evaluator policy content."""

    def __init__(
        self,
        *,
        governance_exporter: ComplyTimeGovernanceBundleExporter | None = None,
    ) -> None:
        self._governance_exporter = governance_exporter or ComplyTimeGovernanceBundleExporter()

    def export(
        self,
        document: PublicationDocument,
        target: Path,
        *,
        policy_content: Path,
        pack_id: str,
        evaluator_id: str,
        pack_version: str,
        gemara_source: str,
        schemas: tuple[str, ...] = (),
        replace_existing: bool = True,
    ) -> Path:
        """Create governance, policy content, and strict ComplyPack configuration."""
        _validate_policy_content(policy_content)
        config = ComplyPackConfig(
            id=pack_id,
            evaluator_id=evaluator_id,
            version=pack_version,
            gemara=ComplyPackGemaraConfig(sources=(ComplyPackSource(source=gemara_source),)),
            schemas=(tuple(ComplyPackSchema(platform=platform) for platform in schemas) or None),
        )

        if target.exists():
            if not replace_existing:
                raise FileExistsError(f"ComplyPack workspace already exists: {target}")
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
        target.mkdir(parents=True, exist_ok=False)

        governance = target / _GOVERNANCE_DIRECTORY
        self._governance_exporter.export(document, governance, replace_existing=False)
        _copy_policy_content(policy_content, target / _POLICY_DIRECTORY)

        config_path = target / _COMPLYPACK_FILE
        write_yaml(
            config_path,
            config.model_dump(mode="json", by_alias=True, exclude_none=True),
        )
        manifest = ComplyPackWorkspaceManifest(
            document_key=document.key.value,
            governance_manifest_sha256=_sha256_file(governance / "manifest.yaml"),
            complypack_config_sha256=_sha256_file(config_path),
            policy_content_sha256=_directory_hash(target / _POLICY_DIRECTORY),
        )
        write_yaml(
            target / _WORKSPACE_MANIFEST_FILE,
            manifest.model_dump(mode="json", by_alias=True),
        )
        write_directory_lineage_manifest(
            target,
            document,
            kind="complypack_authoring_workspace",
        )
        return target


def _validate_policy_content(path: Path) -> None:
    if not path.is_dir():
        raise ValueError(f"Policy content directory does not exist: {path}")
    files = [candidate for candidate in path.rglob("*") if candidate.is_file()]
    if not files:
        raise ValueError(f"Policy content directory is empty: {path}")
    symlinks = [candidate for candidate in path.rglob("*") if candidate.is_symlink()]
    if symlinks:
        raise ValueError("Policy content must not contain symbolic links")


def _copy_policy_content(source: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=False)
    for source_path in sorted(source.rglob("*")):
        relative = source_path.relative_to(source)
        target_path = target / relative
        if source_path.is_dir():
            target_path.mkdir(parents=True, exist_ok=True)
        elif source_path.is_file():
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source_path, target_path)


def _sha256_file(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _directory_hash(path: Path) -> str:
    digest = sha256()
    for candidate in sorted(item for item in path.rglob("*") if item.is_file()):
        relative = candidate.relative_to(path).as_posix().encode("utf-8")
        content = candidate.read_bytes()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()
