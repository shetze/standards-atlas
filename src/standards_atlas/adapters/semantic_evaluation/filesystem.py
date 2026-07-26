"""Filesystem repositories for prompts, corpora, and evaluation evidence."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import yaml

from standards_atlas.application.semantic_evaluation.models import (
    EvaluationReport,
    GoldenCorpus,
    GoldenCorpusCase,
    PromptDefinition,
)


class FileSystemPromptRepository:
    def __init__(self, root: Path) -> None:
        self._root = root

    def load(self, identifier: str, version: str) -> PromptDefinition:
        directory = self._root / identifier / version
        metadata = _load_yaml(directory / "prompt.yaml")
        schema = _load_json(directory / "schema.json")
        return PromptDefinition(
            identifier=str(metadata["identifier"]),
            version=str(metadata["version"]),
            task=str(metadata["task"]),
            description=str(metadata.get("description", "")),
            system_prompt=(directory / "system.txt").read_text(encoding="utf-8").strip(),
            user_template=(directory / "user.txt").read_text(encoding="utf-8").strip(),
            output_schema=schema,
        )


class FileSystemGoldenCorpusRepository:
    def __init__(self, root: Path) -> None:
        self._root = root

    def load(self, identifier: str, version: str) -> GoldenCorpus:
        payload = _load_json(self._root / identifier / version / "corpus.json")
        cases = tuple(
            GoldenCorpusCase(
                identifier=str(case["id"]),
                input={str(key): str(value) for key, value in case["input"].items()},
                expected=case["expected"],
                tags=tuple(str(tag) for tag in case.get("tags", ())),
            )
            for case in payload["cases"]
        )
        return GoldenCorpus(
            identifier=str(payload["identifier"]),
            version=str(payload["version"]),
            task=str(payload["task"]),
            cases=cases,
        )


class FileSystemEvaluationReportRepository:
    def __init__(self, root: Path) -> None:
        self._root = root

    def save(self, report: EvaluationReport) -> Path:
        model = _safe_name(report.requested_model)
        directory = self._root / report.task / report.prompt_version / report.corpus_version / model
        directory.mkdir(parents=True, exist_ok=True)
        timestamp = report.generated_at.replace(":", "-")
        path = directory / f"{timestamp}.json"
        _write_json(path, asdict(report))
        return path

    def load(self, path: Path) -> dict[str, Any]:
        return _load_json(path)


def _load_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected YAML mapping in {path}")
    return payload


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object in {path}")
    return payload


def _write_json(path: Path, payload: Any) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _safe_name(value: str) -> str:
    return "".join(
        character if character.isalnum() or character in "-_." else "-"
        for character in value
    )
