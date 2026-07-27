"""Persistent reports for semantic evaluations and model comparisons."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from standards_atlas.application.semantic_evaluation.models import EvaluationRun


class SemanticEvaluationReporter:
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
