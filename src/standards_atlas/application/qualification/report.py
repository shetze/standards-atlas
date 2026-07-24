"""Auditable reports for qualification executions."""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from standards_atlas import __version__
from standards_atlas.application.qualification.golden_corpus import GoldenCorpusReport


class QualificationRunReporter:
    """Persist machine-readable and human-readable golden-corpus evidence."""

    schema_version = 1

    def write(
        self,
        report: GoldenCorpusReport,
        *,
        corpus_root: Path,
        project_root: Path,
        output_root: Path | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> tuple[Path, Path]:
        root = project_root.resolve()
        corpus = corpus_root.resolve()
        timestamp = (now or (lambda: datetime.now(UTC)))().astimezone(UTC)
        corpus_hash = self._directory_hash(corpus)
        run_id = f"{timestamp:%Y%m%dT%H%M%SZ}-{corpus_hash[:8]}"
        base = (output_root or root / ".atlas" / "qualification" / "runs").resolve()
        run_dir = base / run_id
        suffix = 2
        while run_dir.exists():
            run_dir = base / f"{run_id}-{suffix}"
            suffix += 1
        run_dir.mkdir(parents=True)

        payload = {
            "schema_version": self.schema_version,
            "run_id": run_dir.name,
            "status": "passed" if report.passed else "failed",
            "completed_at": timestamp.isoformat().replace("+00:00", "Z"),
            "standards_atlas_version": __version__,
            "python_version": platform.python_version(),
            "git": self._git_identity(root),
            "corpus": self._relative(corpus, root),
            "corpus_version": report.corpus_version,
            "corpus_sha256": corpus_hash,
            "summary": {
                "total": len(report.cases),
                "passed": sum(case.passed for case in report.cases),
                "failed": sum(not case.passed for case in report.cases),
            },
            "cases": [case.model_dump(mode="json") for case in report.cases],
        }
        json_path = run_dir / "report.json"
        json_path.write_text(self._canonical_json(payload) + "\n", encoding="utf-8")
        markdown_path = run_dir / "report.md"
        markdown_path.write_text(self._markdown(payload), encoding="utf-8")
        return json_path, markdown_path

    @staticmethod
    def _directory_hash(root: Path) -> str:
        digest = hashlib.sha256()
        for path in sorted(candidate for candidate in root.rglob("*") if candidate.is_file()):
            relative = path.relative_to(root).as_posix().encode()
            data = path.read_bytes()
            digest.update(len(relative).to_bytes(8, "big"))
            digest.update(relative)
            digest.update(len(data).to_bytes(8, "big"))
            digest.update(data)
        return digest.hexdigest()

    @staticmethod
    def _canonical_json(payload: object) -> str:
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _relative(path: Path, root: Path) -> str:
        try:
            return path.relative_to(root).as_posix()
        except ValueError:
            return path.as_posix()

    @staticmethod
    def _git_identity(root: Path) -> dict[str, object]:
        def command(*args: str) -> str | None:
            try:
                return subprocess.run(
                    ("git", *args), cwd=root, check=True, capture_output=True, text=True
                ).stdout.strip()
            except (OSError, subprocess.CalledProcessError):
                return None

        revision = command("rev-parse", "HEAD")
        status = command("status", "--porcelain")
        return {"revision": revision, "dirty": bool(status) if status is not None else None}

    @staticmethod
    def _markdown(payload: dict[str, object]) -> str:
        summary = payload["summary"]
        lines = [
            "# Standards Atlas qualification report",
            "",
            f"- **Run ID:** `{payload['run_id']}`",
            f"- **Status:** {payload['status']}",
            f"- **Completed:** {payload['completed_at']}",
            f"- **Standards Atlas:** {payload['standards_atlas_version']}",
            f"- **Corpus:** `{payload['corpus']}`",
            f"- **Corpus version:** `{payload['corpus_version']}`",
            f"- **Corpus SHA-256:** `{payload['corpus_sha256']}`",
            "- **Cases:** "
            f"{summary['total']} total, {summary['passed']} passed, {summary['failed']} failed",
            "",
            "## Results",
            "",
            "| Case | Result | Input SHA-256 | Normalized SHA-256 |",
            "|---|---|---|---|",
        ]
        for case in payload["cases"]:
            normalized = case["normalized_sha256"] or "-"
            result = "passed" if case["passed"] else "failed"
            lines.append(
                f"| `{case['case_id']}` | {result} | `{case['input_sha256']}` | `{normalized}` |"
            )
        failures = [case for case in payload["cases"] if case["failures"]]
        if failures:
            lines.extend(["", "## Failures", ""])
            for case in failures:
                lines.append(f"### {case['case_id']}")
                lines.append("")
                lines.extend(f"- {failure}" for failure in case["failures"])
                lines.append("")
        return "\n".join(lines).rstrip() + "\n"
