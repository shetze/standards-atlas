"""Versioned golden-corpus qualification for extraction and normalization."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from standards_atlas.adapters.docling import DoclingJsonReader
from standards_atlas.application.normalization.document_normalizer import DocumentNormalizer


class GoldenInvariant(BaseModel):
    model_config = ConfigDict(frozen=True)
    kind: Literal["equals", "contains", "count", "nonzero", "zero"]
    path: str
    expected: Any = None


class GoldenCaseManifest(BaseModel):
    model_config = ConfigDict(frozen=True)
    schema_version: int = 1
    id: str
    description: str
    source_kind: Literal["synthetic", "real_excerpt", "malformed"]
    features: tuple[str, ...]
    input: str = "input.docling.json"
    expected_artifact: str | None = None
    invariants: tuple[GoldenInvariant, ...] = ()


class GoldenCaseResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    case_id: str
    passed: bool
    input_sha256: str
    normalized_sha256: str | None = None
    failures: tuple[str, ...] = ()


class GoldenCorpusReport(BaseModel):
    model_config = ConfigDict(frozen=True)
    schema_version: int = 1
    corpus_version: str
    passed: bool
    cases: tuple[GoldenCaseResult, ...]


class GoldenCorpusQualifier:
    """Execute a checked-in corpus without updating its expectations."""

    def run(self, root: Path) -> GoldenCorpusReport:
        index = json.loads((root / "corpus.json").read_text(encoding="utf-8"))
        results = tuple(self._run_case(root / "cases" / case_id) for case_id in index["cases"])
        return GoldenCorpusReport(
            corpus_version=index["version"],
            passed=all(result.passed for result in results),
            cases=results,
        )

    def _run_case(self, case_dir: Path) -> GoldenCaseResult:
        manifest = GoldenCaseManifest.model_validate_json(
            (case_dir / "manifest.json").read_text(encoding="utf-8")
        )
        input_path = case_dir / manifest.input
        input_hash = _sha256(input_path.read_bytes())
        failures: list[str] = []
        try:
            extracted = DoclingJsonReader().read(input_path)
            normalized = DocumentNormalizer().normalize(extracted)
            payload = normalized.model_dump(mode="json", exclude_none=True)
            normalized_bytes = _canonical_json(payload)
            normalized_hash = _sha256(normalized_bytes)
            context = {"extracted": extracted.model_dump(mode="json"), "normalized": payload}
            for invariant in manifest.invariants:
                actual = _resolve(context, invariant.path)
                if not _matches(invariant, actual):
                    failures.append(
                        f"{invariant.kind} {invariant.path}: expected "
                        f"{invariant.expected!r}, got {actual!r}"
                    )
            if manifest.expected_artifact:
                expected = (case_dir / manifest.expected_artifact).read_bytes()
                if normalized_bytes != expected:
                    failures.append("normalized artifact differs from checked-in golden file")
        except Exception as exc:  # qualification reports failures instead of aborting corpus
            normalized_hash = None
            failures.append(f"{type(exc).__name__}: {exc}")
        return GoldenCaseResult(
            case_id=manifest.id,
            passed=not failures,
            input_sha256=input_hash,
            normalized_sha256=normalized_hash,
            failures=tuple(failures),
        )


def _resolve(value: Any, path: str) -> Any:
    current = value
    for part in path.split("."):
        if part == "":
            continue
        if isinstance(current, list) and part == "count":
            current = len(current)
        elif isinstance(current, dict):
            current = current[part]
        elif isinstance(current, list) and part.isdigit():
            current = current[int(part)]
        else:
            current = getattr(current, part)
    return current


def _matches(invariant: GoldenInvariant, actual: Any) -> bool:
    if invariant.kind == "equals":
        return actual == invariant.expected
    if invariant.kind == "contains":
        return invariant.expected in actual
    if invariant.kind == "count":
        return len(actual) == invariant.expected
    if invariant.kind == "nonzero":
        return bool(actual)
    return not bool(actual)


def _canonical_json(payload: Any) -> bytes:
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()
