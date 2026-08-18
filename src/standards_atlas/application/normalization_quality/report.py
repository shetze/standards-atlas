"""Machine-readable and human-readable normalization-quality qualification reports."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from standards_atlas.application.normalization_quality.models import (
    NormalizationQualityCase,
    NormalizationQualityRun,
    QualityStatus,
)


class NormalizationQualityReporter:
    def write(
        self, runs: tuple[NormalizationQualityRun, ...], output: Path
    ) -> tuple[Path, Path, Path]:
        if not runs:
            raise ValueError("at least one normalization-quality run is required")
        output.mkdir(parents=True, exist_ok=True)
        json_path = output / "qualification.json"
        jsonl_path = output / "findings.jsonl"
        markdown_path = output / "qualification.md"
        payload = {
            "report_type": "normalization_quality_qualification",
            "schema_version": 1,
            "corpus_path": runs[0].corpus_path,
            "prompt_version": runs[0].prompt_version,
            "models": [run.to_dict() for run in runs],
            "comparison": _comparison(runs),
        }
        json_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        with jsonl_path.open("w", encoding="utf-8") as stream:
            for run in runs:
                for case in run.cases:
                    if case.status is QualityStatus.SUSPICIOUS:
                        stream.write(
                            json.dumps(
                                {
                                    "model_id": run.model_id,
                                    "example_id": case.example_id,
                                    "document_key": case.document_key,
                                    "reference": case.reference,
                                    "title": case.title,
                                    "text": case.text,
                                    "findings": [
                                        {
                                            "type": finding.type.value,
                                            "severity": finding.severity.value,
                                            "evidence": finding.evidence,
                                            "explanation": finding.explanation,
                                            "confidence": finding.confidence,
                                        }
                                        for finding in case.findings
                                    ],
                                },
                                ensure_ascii=False,
                            )
                            + "\n"
                        )
        markdown_path.write_text(_markdown(runs), encoding="utf-8")
        return json_path, jsonl_path, markdown_path


def _comparison(runs: tuple[NormalizationQualityRun, ...]) -> dict[str, object]:
    case_ids = sorted({case.example_id for run in runs for case in run.cases})
    statuses = {
        run.model_id: {case.example_id: case.status for case in run.cases if case.succeeded}
        for run in runs
    }
    unanimous_ok = []
    unanimous_suspicious = []
    disagreements = []
    for case_id in case_ids:
        values = [statuses[run.model_id].get(case_id) for run in runs]
        if None in values:
            continue
        if all(value is QualityStatus.OK for value in values):
            unanimous_ok.append(case_id)
        elif all(value is QualityStatus.SUSPICIOUS for value in values):
            unanimous_suspicious.append(case_id)
        else:
            disagreements.append(case_id)
    return {
        "unanimous_ok": len(unanimous_ok),
        "unanimous_suspicious": len(unanimous_suspicious),
        "disagreements": len(disagreements),
        "disagreement_example_ids": disagreements,
    }


def _markdown(runs: tuple[NormalizationQualityRun, ...]) -> str:
    comparison = _comparison(runs)
    lines = [
        "# Normalization Quality Qualification",
        "",
        "This report is observational. It does not modify EngineeringDocuments or "
        "normalization artifacts.",
        "",
        f"- Corpus: `{runs[0].corpus_path}`",
        f"- Prompt: `{runs[0].prompt_version}`",
        "",
        "## Model summary",
        "",
        "| Model | Cases | Reviewed | OK | Suspicious | Failed | Cached |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for run in runs:
        lines.append(
            f"| `{run.model_id}` | {len(run.cases)} | {run.reviewed} | "
            f"{run.reviewed - run.suspicious} | {run.suspicious} | {run.failed} | "
            f"{run.cached} |"
        )
    lines.extend(
        [
            "",
            "## Agreement",
            "",
            f"- Unanimous OK: {comparison['unanimous_ok']}",
            f"- Unanimous suspicious: {comparison['unanimous_suspicious']}",
            f"- Model disagreements: {comparison['disagreements']}",
            "",
            "## Finding types",
            "",
            "| Finding | " + " | ".join(run.model_id for run in runs) + " |",
            "|---|" + "---:|" * len(runs),
        ]
    )
    finding_types = sorted({name for run in runs for name in run.finding_counts()})
    for name in finding_types:
        counts = " | ".join(str(run.finding_counts().get(name, 0)) for run in runs)
        lines.append(f"| {name} | {counts} |")
    disagreements = set(comparison["disagreement_example_ids"])
    if disagreements:
        lines.extend(["", "## Model disagreements", ""])
        by_run = {run.model_id: {case.example_id: case for case in run.cases} for run in runs}
        for case_id in sorted(disagreements):
            representative = next(
                by_run[run.model_id][case_id] for run in runs if case_id in by_run[run.model_id]
            )
            lines.extend(_case_heading(representative))
            lines.extend(["", representative.text.strip(), ""])
            for run in runs:
                case = by_run[run.model_id].get(case_id)
                if case is None:
                    continue
                status = case.status.value if case.status else "failed"
                lines.append(f"**{run.model_id}:** {status}")
                lines.extend(_finding_lines(case))
                lines.append("")
    lines.extend(["", "## Suspicious clauses by finding type", ""])
    grouped: dict[str, list[tuple[str, NormalizationQualityCase]]] = {}
    for run in runs:
        for case in run.cases:
            for finding in case.findings:
                grouped.setdefault(finding.type.value, []).append((run.model_id, case))
    for finding_type in sorted(grouped):
        lines.extend([f"### {finding_type}", ""])
        seen: set[tuple[str, str]] = set()
        for model_id, case in grouped[finding_type]:
            key = (model_id, case.example_id)
            if key in seen:
                continue
            seen.add(key)
            lines.extend(_case_heading(case))
            lines.append(f"- Model: `{model_id}`")
            lines.extend(_finding_lines(case, finding_type=finding_type))
            lines.append("")
    failure_counts = Counter(case.error for run in runs for case in run.cases if case.error)
    if failure_counts:
        lines.extend(["## Failures", ""])
        for error, count in failure_counts.most_common():
            lines.append(f"- {count} × `{error}`")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _case_heading(case: NormalizationQualityCase) -> list[str]:
    label = (
        ":".join(part for part in (case.document_key, case.reference) if part) or case.example_id
    )
    suffix = f" — {case.title}" if case.title else ""
    return [f"### {label}{suffix}"]


def _finding_lines(case: NormalizationQualityCase, *, finding_type: str | None = None) -> list[str]:
    lines: list[str] = []
    for finding in case.findings:
        if finding_type is not None and finding.type.value != finding_type:
            continue
        lines.append(
            f"- `{finding.type.value}` / {finding.severity.value} / "
            f"confidence {finding.confidence:.2f}: **{finding.evidence}** — "
            f"{finding.explanation}"
        )
    return lines
