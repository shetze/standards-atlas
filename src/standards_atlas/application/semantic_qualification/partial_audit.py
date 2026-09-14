"""Immutable audit of stored partial responses and source-bound decision plans.

A summary report is not a provider response. Missing raw artifacts are counted
as unavailable, never reconstructed from an error message or another task's run.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any

from standards_atlas.application.model.source_structure import structure_fingerprint
from standards_atlas.application.semantic_qualification.partial_diagnostics import (
    describe_partial_plan,
    summarize_partial_plans,
)
from standards_atlas.application.semantic_qualification.partial_observations import (
    PARTIAL_REQUEST_SCHEMA_VERSION,
    PartialObservation,
    PartialRequestPlan,
    ordered_attributes,
    partial_response_diagnostics,
)
from standards_atlas.application.semantic_qualification.partial_proposals import load_partial_inputs
from standards_atlas.application.semantic_qualification.partial_requests import (
    PartialProposalConfig,
    PartialTaskResources,
    prepare_partial_request,
)
from standards_atlas.application.semantic_qualification.request_builder import (
    build_clause_reference,
    serialize_generation_request,
)
from standards_atlas.application.semantic_qualification.response_identity import response_identity
from standards_atlas.application.semantic_qualification.taxonomy_decisions import (
    derive_clause_decision_plan,
    load_taxonomy_rules,
)


class _AuditSource:
    """Read only, bounded to one run root, without ZIP extraction or symlink escape."""

    def __init__(self, path: Path):
        self.path = path.resolve()
        self.archive = None
        self.fingerprints: dict[str, str] = {}
        if path.is_file() and zipfile.is_zipfile(path):
            self.archive = zipfile.ZipFile(path)
            names = self.archive.namelist()
            if len(names) != len(set(names)):
                self.close()
                raise ValueError("duplicate partial archive member names")
            reports = [
                n
                for n in names
                if n == "partial-run-report.json" or n.endswith("/partial-run-report.json")
            ]
            if len(reports) != 1:
                self.close()
                raise ValueError("partial archive must contain exactly one run report")
            self.prefix = reports[0].removesuffix("partial-run-report.json")
            self.report_name = "partial-run-report.json"
            self.names = {n.removeprefix(self.prefix) for n in names if n.startswith(self.prefix)}
            self.root = self.path
        else:
            self.root = self.path if path.is_dir() else self.path.parent
            self.report_name = "partial-run-report.json" if path.is_dir() else path.name
            candidates = [self.root / self.report_name, self.root / "partial-run-plan.json"]
            candidates.extend((self.root / "cases").rglob("*.json"))
            self.names = {p.relative_to(self.root).as_posix() for p in candidates if p.is_file()}
            self.prefix = ""
        if self.archive is None and (self.root / ".partial-run.lock").exists():
            raise ValueError("partial experiment has an active writer; audit a closed run or copy")

    def close(self) -> None:
        if self.archive is not None:
            self.archive.close()

    def read(self, name: str) -> Any:
        relative = PurePosixPath(name)
        if relative.is_absolute() or ".." in relative.parts or "\\" in name:
            raise ValueError(f"unsafe partial artifact path: {name}")
        if self.archive is not None:
            raw = self.archive.read(self.prefix + name)
        else:
            target = (self.root / name).resolve()
            if not target.is_relative_to(self.root):
                raise ValueError(f"partial artifact escapes source: {name}")
            raw = target.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if name in self.fingerprints and self.fingerprints[name] != digest:
            raise ValueError(f"partial artifact changed during audit: {name}")
        self.fingerprints[name] = digest
        return json.loads(raw)

    def optional(self, name: str) -> Any:
        return self.read(name) if name in self.names else None


def _load_plan(source, case, example):
    directory = case["case_directory"]
    saved = source.optional(f"{directory}/partial-request-plan.json")
    plan = PartialRequestPlan.model_validate(saved) if saved is not None else None
    status = "stored_only" if plan is not None else "unavailable"
    if example is not None:
        clause = build_clause_reference(example.input)
        if clause.model_dump(mode="json") != case["clause"]:
            raise ValueError("source corpus clause identity/content hash differs from report")
        content = example.input["content"]
        derived = derive_clause_decision_plan(
            example.input["context"],
            text=content["text"],
            content_hash=content["hash"],
        )
        if plan is not None:
            if derived != plan.decision_plan:
                raise ValueError(
                    "stored decision plan differs from independently replayed source rules"
                )
            status = "source_verified"
        else:
            # Only the source and requested/fixed partition can be reconstructed
            # from a summary. Do not invent a generation or provider identity.
            fixed = case.get("fixed_attributes", {})
            selected = ordered_attributes(list(case["requested_attributes"]) + list(fixed))
            plan = PartialRequestPlan(
                schema_version=PARTIAL_REQUEST_SCHEMA_VERSION,
                clause=clause,
                decision_plan=derived,
                selected_attributes=selected,
                requested_attributes=ordered_attributes(case["requested_attributes"]),
                fixed_attributes=fixed,
            )
            status = "reconstructed_from_source"
    if plan is not None and (
        plan.clause.model_dump(mode="json") != case["clause"]
        or list(plan.requested_attributes) != case["requested_attributes"]
        or plan.fixed_attributes != case["fixed_attributes"]
    ):
        raise ValueError("stored/reconstructed partial plan differs from reported case")
    return plan, status


def _audit_case(source, case, example, config, resources):
    directory = case["case_directory"]
    expected = "cases/" + structure_fingerprint({"example_id": case["example_id"]})
    if directory != expected:
        raise ValueError("case directory does not match the reported example identity")
    result = {
        "example_id": case["example_id"],
        "clause": case["clause"],
        "case_directory": directory,
        "reported_status": case["status"],
        "reported_error": case.get("error"),
        "integrity_errors": [],
        "plan_status": "unavailable",
        "response_status": "unavailable",
        "request_check": "unavailable",
        "observation_check": "unavailable",
        "missing_artifacts": [
            name
            for name in (
                "partial-request-plan.json",
                "request.json",
                "response.json",
                "partial-observation.json",
            )
            if f"{directory}/{name}" not in source.names
        ],
    }
    plan, result["plan_status"] = _load_plan(source, case, example)
    if plan is not None:
        result["decision_plan"] = plan.decision_plan.model_dump(mode="json")
        result["decision_plan_summary"] = describe_partial_plan(plan)
    request = source.optional(f"{directory}/request.json")
    observation_payload = source.optional(f"{directory}/partial-observation.json")
    observation = None
    if observation_payload is not None:
        observation = PartialObservation.model_validate(observation_payload)
        if observation.plan != plan:
            raise ValueError("observation plan differs from saved partial plan")
        result["observation_check"] = "internally_valid"
    if request is not None and plan is not None:
        metadata = request.get("metadata", {})
        if metadata.get("partial_plan_fingerprint") != plan.fingerprint:
            raise ValueError("request is not bound to the saved partial plan")
        if observation is not None and (
            metadata.get("qualification_input_fingerprint") != observation.request_fingerprint
        ):
            raise ValueError("observation request fingerprint mismatch")
        if metadata.get("requested_attributes") != list(plan.requested_attributes):
            raise ValueError("request attribute selection differs from partial plan")
        if config is not None:
            if request.get("model") != config.model or request.get("prompt_version") != (
                config.prompt_version
            ):
                raise ValueError("request model/prompt differs from run configuration")
            canonical_schema = dict(PartialTaskResources.load(resources, config).schema)
            canonical_schema["properties"] = {
                key: value
                for key, value in canonical_schema["properties"].items()
                if key in plan.requested_attributes or key in {"confidence", "rationale"}
            }
            canonical_schema["required"] = list(plan.requested_attributes)
            if request.get("output_schema") != canonical_schema:
                raise ValueError("request schema differs from the canonical partial contract")
        result["request_check"] = "plan_bound"
        if config is not None and example is not None:
            prepared = prepare_partial_request(
                config,
                example.id,
                example.input,
                PartialTaskResources.load(resources, config),
                accepted_attributes=plan.accepted_attributes,
                accepted_state_sha256=plan.accepted_state_sha256,
            )
            if prepared.request is None or request != serialize_generation_request(
                prepared.request
            ):
                raise ValueError("stored request differs from independently regenerated request")
            result["request_check"] = "source_regenerated"
    response = source.optional(f"{directory}/response.json")
    if response is not None:
        result["response_status"] = "stored_unchecked"
        if observation is not None and observation.response_sha256 is not None:
            if structure_fingerprint(response) != observation.response_sha256:
                raise ValueError("saved response checksum differs from observation")
            result["response_checksum_check"] = "matched"
            if observation.outcome == "evaluated" and observation.values != response.get("value"):
                raise ValueError("accepted observation differs from original provider values")
        else:
            result["response_checksum_check"] = "unavailable"
        if request is not None and plan is not None:
            result["response_identity"] = response_identity(
                response,
                requested_model=request["model"],
                prompt_version=request["prompt_version"],
                provider=config.provider if config is not None else "unverified-run-config",
            )
            result["response_validation"] = partial_response_diagnostics(
                response.get("value"),
                request["output_schema"],
                plan,
            )
            result["response_status"] = "inspected"
        if (
            observation is not None
            and config is not None
            and (observation.model != config.model or observation.provider != config.provider)
        ):
            result["integrity_errors"].append("observation voter differs from run configuration")
    # Gateway schema failures may only survive in immutable execution attempts.
    # Inspect every saved failed payload independently; never pick an arbitrary
    # 'latest' execution (execution directory names are not chronological).
    attempts = []
    for name in sorted(source.names):
        if not name.startswith(directory + "/executions/") or "/attempt-" not in name:
            continue
        payload = source.read(name)
        error = payload.get("error")
        if not error:
            continue
        item = {"artifact": name, "error": error.get("message"), "status": "unavailable"}
        raw = error.get("raw_content")
        if isinstance(raw, str) and plan is not None:
            try:
                value = json.loads(raw)
            except (ValueError, TypeError) as exc:
                item.update(status="not_json", parsing_error=str(exc))
            else:
                attempt_request = payload.get("request", {})
                if attempt_request.get("metadata", {}).get("partial_plan_fingerprint") != (
                    plan.fingerprint
                ):
                    item.update(status="unbound", parsing_error="attempt/plan identity mismatch")
                elif "output_schema" in attempt_request:
                    item.update(
                        status="inspected",
                        response_validation=partial_response_diagnostics(
                            value,
                            attempt_request["output_schema"],
                            plan,
                        ),
                    )
        attempts.append(item)
    result["failed_attempts"] = attempts
    return result, plan


def audit_partial_experiment(
    *,
    experiment: Path,
    output_directory: Path,
    resources: Path,
    run: Path | None = None,
    dataset: Path | None = None,
) -> dict[str, Any]:
    """Inspect original artifacts where available. Write a portable, separate report.

    Supplying a source run/dataset independently checks plans and regeneration;
    with a summary alone that part is explicitly unavailable. This never runs a
    gateway, recovers observations, changes votes, or publishes data.
    """
    if run is not None and dataset is not None:
        raise ValueError("provide at most one of --run or --dataset")
    destination = output_directory.resolve()
    if destination.exists():
        raise ValueError("partial audit output must be a new, separate directory")
    for name in (
        "data",
        "src/standards_atlas/resources",
        ".atlas/data/documents",
        ".atlas/data/knowledge-evidence",
    ):
        if destination.is_relative_to(Path(name).resolve()):
            raise ValueError("audit output must not be a canonical/public data directory")
    source = _AuditSource(experiment)
    try:
        for path in (experiment, run, dataset):
            if path is not None and (
                destination == path.resolve()
                or (path.is_dir() and destination.is_relative_to(path.resolve()))
            ):
                raise ValueError("audit output must be outside the input directory")
        # A report file represents its run root if run artifacts are present.
        if (
            source.archive is None
            and "partial-run-plan.json" in source.names
            and destination.is_relative_to(source.root)
        ):
            raise ValueError("audit output must be outside the experiment root")
        report = source.read(source.report_name)
        if report.get("kind") != "partial-run-report" or report.get("schema_version") != "1.0":
            raise ValueError("expected a schema-1.0 partial-run-report")
        cases = report["cases"]
        if not cases or len({c["example_id"] for c in cases}) != len(cases):
            raise ValueError("partial report must contain unique nonempty case identities")
        if len(cases) != report["accounted_count"] or len(cases) != report["selected_count"]:
            raise ValueError("partial report case counts do not match selection")
        if dict(Counter(c["status"] for c in cases)) != report["status_counts"]:
            raise ValueError("partial report status counts differ from cases")
        manifest = source.optional("partial-run-plan.json")
        config = PartialProposalConfig.model_validate(manifest["config"]) if manifest else None
        if manifest is not None and [c["example_id"] for c in manifest["cases"]] != [
            c["example_id"] for c in cases
        ]:
            raise ValueError("run plan and report selections differ")
        inputs = load_partial_inputs(run=run, dataset=dataset) if run or dataset else None
        examples = {item.id: item for item in inputs.examples} if inputs else {}
        if inputs is not None and len(examples) != len(inputs.examples):
            raise ValueError("source dataset has duplicate example ids")
        results, plans = [], []
        for case in cases:
            try:
                if inputs is not None and case["example_id"] not in examples:
                    raise ValueError("reported case is absent from selected source corpus")
                item, plan = _audit_case(
                    source,
                    case,
                    examples.get(case["example_id"]),
                    config,
                    resources,
                )
                if plan is not None:
                    plans.append(plan)
            except (ValueError, OSError, KeyError, TypeError) as exc:
                item = {
                    "example_id": case["example_id"],
                    "clause": case.get("clause"),
                    "reported_status": case.get("status"),
                    "plan_status": "not_verified",
                    "response_status": "not_verified",
                    "integrity_errors": [f"{type(exc).__name__}: {exc}"],
                }
            results.append(item)
        rules = load_taxonomy_rules()
        audit = {
            "schema_version": "1.0",
            "kind": "partial-experiment-audit",
            "diagnostic_only": True,
            "gateway_request_count": 0,
            "observations_modified": False,
            "acceptance_changed": False,
            "selected_count": len(cases),
            "accounted_count": len(results),
            "reported_status_counts": report["status_counts"],
            "plan_status_counts": dict(Counter(i["plan_status"] for i in results)),
            "response_status_counts": dict(Counter(i["response_status"] for i in results)),
            "integrity_error_case_count": sum(bool(i["integrity_errors"]) for i in results),
            "response_issue_counts": dict(
                Counter(
                    e["code"]
                    for i in results
                    for e in i.get("response_validation", {}).get("issues", [])
                )
            ),
            "failed_attempt_issue_counts": dict(
                Counter(
                    e["code"]
                    for i in results
                    for a in i.get("failed_attempts", [])
                    for e in a.get("response_validation", {}).get("issues", [])
                )
            ),
            "decision_plan_summary": summarize_partial_plans(plans),
            "rules_eligible_to_fix": [r.id for r in rules.rules if r.maximum_state == "fixed"],
            "pending_rules": [r.id for r in rules.rules if r.qualification == "pending-review"],
            "source_fingerprints": inputs.fingerprints if inputs else {},
            "artifact_fingerprints": dict(sorted(source.fingerprints.items())),
            "limitations": [
                "A reported error is not an original response; absent values are never guessed.",
                "Reconstructed source plans do not prove the original request or provider output.",
                "Only source_regenerated requests were compared to complete regenerated requests.",
                "Checksums bind bytes, not semantic accuracy or runtime artifact attestation.",
                "All-errors diagnostics never salvage fields or change grouped acceptance.",
                "Attempt diagnostics are separate from logical response counts and votes.",
            ],
            "cases": results,
        }
    finally:
        source.close()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".partial-audit-", dir=destination.parent) as temporary:
        staging = Path(temporary) / "audit"
        staging.mkdir()
        (staging / "partial-audit.json").write_text(
            json.dumps(audit, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        (staging / "partial-audit.md").write_text(render_partial_audit(audit), encoding="utf-8")
        if destination.exists():
            raise ValueError("partial audit output already exists")
        staging.rename(destination)
    return audit


def render_partial_audit(audit: dict[str, Any]) -> str:
    summary = audit["decision_plan_summary"]
    lines = [
        "# Partial experiment audit",
        "",
        "Read-only; no inference or acceptance changes.",
        "",
        f"Selected/accounted: {audit['selected_count']} / {audit['accounted_count']}.",
        f"Original response inspection: `{audit['response_status_counts']}`.",
        f"Decision plan inspection: `{audit['plan_status_counts']}`.",
        f"Cases with integrity errors: {audit['integrity_error_case_count']}.",
        "",
        "## Response contract",
        "",
        f"Original response issues: `{audit['response_issue_counts']}`.",
        f"Failed-attempt issues (not extra votes): `{audit['failed_attempt_issue_counts']}`.",
        "No issues recorded is not success when raw responses are unavailable.",
        "",
        "## Decision plan",
        "",
        f"Source origins: `{summary['source_origins']}`.",
        f"Fixed/requested attributes: {summary['fixed_attribute_count']} / "
        f"{summary['requested_attribute_count']}.",
        f"Rules eligible to fix: `{audit['rules_eligible_to_fix']}`.",
        f"Rules pending independent review: `{audit['pending_rules']}`.",
        "",
        "| Attribute | Fixed | Hint | Conflict | Open |",
        "|---|---:|---:|---:|---:|",
    ]
    for name, counts in summary["attribute_states"].items():
        lines.append(
            f"| {name} | "
            + " | ".join(
                str(counts.get(state, 0)) for state in ("fixed", "hint", "conflict", "open")
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Evidence and limitations",
            "",
            "Exact original values, all checkable violations, plan sources and artifact "
            "checksums are in partial-audit.json. Missing evidence is explicit.",
        ]
    )
    lines.extend("- " + text for text in audit["limitations"])
    return "\n".join(lines) + "\n"
