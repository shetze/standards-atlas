"""Fresh, independently recorded repetitions around the existing partial engine."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from standards_atlas.application.model.source_structure import structure_fingerprint
from standards_atlas.application.schema import (
    require_current_payload,
    require_current_schema,
    require_supported_schema,
)
from standards_atlas.application.semantic_qualification.acceptance_profiles import (
    PartialAcceptanceProfile,
)
from standards_atlas.application.semantic_qualification.campaign_selection import (
    load_campaign,
    safe_files,
)
from standards_atlas.application.semantic_qualification.mixed_applicability import (
    run_mixed_applicability,
    verify_mixed_applicability,
)
from standards_atlas.application.semantic_qualification.mixed_evidence import MixedConsensusReport
from standards_atlas.application.semantic_qualification.partial_cascade import (
    completion_for_matrix,
    run_partial_cascade,
)
from standards_atlas.application.semantic_qualification.partial_cascade_archive import (
    archive_partial_cascade,
    verify_partial_cascade,
)
from standards_atlas.application.semantic_qualification.partial_proposals import (
    _atomic_json,
    _run_lock,
)
from standards_atlas.application.semantic_qualification.performance import RequestTiming
from standards_atlas.application.semantic_qualification.qualification_matrix import (
    QualificationMatrixManifest,
)
from standards_atlas.application.semantic_qualification.request_builder import (
    serialize_generation_request,
)

FRESH_MODES = ("fresh_end_to_end", "fresh_detail_fixed_presence")


class FreshLedgerGateway:
    """Record physical calls before they become observations; reject cached results.

    A cache-free adapter is required by the CLI. This second check ensures even a
    misconfigured/custom gateway cannot quietly pass off a cache hit as fresh.
    The ledger proves recorded execution, not independent runtime attestation.
    """

    def __init__(self, gateway, *, root: Path, binding: dict, model_id: str):
        self.gateway, self.root = gateway, root
        self.binding, self.model_id = binding, model_id

    def health(self):
        return self.gateway.health()

    def generate_structured(self, request):
        event_id = uuid.uuid4().hex
        event = {
            "schema_version": "1.0",
            "kind": "qualification-request-event",
            "event_id": event_id,
            "binding": self.binding,
            "model_id": self.model_id,
            "request": serialize_generation_request(request),
            "started_at": datetime.now(UTC).isoformat(),
        }
        require_current_payload("qualification-request-event", event)
        start = time.monotonic()
        try:
            result = self.gateway.generate_structured(request)
            event.update(
                returned=True,
                cached=result.cached,
                response_sha256=structure_fingerprint(asdict(result)),
                usage=asdict(result.usage) if result.usage is not None else None,
            )
            if result.cached:
                raise ValueError("fresh qualification rejected a cached provider response")
            return result
        except Exception as exc:
            event["error"] = {"type": type(exc).__name__, "message": str(exc)}
            raise
        finally:
            event["wall_seconds"] = time.monotonic() - start
            _atomic_json(self.root / "qualification-events" / f"{event_id}.json", event)


def job_key(variant: str, mode: str, repetition: int) -> str:
    return f"jobs/{variant}/{mode}/{repetition:02d}"


def _names(root):
    return {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}


def _receipt_hashes(root):
    return {name: value for name, value in safe_files(root).items() if name != "repeat.json"}


def _timings(root, mode):
    timing = RequestTiming()
    patterns = ["policy/executions/execution-*/request-timing.json"]
    if mode != "fresh_detail_fixed_presence":
        patterns.append("stages/**/executions/execution-*/request-timing.json")
    for pattern in patterns:
        for p in root.glob(pattern):
            timing = timing.plus(RequestTiming.model_validate_json(p.read_bytes()))
    return timing


def verify_job(*, campaign: Path, key: str, resources: Path, loaded=None):
    """Rebuild acceptance and final policy; a summary's success boolean is not evidence."""
    loaded = loaded or load_campaign(campaign, resources)
    definition, spec, population, *_rest, selection = loaded
    components = key.split("/")
    if len(components) != 4 or components[0] != "jobs":
        raise ValueError("invalid qualification job key")
    _, variant_id, mode, raw_repeat = components
    if mode not in (*FRESH_MODES, "full_baseline"):
        raise ValueError("unsupported qualification repetition mode")
    repetition = int(raw_repeat)
    if key != job_key(variant_id, mode, repetition) or not 1 <= repetition <= (
        1 if mode == "full_baseline" else spec.repetitions
    ):
        raise ValueError("invalid qualification repetition index")
    variant = next((v for v in spec.variants if v.id == variant_id), None)
    if variant is None or (mode == "full_baseline" and variant_id != spec.candidate):
        raise ValueError("job is not a configured variant")
    root = campaign / key
    if not root.resolve().is_relative_to(campaign.resolve()):
        raise ValueError("qualification job escapes campaign")
    receipt = json.loads((root / "repeat.json").read_bytes())
    require_supported_schema("partial-qualification-repeat", receipt.get("schema_version"))
    if receipt["binding"] != {
        "campaign_sha256": definition["campaign_sha256"],
        "job": key,
        "run_id": receipt["binding"]["run_id"],
    }:
        raise ValueError("repeat belongs to another campaign/job")
    if receipt.get("kind") != "partial-qualification-repeat" or receipt.get("mode") != mode:
        raise ValueError("qualification receipt kind/mode differs from job")
    if receipt.get("status") != "completed":
        raise ValueError("interrupted qualification job is not a completed repetition")
    if receipt["files"] != _receipt_hashes(root):
        raise ValueError("qualification repeat evidence changed after sealing")
    stored = definition["variants"][variant_id]
    matrix = QualificationMatrixManifest.model_validate(stored["matrix"])
    expected_ids = (
        {e.id for e in population}
        if mode == "full_baseline"
        else set(selection["cohorts"]["evaluation_union"])
    )
    examples = tuple(e for e in population if e.id in expected_ids)
    engine = root / "run"
    names = _names(engine)

    def read(name):
        return (engine / name).read_bytes()

    if mode == "fresh_detail_fixed_presence":
        anchor_key = job_key(variant_id, "fresh_end_to_end", 1)
        anchor = verify_job(campaign=campaign, key=anchor_key, resources=resources, loaded=loaded)
        mixed = MixedConsensusReport.model_validate_json(read("gate-anchor.json"))
        if mixed != anchor["mixed"] or receipt.get("anchor_job") != anchor_key:
            raise ValueError("fixed-presence repetition differs from the verified frozen gate")
        if any(n.startswith("stages/") for n in names):
            raise ValueError("fixed-presence repetition cannot include a new cascade")
    else:
        mixed, replayed_examples, replayed_matrix = verify_partial_cascade(
            read=read, names=names, resources=resources
        )
        if replayed_examples != examples or replayed_matrix != matrix:
            raise ValueError("repetition source/matrix differs from frozen campaign")
        plan = json.loads(read("partial-cascade-plan.json"))
        summary = json.loads(read("partial-cascade-report.json"))
        if (
            not summary["executed"]
            or "stage_limit" in plan
            or mixed.completion_profile != completion_for_matrix(matrix)
            or plan.get("prompt_version", "taxonomy-partial-v2") != variant.prompt
            or plan.get("acceptance_profile") != stored["acceptance_profile"]
        ):
            raise ValueError("partial/changed/reduced execution cannot qualify")
        if len(summary["stages"]) != len(matrix.execution.stages) and mixed.completed_count != len(
            examples
        ):
            raise ValueError("incomplete stage sequence is not a finished cascade")
    policy = verify_mixed_applicability(
        read=read, names=names, report=mixed, examples=examples, manifest=matrix
    )
    if policy is None:
        raise ValueError("repetition lacks verified final applicability policy")
    required_mode = mode if mode in FRESH_MODES else "operational"
    if policy.qualification_mode.value != required_mode:
        raise ValueError("policy freshness mode differs from repetition")
    events = [
        json.loads(p.read_bytes()) for p in sorted((root / "qualification-events").glob("*.json"))
    ]
    for event in events:
        require_supported_schema("qualification-request-event", event.get("schema_version"))
        if event.get("kind") != "qualification-request-event":
            raise ValueError("unsupported physical request event")
    ids = [e["event_id"] for e in events]
    if len(set(ids)) != len(ids) or any(e["binding"] != receipt["binding"] for e in events):
        raise ValueError("repeated or foreign physical event identity")
    if any(e.get("cached") is True for e in events):
        raise ValueError("cached evidence cannot qualify a fresh repetition")
    timing = _timings(engine, mode)
    if (
        timing.request_count != len(events)
        or timing.cached_response_count
        or timing.failed_request_count != sum("error" in e for e in events)
        or timing.fresh_response_count
        != sum("response_sha256" in e and "error" not in e for e in events)
    ):
        raise ValueError("physical event ledger does not reconcile with recorded work")
    event_responses = {e["response_sha256"] for e in events if "response_sha256" in e}
    responses = [n for n in names if n.endswith("/response.json")]
    for name in responses:
        data = json.loads(read(name))
        if data.get("cached") or structure_fingerprint(data) not in event_responses:
            raise ValueError("stored response has no fresh physical event in this repetition")
    if (
        not events
        and mixed.clause_count
        and any(
            d.source == "models" and d.status == "accepted"
            for c in mixed.clauses
            for d in c.decisions
        )
        and mode != "fresh_detail_fixed_presence"
    ):
        raise ValueError("model acceptance without fresh model work")
    usage = {}
    for field in ("prompt_tokens", "completion_tokens", "total_tokens"):
        known = [e.get("usage", {}).get(field) for e in events if isinstance(e.get("usage"), dict)]
        known = [v for v in known if type(v) is int and v >= 0]
        usage[field] = sum(known) if known else None
        usage[field + "_measured_calls"] = len(known)
    usage["physical_calls"] = len(events)
    usage["complete"] = all(
        usage[f + "_measured_calls"] == len(events)
        for f in ("prompt_tokens", "completion_tokens", "total_tokens")
    )
    return {
        "key": key,
        "mixed": mixed,
        "policy": policy,
        "events": events,
        "timing": timing,
        "usage": usage,
        "receipt": receipt,
        "examples": examples,
        "matrix": matrix,
        "artifact_sha256": hashlib.sha256((root / "repeat.json").read_bytes()).hexdigest(),
    }


