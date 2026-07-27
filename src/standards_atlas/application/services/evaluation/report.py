"""Persistent reports for evaluations and model comparisons."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from standards_atlas.application.services.evaluation.models import EvaluationRun


class EvaluationReporter:
    def write(self, run: EvaluationRun, output_root: Path) -> Path:
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        safe_model = run.model.replace("/", "_")
        path = output_root / f"{timestamp}-{run.task}-{safe_model}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(asdict(run), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return path

    def write_comparison(self, runs: tuple[EvaluationRun, ...], output: Path) -> Path:
        payload = {
            "task": runs[0].task if runs else None,
            "models": [asdict(run) for run in runs],
            "ranking": [
                run.model
                for run in sorted(
                    runs,
                    key=lambda item: (item.metrics.f1, item.metrics.schema_valid_rate),
                    reverse=True,
                )
            ],
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return output

    def write_matrix_summary(
        self,
        runs: tuple[EvaluationRun, ...],
        output: Path,
        *,
        manifest_hash: str,
        include_case_details: bool = False,
    ) -> Path:
        """Write a portable report that omits protected clause-derived content by default."""
        matrix = []
        for run in runs:
            item = {
                "task": run.task,
                "prompt_version": run.prompt_version,
                "dataset_version": run.dataset_version,
                "model": run.model,
                "provider": run.provider,
                "metrics": asdict(run.metrics),
                "metadata": dict(run.metadata),
            }
            if include_case_details:
                item["cases"] = [asdict(case) for case in run.cases]
            else:
                item["cases"] = [
                    {
                        "example_id": case.example_id,
                        "valid_json": case.valid_json,
                        "schema_valid": case.schema_valid,
                        "metrics": asdict(case.metrics),
                        "duration_ms": case.duration_ms,
                        "input_hash": case.input_hash,
                        "raw_response_hash": case.raw_response_hash,
                        "error": case.error,
                    }
                    for case in run.cases
                ]
            matrix.append(item)
        payload = {
            "schema_version": 1,
            "benchmark_manifest_hash": manifest_hash,
            "contains_case_content": include_case_details,
            "runs": matrix,
            "ranking": [
                {"prompt_version": run.prompt_version, "model": run.model}
                for run in sorted(
                    runs,
                    key=lambda item: (item.metrics.f1, item.metrics.schema_valid_rate),
                    reverse=True,
                )
            ],
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return output


SemanticEvaluationReporter = EvaluationReporter
