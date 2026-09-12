"""Model-free historical inspection, routing replay and local-proposal replay.

No path in this module calls a generation gateway or starts a model server.
Routing replay deliberately does not pretend to rebuild consensus from votes
that are absent from a historical selection.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from enum import StrEnum
from pathlib import Path
from typing import Any

from standards_atlas import __version__
from standards_atlas.application.schema import require_supported_schema
from standards_atlas.application.semantic_qualification.cascade_metrics import (
    reason_counts,
    resolution_counts,
    stage_accounting,
)
from standards_atlas.application.semantic_qualification.cascade_replay_proposals import (
    ProposalReplay,
)
from standards_atlas.application.semantic_qualification.cascade_replay_source import (
    CascadeReplaySource,
)
from standards_atlas.application.semantic_qualification.qualification_matrix import (
    CascadeResolutionConfig,
    QualificationMatrixManifest,
    capture_resolved_dimensions,
    cascade_stage_unresolved_clause_ids,
    cascade_unresolved_clause_ids,
    effective_cascade_resolution,
)


class CascadeReplayMode(StrEnum):
    HISTORICAL = "historical"
    ROUTING = "routing"
    PROPOSALS = "proposals"


def replay_cascade(
    *,
    run: Path,
    output_directory: Path,
    mode: CascadeReplayMode = CascadeReplayMode.ROUTING,
    manifest_path: Path | None = None,
    runs_output: Path | None = None,
    resources: Path | None = None,
) -> tuple[Path, Path]:
    """Write a separate audit report; never overwrite qualification artifacts."""
    mode = CascadeReplayMode(mode)
    source = CascadeReplaySource(run)
    try:
        destination = output_directory.resolve()
        if source.path.is_dir() and destination.is_relative_to(source.path):
            raise ValueError("replay output must be outside the source run directory")
        if destination == source.path or destination.exists():
            raise ValueError("replay output must be a new, separate directory")
        manifest = QualificationMatrixManifest.model_validate(source.manifest(manifest_path))
        if manifest.execution.mode != "cascade":
            raise ValueError("cascade-replay requires a cascade qualification manifest")
        selection = source.selection()
        if (selection.corpus_id, selection.task, selection.dataset_version) != (
            manifest.corpus_id,
            manifest.task,
            manifest.dataset_version,
        ):
            raise ValueError("qualification selection does not match the manifest")
        provenance = json.loads(source.required(suffix="cascade-provenance.json"))
        require_supported_schema("cascade-provenance", provenance.get("schema_version"))
        if provenance["matrix_id"] != manifest.matrix_id:
            raise ValueError("cascade provenance matrix does not match manifest")
        ids = tuple(item.clause_id for item in selection.clauses)
        coordinates = {item.clause_id: item.document_key for item in selection.clauses}
        aliases = {item.example_id: item.clause_id for item in selection.clauses}
        for clause_id in ids:
            if clause_id in aliases and aliases[clause_id] != clause_id:
                raise ValueError("ambiguous clause/example identity in qualification selection")
            aliases[clause_id] = clause_id
        recorded = {item["stage_id"]: item for item in provenance["stages"]}
        if len(recorded) != len(provenance["stages"]):
            raise ValueError("duplicate cascade stage in provenance")
        configured = {item.id for item in manifest.execution.stages}
        if set(recorded) - configured:
            raise ValueError("cascade provenance contains an unconfigured stage")
        for stage in manifest.execution.stages:
            if Path(stage.id).name != stage.id or stage.id in {".", ".."}:
                raise ValueError("unsafe cascade stage id")
        with tempfile.TemporaryDirectory(prefix="atlas-cascade-replay-") as temporary:
            workspace = Path(temporary)
            examples = source.materialize_inputs(selection, workspace)
            proposals = None
            if mode == CascadeReplayMode.PROPOSALS:
                if runs_output is None or resources is None:
                    raise ValueError("proposals mode requires --runs-output and --resources")
                proposals = ProposalReplay(
                    manifest=manifest,
                    runs_output=runs_output,
                    resources=resources,
                    corpus_root=workspace,
                    workspace=workspace,
                    examples=examples,
                )
            stages, resolutions, gaps = _replay_stages(
                source=source,
                manifest=manifest,
                ids=ids,
                coordinates=coordinates,
                aliases=aliases,
                recorded=recorded,
                mode=mode,
                proposals=proposals,
            )
            if proposals is not None:
                gaps.extend(proposals.requires_inference)
                proposals.final_consensus(ids, resolutions)
            finished = {
                clause_id for stage in stages for clause_id in stage["completed_clause_ids"]
            }
            first = stages[0] if stages else {}
            remaining = [clause_id for clause_id in ids if clause_id not in finished]
            payload = {
                "schema_version": "1.0",
                "standards_atlas_version": __version__,
                "mode": mode.value,
                "source": str(source.path),
                "matrix_id": manifest.matrix_id,
                "corpus_id": manifest.corpus_id,
                "model_inference_performed": False,
                "consensus_recomputed": mode == CascadeReplayMode.PROPOSALS,
                "historical_stage_consensus_used": mode != CascadeReplayMode.PROPOSALS,
                "complete_counterfactual_run": False,
                "selected_clause_count": len(ids),
                "accounted_clause_count": len(ids),
                "completed_clause_count": len(finished),
                "unresolved_clause_count": len(remaining),
                "unresolved_clause_ids": remaining,
                "early_exit_count": first.get("completed_clause_count", 0),
                "early_exit_rate": first.get("completed_fraction_of_selection", 0.0),
                "requires_inference_clause_count": len({item["clause_id"] for item in gaps}),
                "requires_inference": gaps,
                "known_proposal_failures": proposals.known_failures if proposals else [],
                "stages": stages,
                "dimension_resolutions": resolutions,
                "input_fingerprints": {
                    **source.fingerprints,
                    **(proposals.fingerprints if proposals is not None else {}),
                },
                "limitations": [
                    "No fresh qualification or semantic accuracy claim; selection "
                    "denominator is unchanged.",
                    "Routing replay changes only routing/capture; archived consensus is "
                    "not recomputed.",
                    "Missing stage observations are not negative votes and cannot be fabricated.",
                    "Timing is historical when recorded; absent request/error/retry costs "
                    "remain unknown.",
                    "Applicability detail policy and public enrichments are not modified or rerun.",
                ],
            }
            destination.mkdir(parents=True)
            if proposals is not None:
                shutil.copytree(workspace / "consensus", destination / "consensus")
        json_path = destination / "cascade-replay.json"
        markdown_path = destination / "cascade-replay.md"
        json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        markdown_path.write_text(render_replay_markdown(payload), encoding="utf-8")
        return json_path, markdown_path
    finally:
        source.close()


def _replay_stages(
    *,
    source: CascadeReplaySource,
    manifest: QualificationMatrixManifest,
    ids: tuple[str, ...],
    coordinates: dict[str, str],
    aliases: dict[str, str],
    recorded: dict[str, dict],
    mode: CascadeReplayMode,
    proposals: ProposalReplay | None,
) -> tuple[list[dict], dict, list[dict]]:
    stages = []
    resolutions: dict[str, dict] = {}
    gaps = []
    unresolved = ids
    previous: dict[str, tuple[str, ...]] = {}
    for index, stage in enumerate(manifest.execution.stages):
        history = recorded.get(stage.id)
        if mode == CascadeReplayMode.HISTORICAL and history is None:
            continue
        entered = _canonical_ids(history.get("entered_clause_ids", []), aliases) if history else ()
        if history is not None and len(entered) != history["entered_clause_count"]:
            raise ValueError(f"cascade entry count mismatch: {stage.id}")
        stage_ids = (
            entered
            if mode == CascadeReplayMode.HISTORICAL
            else (ids if stage.apply_to == "all" else unresolved)
        )
        if not stage_ids:
            break
        resolution = effective_cascade_resolution(
            stage.resolution or manifest.execution.resolution,
            review_majority_min_confidence=(
                manifest.consensus.review_policy.accept_majority_min_confidence
            ),
        )
        if history and history.get("effective_resolution"):
            persisted = CascadeResolutionConfig.model_validate(history["effective_resolution"])
            if persisted != resolution:
                raise ValueError(f"effective cascade resolution differs from manifest: {stage.id}")
        if proposals is not None:
            proposals.prepare(stage, stage_ids)
            cumulative = proposals.consensus(stage, stage_ids, resolution, resolver=False)
            local = (
                proposals.consensus(stage, stage_ids, resolution, resolver=True)
                if index
                else cumulative
            )
        else:
            cumulative = source.consensus(manifest.matrix_id, stage.id, resolver=False)
            local = (
                source.consensus(manifest.matrix_id, stage.id, resolver=True)
                if index
                else cumulative
            )
        cumulative_by_id = _report_clauses(cumulative, coordinates, manifest.corpus_id)
        local_by_id = _report_clauses(local, coordinates, manifest.corpus_id)
        counts_before = resolution_counts(resolutions)
        if mode == CascadeReplayMode.HISTORICAL:
            recorded_unresolved = _canonical_ids(history["unresolved_clause_ids"], aliases)
            if not set(recorded_unresolved) <= set(entered):
                raise ValueError(f"unresolved clauses were not entered: {stage.id}")
            if len(recorded_unresolved) != history["unresolved_clause_count"]:
                raise ValueError(f"cascade unresolved count mismatch: {stage.id}")
            historical_reasons = {
                aliases[key]: tuple(value) for key, value in history["exit_reasons"].items()
            }
            reasons = {
                clause_id: (
                    ("no_consensus_result",)
                    if clause_id not in cumulative_by_id
                    else historical_reasons.get(clause_id, ("outcome_not_recorded",))
                )
                for clause_id in stage_ids
            }
            for clause_id in recorded_unresolved:
                if not reasons[clause_id]:
                    reasons[clause_id] = ("historically_unresolved",)
            unresolved = tuple(clause_id for clause_id in stage_ids if reasons[clause_id])
        elif index == 0:
            unresolved, reasons = cascade_unresolved_clause_ids(
                tuple(cumulative_by_id.values()),
                stage_clause_ids=stage_ids,
                resolution=resolution,
            )
        else:
            unresolved, reasons = cascade_stage_unresolved_clause_ids(
                tuple(cumulative_by_id.values()),
                tuple(local_by_id.values()),
                stage_clause_ids=stage_ids,
                previous_reasons=previous,
                resolution=resolution,
            )
        for clause_id in stage_ids:
            if clause_id not in cumulative_by_id or (index and clause_id not in local_by_id):
                gaps.append(
                    {
                        "clause_id": clause_id,
                        "stage_id": stage.id,
                        "model_ids": list(stage.models),
                        "reason": "stage_not_observed"
                        if clause_id not in entered
                        else "consensus_not_available",
                    }
                )
                continue
            if mode == CascadeReplayMode.HISTORICAL:
                continue
            clause = cumulative_by_id[clause_id]
            local_clause = local_by_id[clause_id]
            captured = capture_resolved_dimensions(
                cumulative_clause=clause,
                stage_clause=(
                    local_clause
                    if resolution.statement_function_resolution_mode == "stage_resolver"
                    else clause
                ),
                previous_reasons=previous.get(clause_id, ()),
                remaining_reasons=reasons[clause_id],
                source=stage.id,
                initial_stage=index == 0,
                resolution=resolution,
                process_stage_clause=local_clause,
            )
            resolutions.setdefault(clause_id, {}).update(captured)
        counts_after = resolution_counts(resolutions)
        stages.append(
            {
                "stage_id": stage.id,
                "effective_resolution": resolution.model_dump(mode="json"),
                "entered_clause_count": len(stage_ids),
                "entered_clause_ids": list(stage_ids),
                "unresolved_clause_count": len(unresolved),
                "unresolved_clause_ids": list(unresolved),
                "exit_reasons": {key: list(value) for key, value in reasons.items()},
                "exit_reason_counts": reason_counts(reasons),
                **stage_accounting(clause_ids=stage_ids, reasons=reasons, selected_count=len(ids)),
                "resolution_counts_before": counts_before
                if mode != CascadeReplayMode.HISTORICAL
                else None,
                "resolution_counts_after": counts_after
                if mode != CascadeReplayMode.HISTORICAL
                else None,
                "newly_resolved_counts": {
                    key: counts_after[key] - counts_before[key] for key in counts_after
                }
                if mode != CascadeReplayMode.HISTORICAL
                else None,
                "historically_recorded": history,
                "recorded_wall_duration_seconds": history.get("wall_duration_seconds")
                if history
                else None,
            }
        )
        previous = reasons
    return stages, resolutions, gaps


def _canonical_ids(values: list[str], aliases: dict[str, str]) -> tuple[str, ...]:
    try:
        ids = tuple(aliases[value] for value in values)
    except KeyError as exc:
        raise ValueError(f"cascade clause outside run selection: {exc.args[0]}") from exc
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate clause in cascade stage selection")
    return ids


def _report_clauses(report: object, coordinates: dict[str, str], corpus_id: str) -> dict:
    if report is None:
        return {}
    if report.corpus_id != corpus_id:
        raise ValueError("consensus corpus does not match run selection")
    if report.clause_count != len(report.clauses):
        raise ValueError("consensus clause count differs from its records")
    result = {}
    for clause in report.clauses:
        if coordinates.get(clause.clause_id) != clause.document_key:
            raise ValueError(
                f"consensus clause outside selected document coordinates: {clause.clause_id}"
            )
        if clause.clause_id in result:
            raise ValueError(f"duplicate consensus clause: {clause.clause_id}")
        result[clause.clause_id] = clause
    return result


def render_replay_markdown(payload: dict[str, Any]) -> str:
    selected = payload["selected_clause_count"]
    accounted = payload["accounted_clause_count"]
    early_count = payload["early_exit_count"]
    early_rate = payload["early_exit_rate"]
    missing = payload["requires_inference_clause_count"]
    lines = [
        "# Cascade replay",
        "",
        f"Mode: `{payload['mode']}`. No LLM inference performed.",
        "",
        f"Selected/accounted clauses: **{selected} / {accounted}**.",
        f"Efficient early exits: **{early_count} ({early_rate:.2%})**.",
        f"Clauses with missing stage observations: **{missing}**.",
        "",
        "| Stage | Entered | Completed with evidence | Open | Missing consensus |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for stage in payload["stages"]:
        lines.append(
            f"| {stage['stage_id']} | {stage['entered_clause_count']} | "
            f"{stage['completed_clause_count']} | {stage['unresolved_clause_count']} | "
            f"{stage['missing_consensus_clause_count']} |"
        )
    lines.extend(["", "## Interpretation", ""])
    lines.extend(f"- {item}" for item in payload["limitations"])
    lines.extend(
        [
            "",
            "Historical stage counters are preserved under `historically_recorded`, "
            "not relabelled as corrected results.",
            "Detailed reasons, resolution captures, missing observations and source "
            "fingerprints are in `cascade-replay.json`.",
            "",
        ]
    )
    return "\n".join(lines)
