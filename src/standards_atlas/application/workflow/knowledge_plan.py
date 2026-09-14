"""Explicit model-free reuse/publication workflow and opt-in document restoration."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from standards_atlas.application.catalog import StandardCatalog
from standards_atlas.application.catalog.atlasdata_binding import atlasdata_bindings
from standards_atlas.application.context.canonical_cbox import context_fingerprint
from standards_atlas.application.workflow.models import (
    ArtifactPolicy,
    WorkflowOperation,
    WorkflowOperationKind,
    WorkflowPlan,
    WorkflowStage,
    WorkflowStep,
)

KNOWLEDGE_STAGES = frozenset(
    {
        WorkflowStage.KNOWLEDGE_RESTORE,
        WorkflowStage.KNOWLEDGE_ADOPT,
        WorkflowStage.KNOWLEDGE_PUBLISH,
        WorkflowStage.CBOX_REPORT,
    }
)


def _step(
    family: str,
    document: str,
    stage: WorkflowStage,
    operation: WorkflowOperation,
    output: Path,
) -> WorkflowStep:
    return WorkflowStep(
        family,
        document,
        stage,
        operation,
        ArtifactPolicy.DERIVED,
        output_paths=(str(output),),
    )


def _transfer_operation(
    kind: WorkflowOperationKind,
    *,
    manifest: Path,
    documents: tuple[str, ...],
    output: Path,
    strict_evidence: bool = False,
) -> WorkflowOperation:
    parameters: dict[str, str | bool | tuple[str, ...]] = {
        "manifest": str(manifest),
        "documents": documents,
        "available_only": True,
        "write": True,
        "output": str(output),
    }
    if kind is WorkflowOperationKind.ATLASDATA_IMPORT_ENRICHMENTS:
        parameters["strict_evidence"] = strict_evidence
    return WorkflowOperation.create(kind, **parameters)


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
    steps = []
    if restore:
        output = report_root / "restore.json"
        steps.append(
            _step(
                "knowledge",
                selection,
                WorkflowStage.KNOWLEDGE_RESTORE,
                _transfer_operation(
                    WorkflowOperationKind.ATLASDATA_IMPORT_ENRICHMENTS,
                    manifest=manifest,
                    documents=keys,
                    output=output,
                    strict_evidence=strict_evidence,
                ),
                output,
            )
        )
    if adopt_run is not None:
        output = report_root / "adopt.json"
        steps.append(
            _step(
                "knowledge",
                selection,
                WorkflowStage.KNOWLEDGE_ADOPT,
                WorkflowOperation.create(
                    WorkflowOperationKind.DOCUMENT_ADOPT_QUALIFICATION,
                    run=str(adopt_run),
                    documents=keys,
                    available_only=True,
                    write=True,
                    output=str(output),
                ),
                output,
            )
        )
    if publish:
        output = report_root / "export.json"
        steps.append(
            _step(
                "knowledge",
                selection,
                WorkflowStage.KNOWLEDGE_PUBLISH,
                _transfer_operation(
                    WorkflowOperationKind.ATLASDATA_EXPORT_ENRICHMENTS,
                    manifest=manifest,
                    documents=keys,
                    output=output,
                ),
                output,
            )
        )
        output = report_root / "reimport.json"
        steps.append(
            _step(
                "knowledge",
                selection,
                WorkflowStage.KNOWLEDGE_RESTORE,
                _transfer_operation(
                    WorkflowOperationKind.ATLASDATA_IMPORT_ENRICHMENTS,
                    manifest=manifest,
                    documents=keys,
                    output=output,
                    strict_evidence=strict_evidence,
                ),
                output,
            )
        )
    output = report_root / "cbox.json"
    steps.append(
        _step(
            "knowledge",
            selection,
            WorkflowStage.CBOX_REPORT,
            WorkflowOperation.create(
                WorkflowOperationKind.DOCUMENT_CBOX_REPORT,
                documents=keys,
                available_only=True,
                knowledge_domain=knowledge_domain,
                output=str(output),
            ),
            output,
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
            output = root / "restore.json"
            steps.append(
                _step(
                    step.family,
                    step.document,
                    WorkflowStage.KNOWLEDGE_RESTORE,
                    _transfer_operation(
                        WorkflowOperationKind.ATLASDATA_IMPORT_ENRICHMENTS,
                        manifest=manifest,
                        documents=(step.document,),
                        output=output,
                        strict_evidence=strict_evidence,
                    ),
                    output,
                )
            )
        if step.stage is WorkflowStage.CONTEXT_ENRICHMENT or (
            step.stage is WorkflowStage.TAXONOMY and step.document not in contextual
        ):
            output = root / "cbox.json"
            steps.append(
                _step(
                    step.family,
                    step.document,
                    WorkflowStage.CBOX_REPORT,
                    WorkflowOperation.create(
                        WorkflowOperationKind.DOCUMENT_CBOX_REPORT,
                        documents=(step.document,),
                        knowledge_domain=knowledge_domain,
                        output=str(output),
                    ),
                    output,
                )
            )
    return replace(plan, steps=tuple(steps))