def run_campaign(
    *,
    campaign: Path,
    resources: Path,
    execute: bool = False,
    phase: str = "all",
    variant_id: str | None = None,
    gateway_context=None,
    progress=None,
):
    """Sequential orchestration; ordinary per-clause failures remain in the reports.

    Sealed repetitions are replay-verified, never regenerated as extra evidence.
    An interrupted job resumes within the same independent repetition and ledger.
    """
    require_current_schema("partial-qualification-repeat", "1.0")
    campaign = campaign.resolve()
    loaded = load_campaign(campaign, resources)
    definition, spec, population, *_rest, selection = loaded
    if phase not in ("all", "end-to-end", "fixed-detail", "full"):
        raise ValueError("phase must be all, end-to-end, fixed-detail or full")
    variants = tuple(v for v in spec.variants if variant_id is None or v.id == variant_id)
    if not variants:
        raise ValueError("unknown campaign variant")
    if phase == "full":
        variants = tuple(v for v in variants if v.id == spec.candidate)
        if not variants:
            raise ValueError("full baseline is only defined for the candidate")
    modes = (
        FRESH_MODES
        if phase == "all"
        else ("fresh_end_to_end",)
        if phase == "end-to-end"
        else ("fresh_detail_fixed_presence",)
        if phase == "fixed-detail"
        else ("full_baseline",)
    )
    jobs = [
        (v, mode, rep)
        for v in variants
        for mode in modes
        for rep in range(1, 2 if mode == "full_baseline" else spec.repetitions + 1)
    ]
    report = {
        "schema_version": "1.0",
        "kind": "partial-qualification-execution",
        "campaign_sha256": definition["campaign_sha256"],
        "run_mode": "executed" if execute else "planned",
        "jobs": [],
    }
    require_current_payload("partial-qualification-execution", report)
    if not execute:
        report["jobs"] = [
            {"job": job_key(v.id, mode, rep), "status": "planned"} for v, mode, rep in jobs
        ]
        return report
    if gateway_context is None:
        raise ValueError("execution requires a cache-disabled gateway context")
    if phase == "full":
        from standards_atlas.application.semantic_qualification.campaign_evaluation import (
            evaluate_campaign,
        )

        gate = evaluate_campaign(campaign=campaign, resources=resources, write=False)
        if not gate["pre_full_eligible"]:
            raise ValueError("full baseline blocked by missing/failed qualification evidence")
    with _run_lock(campaign):
        for variant, mode, rep in jobs:
            key = job_key(variant.id, mode, rep)
            root = campaign / key
            if progress:
                progress(f"Qualification {key}")
            if (root / "repeat.json").is_file():
                try:
                    verify_job(campaign=campaign, key=key, resources=resources, loaded=loaded)
                    report["jobs"].append({"job": key, "status": "verified_existing"})
                    continue
                except (ValueError, OSError, KeyError) as exc:
                    report["jobs"].append(
                        {"job": key, "status": "invalid_evidence", "error": str(exc)}
                    )
                    continue
            root.mkdir(parents=True, exist_ok=True)
            engine = root / "run"
            if any(p.is_symlink() for p in root.rglob("*")):
                raise ValueError("unsafe link in campaign execution")
            identity = root / "execution-identity.json"
            binding = {"campaign_sha256": definition["campaign_sha256"], "job": key}
            if identity.is_file():
                old = json.loads(identity.read_bytes())
                if any(old[k] != v for k, v in binding.items()):
                    raise ValueError("interrupted execution belongs to another job")
                binding = old
            else:
                binding["run_id"] = uuid.uuid4().hex
                _atomic_json(identity, binding)
            variant_snapshot = definition["variants"][variant.id]
            matrix = QualificationMatrixManifest.model_validate(variant_snapshot["matrix"])
            profile = (
                PartialAcceptanceProfile.model_validate(variant_snapshot["acceptance_profile"])
                if variant_snapshot["acceptance_profile"]
                else None
            )
            ids = (
                {e.id for e in population}
                if mode == "full_baseline"
                else set(selection["cohorts"]["evaluation_union"])
            )
            examples = tuple(e for e in population if e.id in ids)

            @contextmanager
            def gateway(model, *, event_root=root, event_binding=binding):
                with gateway_context(model) as delegate:
                    yield FreshLedgerGateway(
                        delegate, root=event_root, binding=event_binding, model_id=model.id
                    )

            started = time.monotonic()
            anchor_key = None
            try:
                if mode == "fresh_detail_fixed_presence":
                    anchor_key = job_key(variant.id, "fresh_end_to_end", 1)
                    anchor = verify_job(
                        campaign=campaign, key=anchor_key, resources=resources, loaded=loaded
                    )
                    mixed = anchor["mixed"]
                    engine.mkdir(exist_ok=True)
                    _atomic_json(engine / "gate-anchor.json", mixed.model_dump(mode="json"))
                else:
                    run_partial_cascade(
                        manifest=matrix,
                        examples=examples,
                        output_directory=engine,
                        resources=resources,
                        execute=True,
                        gateway_context=gateway,
                        prompt_version=variant.prompt,
                        acceptance_profile=profile,
                        require_taxonomy_decisions=variant.require_taxonomy_decisions,
                        source_fingerprints={"campaign": definition["campaign_sha256"]},
                        progress=progress,
                    )
                    mixed = MixedConsensusReport.model_validate_json(
                        (engine / "mixed-consensus-report.json").read_bytes()
                    )
                run_mixed_applicability(
                    report=mixed,
                    examples=examples,
                    manifest=matrix,
                    root=engine,
                    resources=resources,
                    gateway_context=gateway,
                    qualification_mode=mode if mode in FRESH_MODES else "operational",
                )
                receipt = {
                    "schema_version": "1.0",
                    "kind": "partial-qualification-repeat",
                    "binding": binding,
                    "status": "completed",
                    "mode": mode,
                    "anchor_job": anchor_key,
                    "wall_seconds_last_invocation": time.monotonic() - started,
                    "files": _receipt_hashes(root),
                }
                require_current_payload("partial-qualification-repeat", receipt)
                _atomic_json(root / "repeat.json", receipt)
                verify_job(campaign=campaign, key=key, resources=resources, loaded=loaded)
                if mode == "full_baseline":
                    # Keep the existing checksummed adoption archive; qualification receipt
                    # is resealed after the archiver writes its manifest metadata.
                    archive = archive_partial_cascade(
                        root=engine, archive_directory=campaign / "archives", resources=resources
                    )
                    receipt["files"] = _receipt_hashes(root)
                    _atomic_json(root / "repeat.json", receipt)
                    report["full_archive"] = str(archive)
                report["jobs"].append({"job": key, "status": "completed"})
            except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
                report["jobs"].append({"job": key, "status": "failed", "error": str(exc)})
    _atomic_json(campaign / "execution-report.json", report)
    return report
