"""Explicit model-free reuse/publication workflow and opt-in document restoration."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from standards_atlas.application.catalog import StandardCatalog
from standards_atlas.application.catalog.atlasdata_binding import atlasdata_bindings
from standards_atlas.application.context.canonical_cbox import context_fingerprint
from standards_atlas.application.workflow.models import (
    ArtifactPolicy,
    WorkflowPlan,
    WorkflowStage,
    WorkflowStep,
)

# Re-run preflight on every invocation. Idempotence is provided by the canonical
# merge/transfer services, never by assuming an old marker authorizes a write.
KNOWLEDGE_STAGES = frozenset(
    {
        WorkflowStage.KNOWLEDGE_RESTORE,
        WorkflowStage.KNOWLEDGE_ADOPT,
        WorkflowStage.KNOWLEDGE_PUBLISH,
        WorkflowStage.CBOX_REPORT,
    }
)


def _command(
    family: str,
    document: str,
    stage: WorkflowStage,
    tokens: tuple[str, ...],
    output: Path,
) -> WorkflowStep:
    return WorkflowStep(
        family,
        document,
        stage,
        ("uv", "run", "standards-atlas", *tokens, "--output", str(output)),
        ArtifactPolicy.DERIVED,
        output_paths=(str(output),),
    )


def knowledge_plan(
    catalog: StandardCatalog,
    *,
    family_keys: tuple[str, ...],
    catalog_root: Path,
    manifest: Path,
    adopt_run: Path | None = None,
    restore: bool = False,
    publish: bool = False,
    strict_evidence: bool = False,
    knowledge_domain: str = "functional-safety",
) -> WorkflowPlan:
    bindings = atlasdata_bindings(catalog, root=catalog_root)
    keys = tuple(sorted(key for key, value in bindings.items() if value.family_key in family_keys))
    if not keys:
        raise ValueError("knowledge workflow requires manifest-owned physical AtlasData documents")
    selection = context_fingerprint(list(keys))[:12]
    report_root = Path("local/review/knowledge-workflow") / selection
    selector = tuple(value for key in keys for value in ("--document", key))
    transfer = ("--manifest", str(manifest), *selector, "--available-only", "--write")
    evidence = ("--strict-evidence",) if strict_evidence else ()
    steps = []
    if restore:
        steps.append(
            _command(
                "knowledge",
                selection,
                WorkflowStage.KNOWLEDGE_RESTORE,
                ("atlasdata", "import-enrichments", *transfer, *evidence),
                report_root / "restore.json",
            )
        )
    if adopt_run is not None:
        steps.append(
            _command(
                "knowledge",
                selection,
                WorkflowStage.KNOWLEDGE_ADOPT,
                (
                    "document",
                    "adopt-qualification",
                    "--run",
                    str(adopt_run),
                    *selector,
                    "--available-only",
                    "--write",
                ),
                report_root / "adopt.json",
            )
        )
    if publish:
        steps.append(
            _command(
                "knowledge",
                selection,
                WorkflowStage.KNOWLEDGE_PUBLISH,
                ("atlasdata", "export-enrichments", *transfer),
                report_root / "export.json",
            )
        )
        # A second process re-reads the public files and private evidence, rather
        # than displaying the pre-export in-memory objects as a roundtrip result.
        steps.append(
            _command(
                "knowledge",
                selection,
                WorkflowStage.KNOWLEDGE_RESTORE,
                ("atlasdata", "import-enrichments", *transfer, *evidence),
                report_root / "reimport.json",
            )
        )
    steps.append(
        _command(
            "knowledge",
            selection,
            WorkflowStage.CBOX_REPORT,
            (
                "document",
                "cbox-report",
                *selector,
                "--available-only",
                "--knowledge-domain",
                knowledge_domain,
            ),
            report_root / "cbox.json",
        )
    )
    return WorkflowPlan(families=family_keys, steps=tuple(steps))


def with_knowledge_restore(
    plan: WorkflowPlan,
    *,
    manifest: Path,
    strict_evidence: bool = False,
    knowledge_domain: str = "functional-safety",
) -> WorkflowPlan:
    """Restore after structural reconstruction and before context enrichment/consumers."""
    contextual = {
        item.document for item in plan.steps if item.stage is WorkflowStage.CONTEXT_ENRICHMENT
    }
    steps = []
    for step in plan.steps:
        steps.append(step)
        root = Path("local/review/knowledge-workflow/documents") / step.document
        if step.stage is WorkflowStage.TAXONOMY:
            steps.append(
                _command(
                    step.family,
                    step.document,
                    WorkflowStage.KNOWLEDGE_RESTORE,
                    (
                        "atlasdata",
                        "import-enrichments",
                        "--manifest",
                        str(manifest),
                        "--document",
                        step.document,
                        "--available-only",
                        "--write",
                        *(("--strict-evidence",) if strict_evidence else ()),
                    ),
                    root / "restore.json",
                )
            )
        if step.stage is WorkflowStage.CONTEXT_ENRICHMENT or (
            step.stage is WorkflowStage.TAXONOMY and step.document not in contextual
        ):
            steps.append(
                _command(
                    step.family,
                    step.document,
                    WorkflowStage.CBOX_REPORT,
                    (
                        "document",
                        "cbox-report",
                        "--document",
                        step.document,
                        "--knowledge-domain",
                        knowledge_domain,
                    ),
                    root / "cbox.json",
                )
            )
    return replace(plan, steps=tuple(steps))
