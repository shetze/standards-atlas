"""Explicit activation recommendations after rechecking the complete evidence chain."""

from __future__ import annotations

import hashlib
import json
import shlex
from pathlib import Path

import yaml

from standards_atlas.application.model.source_structure import structure_fingerprint
from standards_atlas.application.schema import require_current_payload, require_current_schema
from standards_atlas.application.semantic_qualification.analysis_archive import (
    create_analysis_archive,
)
from standards_atlas.application.semantic_qualification.campaign_evaluation import evaluate_campaign
from standards_atlas.application.semantic_qualification.campaign_selection import (
    load_campaign,
    safe_files,
)
from standards_atlas.application.semantic_qualification.partial_comparison import (
    _output_is_separate,
)
from standards_atlas.application.semantic_qualification.partial_proposals import _atomic_json


def archive_campaign(*, campaign: Path, output: Path, resources: Path) -> Path:
    """Archive even failed/partial qualifications, retaining explicit rejection reasons."""
    _output_is_separate(output.resolve(), (campaign,))
    evaluation = evaluate_campaign(campaign=campaign, resources=resources)
    definition, spec, *_ = load_campaign(campaign, resources)
    matrix = definition["variants"][spec.candidate]["matrix"]
    manifest = campaign / "qualification-archive-matrix.yaml"
    text = yaml.safe_dump(matrix, sort_keys=False)
    if manifest.exists() and manifest.read_text(encoding="utf-8") != text:
        raise ValueError("archive matrix differs from frozen campaign")
    manifest.write_text(text, encoding="utf-8")
    names = safe_files(campaign)
    return create_analysis_archive(
        output_directory=campaign,
        matrix_id=spec.id + "--qualification-campaign",
        manifest_path=manifest,
        core_paths=tuple(
            campaign / n
            for n in names
            if not n.endswith(".zip") or n == "inputs/review-package.zip"
        ),
        archive_directory=output,
        analysis_metrics={
            "clause_count": evaluation["selection"]["source_population_count"],
            "qualification_evaluation": evaluation,
        },
        matrix_passed=evaluation["activation_eligible"],
        execution_policy={"qualification_campaign": True, "automatic_activation": False},
    )


def activate_campaign(
    *,
    campaign: Path,
    output: Path,
    resources: Path,
    reviewer: str,
    review_reference: str,
    allow_below_target: bool = False,
) -> dict:
    """Export an immutable explicit run configuration; never overwrite project defaults."""
    require_current_schema("partial-qualified-activation", "1.0")
    output = output.resolve()
    _output_is_separate(output, (campaign,))
    if output.exists():
        raise ValueError("activation output must be new")
    if not reviewer.strip() or not review_reference.strip():
        raise ValueError("activation requires a named reviewer and review reference")
    result = evaluate_campaign(campaign=campaign, resources=resources)
    if not result["activation_eligible"]:
        raise ValueError("activation blocked: " + "; ".join(result["blocking_reasons"]))
    if not result["efficient_target_observed"] and not allow_below_target:
        raise ValueError("80% target not observed; explicit --allow-below-target is required")
    definition, spec, *_ = load_campaign(campaign, resources)
    candidate = definition["variants"][spec.candidate]
    output.mkdir(parents=True)
    manifest = output / "matrix.yaml"
    manifest.write_text(yaml.safe_dump(candidate["matrix"], sort_keys=False), encoding="utf-8")
    _atomic_json(output / "qualification-evaluation.json", result)
    command = [
        "uv",
        "run",
        "standards-atlas",
        "evaluation",
        "partial-cascade",
        "--manifest",
        str(manifest),
        "--prompt",
        candidate["configuration"]["prompt_version"],
    ]
    if candidate["acceptance_profile"] is not None:
        path = output / "acceptance-profile.yaml"
        path.write_text(
            yaml.safe_dump(candidate["acceptance_profile"], sort_keys=False), encoding="utf-8"
        )
        command += ["--acceptance-profile", str(path)]
    command += [
        "--dataset",
        "<source-dataset.json>",
        "--output",
        "<new-run-directory>",
        "--execute",
    ]
    payload = {
        "schema_version": "1.0",
        "kind": "partial-qualified-activation",
        "campaign_sha256": definition["campaign_sha256"],
        "evaluation_sha256": result["evaluation_sha256"],
        "candidate": spec.candidate,
        "reviewer": reviewer,
        "review_reference": review_reference,
        "files": safe_files(output),
        "effective_configuration": candidate["configuration"],
        "source_population_sha256": result["selection"]["source_population_sha256"],
        "efficient_target_observed": result["efficient_target_observed"],
        "below_target_explicitly_accepted": bool(
            allow_below_target and not result["efficient_target_observed"]
        ),
        "default_workflow_changed": False,
        "new_rule_qualifications": [],
        "command_template": command,
        "scope": (
            "qualified on pinned population and supplied reviews; "
            "not certification for arbitrary new corpora"
        ),
    }
    require_current_payload("partial-qualified-activation", payload)
    payload["activation_sha256"] = structure_fingerprint(payload)
    _atomic_json(output / "activation.json", payload)
    (output / "README.md").write_text(
        "# Explicit qualified candidate\n\n"
        "No repository defaults or source authorities were changed.\n\n"
        "Replace the two placeholders with source and a new output directory:\n\n```bash\n"
        + shlex.join(command)
        + "\n```\n\n"
        "Retain the qualification evidence and review applicability before using a new corpus.\n",
        encoding="utf-8",
    )
    return payload


def verify_activation(path: Path) -> dict:
    """Check a transported recommendation's own files; raw evidence is checked at export."""
    value = json.loads(path.read_bytes())
    if value.get("schema_version") != "1.0" or value.get("kind") != "partial-qualified-activation":
        raise ValueError("unsupported activation artifact")
    if value["activation_sha256"] != structure_fingerprint(
        {k: v for k, v in value.items() if k != "activation_sha256"}
    ):
        raise ValueError("activation identity changed")
    required = {"matrix.yaml", "qualification-evaluation.json"}
    optional = {"acceptance-profile.yaml"}
    if not required <= set(value["files"]) <= required | optional:
        raise ValueError("activation evidence inventory is incomplete or unexpected")
    if any(member.is_symlink() for member in path.parent.rglob("*")):
        raise ValueError("unsafe activation symlink")
    for name, digest in value["files"].items():
        member = path.parent / name
        if not member.resolve().is_relative_to(path.parent.resolve()) or member.is_symlink():
            raise ValueError("unsafe activation member")
        if hashlib.sha256(member.read_bytes()).hexdigest() != digest:
            raise ValueError("activation member changed")
    evaluation = json.loads((path.parent / "qualification-evaluation.json").read_bytes())
    if (
        evaluation["evaluation_sha256"]
        != structure_fingerprint({k: v for k, v in evaluation.items() if k != "evaluation_sha256"})
        or evaluation["campaign_sha256"] != value["campaign_sha256"]
        or evaluation["evaluation_sha256"] != value["evaluation_sha256"]
        or not evaluation["activation_eligible"]
    ):
        raise ValueError("activation does not reference an eligible evaluation")
    return value
