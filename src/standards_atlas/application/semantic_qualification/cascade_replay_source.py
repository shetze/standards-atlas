"""Read-only, checksum-verified input access for cascade replay."""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

from standards_atlas.application.semantic_qualification.consensus import ConsensusReport
from standards_atlas.application.semantic_qualification.run_selection import (
    QualificationRunSelection,
    examples_for_persisted_selection,
)


class CascadeReplaySource:
    """Read selected artifacts without extracting or modifying the source run."""

    def __init__(self, path: Path) -> None:
        self.path = path.resolve()
        self.archive = zipfile.ZipFile(path) if path.is_file() else None
        if self.archive is None and not path.is_dir():
            raise ValueError(f"qualification run does not exist: {path}")
        names = (
            self.archive.namelist()
            if self.archive is not None
            else [item.relative_to(path).as_posix() for item in path.rglob("*") if item.is_file()]
        )
        if len(names) != len(set(names)):
            self.close()
            raise ValueError("duplicate archive member names are not supported")
        self.names = set(names)
        self.fingerprints: dict[str, str] = {}
        self.expected: dict[str, str] = {}
        if "archive-manifest.json" in self.names:
            payload = json.loads(self.read("archive-manifest.json"))
            self.expected = {item["path"]: item["sha256"] for item in payload["files"]}

    def close(self) -> None:
        if self.archive is not None:
            self.archive.close()

    def read(self, name: str) -> bytes:
        relative = PurePosixPath(name)
        if relative.is_absolute() or ".." in relative.parts or "\\" in name:
            raise ValueError(f"unsafe qualification artifact path: {name}")
        if self.archive is not None:
            data = self.archive.read(name)
        else:
            candidate = (self.path / name).resolve()
            if not candidate.is_relative_to(self.path):
                raise ValueError(f"qualification artifact escapes source: {name}")
            data = candidate.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if name in self.expected and digest != self.expected[name]:
            raise ValueError(f"qualification artifact checksum mismatch: {name}")
        self.fingerprints[name] = digest
        return data

    def locate(self, *preferred: str, suffix: str | None = None) -> str | None:
        for name in preferred:
            if name in self.names:
                return name
        matches = sorted(name for name in self.names if suffix and name.endswith(suffix))
        if len(matches) > 1:
            raise ValueError(f"ambiguous qualification artifact {suffix}: {matches}")
        return matches[0] if matches else None

    def required(self, *preferred: str, suffix: str | None = None) -> bytes:
        name = self.locate(*preferred, suffix=suffix)
        if name is None:
            raise ValueError(f"required qualification artifact missing: {suffix or preferred}")
        return self.read(name)

    def manifest(self, path: Path | None) -> dict[str, Any]:
        name = self.locate("configuration/qualification-manifest.yaml")
        if name is not None:
            data = self.read(name)
            if path is not None:
                alternative = yaml.safe_load(path.read_bytes())
                if alternative != yaml.safe_load(data):
                    raise ValueError("replay manifest differs from archived configuration")
        elif path is not None:
            data = path.read_bytes()
            self.fingerprints[f"external:{path.resolve()}"] = hashlib.sha256(data).hexdigest()
        else:
            raise ValueError("run directory needs --manifest or archived configuration")
        return yaml.safe_load(data)

    def selection(self) -> QualificationRunSelection:
        selection = QualificationRunSelection.model_validate_json(
            self.required(suffix="qualification-selection.json")
        )
        if selection.schema_version != "1.2":
            raise ValueError(
                f"unsupported qualification selection schema: {selection.schema_version}"
            )
        if selection.selected_clause_count != len(selection.clauses):
            raise ValueError("qualification selection count differs from its clause list")
        for field in ("clause_id", "example_id"):
            values = [getattr(item, field) for item in selection.clauses]
            if len(set(values)) != len(values):
                raise ValueError(f"qualification selection contains duplicate {field}")
        return selection

    def materialize_inputs(self, selection: QualificationRunSelection, root: Path) -> tuple:
        """Verify persisted identities and materialize only the immutable corpus."""
        for filename, archived in (
            (selection.dataset_snapshot, "inputs/corpus/dataset.json"),
            (selection.corpus_snapshot, "inputs/corpus/corpus.yaml"),
        ):
            if Path(filename).name != filename:
                raise ValueError("selection snapshot must be a local filename")
            data = self.required(archived, suffix=filename)
            (root / filename).write_bytes(data)
        examples = examples_for_persisted_selection(selection_root=root, selection=selection)
        dataset_path = root / selection.task / selection.dataset_version / "dataset.json"
        corpus_path = root / selection.corpus_id / "corpus.yaml"
        for value in (selection.task, selection.dataset_version, selection.corpus_id):
            if Path(value).name != value or value in {".", ".."}:
                raise ValueError(f"unsafe qualification corpus coordinate: {value}")
        dataset_path.parent.mkdir(parents=True, exist_ok=True)
        corpus_path.parent.mkdir(parents=True, exist_ok=True)
        dataset_path.write_bytes((root / selection.dataset_snapshot).read_bytes())
        corpus_path.write_bytes((root / selection.corpus_snapshot).read_bytes())
        return examples

    def consensus(self, matrix_id: str, stage_id: str, *, resolver: bool) -> ConsensusReport | None:
        suffix = f"cascade/{stage_id}/{'stage-resolver/' if resolver else ''}consensus-report.json"
        name = self.locate(suffix, f"{matrix_id}/{suffix}", suffix=suffix)
        if name is None:
            return None
        report = ConsensusReport.model_validate_json(self.read(name))
        if report.matrix_id != matrix_id:
            raise ValueError(f"consensus matrix mismatch in {name}")
        return report
