from __future__ import annotations

import hashlib
import json
import platform
import subprocess
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from standards_atlas import __version__
from standards_atlas.application.workflow.models import (
    WorkflowExecutionResult,
    WorkflowPlan,
    WorkflowStep,
    WorkflowTask,
)


@dataclass(frozen=True)
class ArtifactDigest:
    path: str
    kind: str
    size: int
    sha256: str


class WorkflowRunReporter:
    """Persist an auditable derivation record for a completed workflow run."""

    schema_version = 2

    def write(
        self,
        plan: WorkflowPlan,
        result: WorkflowExecutionResult,
        *,
        project_root: Path,
        manifest_path: Path,
        hierarchy_key: str | None = None,
        task: WorkflowTask = WorkflowTask.DOCUMENTS,
        qualification_manifest_path: Path | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> tuple[Path, Path]:
        if not result.completed:
            raise ValueError("workflow run reports may only be written for completed runs")

        root = project_root.resolve()
        manifest = manifest_path.resolve()
        qualification_manifest = (
            qualification_manifest_path.resolve()
            if qualification_manifest_path is not None
            else None
        )
        executed = set(result.executed_steps)
        plan_payload = [self._step_payload(step) for step in plan.steps]
        plan_hash = self._json_hash(plan_payload)
        timestamp = (now or (lambda: datetime.now(UTC)))().astimezone(UTC)
        run_id = f"{timestamp:%Y%m%dT%H%M%SZ}-{plan_hash[:8]}"
        run_dir = root / ".atlas" / "workflow" / "runs" / run_id
        suffix = 2
        while run_dir.exists():
            run_dir = root / ".atlas" / "workflow" / "runs" / f"{run_id}-{suffix}"
            suffix += 1
        run_dir.mkdir(parents=True)
        run_id = run_dir.name

        steps = []
        for index, step in enumerate(plan.steps, start=1):
            artifacts = self._collect_step_artifacts(step, root)
            steps.append(
                {
                    "index": index,
                    **self._step_payload(step),
                    "disposition": "executed" if step in executed else "reused",
                    "artifacts": [asdict(item) for item in artifacts],
                }
            )

        inputs = [self._digest(manifest, root)]
        if qualification_manifest is not None:
            inputs.append(self._digest(qualification_manifest, root))
        payload = {
            "schema_version": self.schema_version,
            "run_id": run_id,
            "status": "completed",
            "completed_at": timestamp.isoformat().replace("+00:00", "Z"),
            "standards_atlas_version": __version__,
            "python_version": platform.python_version(),
            "git": self._git_identity(root),
            "manifest": self._relative(manifest, root),
            "task": task.value,
            "qualification_manifest": (
                self._relative(qualification_manifest, root)
                if qualification_manifest is not None
                else None
            ),
            "hierarchy": hierarchy_key,
            "families": list(plan.families),
            "force": plan.force,
            "kept_stages": [stage.value for stage in plan.kept_stages],
            "plan_sha256": plan_hash,
            "inputs": [asdict(item) for item in inputs],
            "summary": {
                "planned_steps": len(plan.steps),
                "executed_steps": len(result.executed_steps),
                "reused_steps": len(plan.steps) - len(result.executed_steps),
            },
            "steps": steps,
        }
        report_json = run_dir / "report.json"
        report_json.write_text(self._canonical_json(payload) + "\n", encoding="utf-8")
        report_md = run_dir / "report.md"
        report_md.write_text(self._markdown(payload), encoding="utf-8")
        return report_json, report_md

    @staticmethod
    def _step_payload(step: WorkflowStep) -> dict[str, object]:
        return {
            "family": step.family,
            "document": step.document,
            "stage": step.stage.value,
            "artifact_policy": step.artifact_policy.value,
            "manual_gate": step.manual_gate,
            "command": list(step.command),
            "declared_output_paths": list(step.output_paths),
            "declared_output_globs": list(step.output_globs),
        }

    def _collect_step_artifacts(self, step: WorkflowStep, root: Path) -> tuple[ArtifactDigest, ...]:
        paths: set[Path] = {root / item for item in step.output_paths}
        for pattern in step.output_globs:
            paths.update(root.glob(pattern))
        files: list[Path] = []
        for path in sorted(paths):
            if path.is_dir():
                files.extend(
                    candidate for candidate in sorted(path.rglob("*")) if candidate.is_file()
                )
            elif path.is_file():
                files.append(path)
        return tuple(self._digest(path, root) for path in files)

    @staticmethod
    def _digest(path: Path, root: Path) -> ArtifactDigest:
        data = path.read_bytes()
        return ArtifactDigest(
            path=WorkflowRunReporter._relative(path, root),
            kind="file",
            size=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
        )

    @staticmethod
    def _relative(path: Path, root: Path) -> str:
        try:
            return path.resolve().relative_to(root).as_posix()
        except ValueError:
            return path.resolve().as_posix()

    @staticmethod
    def _canonical_json(payload: object) -> str:
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @classmethod
    def _json_hash(cls, payload: object) -> str:
        return hashlib.sha256(cls._canonical_json(payload).encode()).hexdigest()

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
            "# Standards Atlas workflow run report",
            "",
            f"- **Run ID:** `{payload['run_id']}`",
            f"- **Status:** {payload['status']}",
            f"- **Completed:** {payload['completed_at']}",
            f"- **Standards Atlas:** {payload['standards_atlas_version']}",
            f"- **Task:** `{payload['task']}`",
            f"- **Manifest:** `{payload['manifest']}`",
            f"- **Qualification manifest:** `{payload['qualification_manifest'] or '-'}`",
            f"- **Hierarchy:** `{payload['hierarchy'] or '-'}`",
            f"- **Plan SHA-256:** `{payload['plan_sha256']}`",
            "- **Steps:** "
            f"{summary['planned_steps']} planned, "
            f"{summary['executed_steps']} executed, "
            f"{summary['reused_steps']} reused",
            "",
            "## Deterministic derivation",
            "",
            "| # | Stage | Family / document | Disposition | Output files |",
            "|---:|---|---|---|---:|",
        ]
        for step in payload["steps"]:
            lines.append(
                f"| {step['index']} | `{step['stage']}` | "
                f"`{step['family']}` / `{step['document']}` | "
                f"{step['disposition']} | {len(step['artifacts'])} |"
            )
        lines.extend(["", "## Artifact hashes", ""])
        for step in payload["steps"]:
            if not step["artifacts"]:
                continue
            lines.extend([f"### {step['index']}. {step['stage']} — {step['document']}", ""])
            for artifact in step["artifacts"]:
                lines.append(
                    f"- `{artifact['path']}` — `{artifact['sha256']}` ({artifact['size']} bytes)"
                )
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"
