"""Post-Docling preparation through verified adoption and public companions."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from standards_atlas.application.catalog import StandardCatalog
from standards_atlas.application.catalog.atlasdata_binding import atlasdata_bindings
from standards_atlas.application.context.canonical_cbox import context_fingerprint
from standards_atlas.application.semantic_qualification.clause_access import SamplingStrategy
from standards_atlas.application.semantic_qualification.qualification_matrix import (
    QualificationMatrixManifest,
)
from standards_atlas.application.workflow.knowledge_plan import with_knowledge_restore
from standards_atlas.application.workflow.models import (
    ArtifactPolicy,
    WorkflowPlan,
    WorkflowStage,
    WorkflowStep,
)
from standards_atlas.application.workflow.qualification_plan import QualificationWorkflowPlanner


class EnrichmentsWorkflowPlanner:
    """Compose existing workflow/application boundaries; never shell out during planning.

    This explicit task authorizes adoption/publication. Documents, qualification
    and knowledge retain their existing opt-in and non-publication contracts.
    """

    def plan(
        self,
        catalog: StandardCatalog,
        *,
        family_keys: tuple[str, ...],
        catalog_root: Path,
        standards_manifest: Path,
        qualification_manifest: Path,
        corpus_count: int | None = None,
        limit: int | None = None,
        corpus_strategy: SamplingStrategy = SamplingStrategy.REPRESENTATIVE_STRATIFIED,
        corpus_seed: int = 0,
        knowledge_domain: str = "functional-safety",
        hierarchy_key: str | None = None,
        regenerate_docling: bool = False,
        overwrite: bool = False,
        fresh: bool = False,
        fresh_applicability_policy: bool = False,
        keep_stages: tuple[WorkflowStage, ...] = (),
        qualification_output: Path = Path(".atlas/data/evaluation/qualification"),
        corpus_output: Path = Path(".atlas/data/evaluation/corpora"),
        restore_enrichments: bool = False,
        strict_evidence: bool = False,
    ) -> WorkflowPlan:
        if len(family_keys) != len(set(family_keys)):
            raise ValueError("enrichments family selection must not contain duplicates")
        manifest = QualificationMatrixManifest.load(qualification_manifest)
        if not manifest.consensus.enabled or not manifest.applicability_decision_policy.enabled:
            raise ValueError(
                "enrichments requires final consensus and an enabled applicability decision "
                "policy for verified canonical adoption"
            )
        bindings = atlasdata_bindings(catalog, root=catalog_root)
        families = set(family_keys)
        if families - {binding.family_key for binding in bindings.values()}:
            raise ValueError("enrichments requires reviewed AtlasData bindings for every family")
        keys = tuple(sorted(key for key, value in bindings.items() if value.family_key in families))
        if not keys:
            raise ValueError("enrichments requires at least one physical document")
        # Isolate run/corpus state from standalone qualification and other selections.
        selection = context_fingerprint(
            {
                "documents": list(keys),
                "matrix_id": manifest.matrix_id,
                "corpus_count": corpus_count,
                "limit": limit,
                "strategy": corpus_strategy.value,
                "seed": corpus_seed,
                "knowledge_domain": knowledge_domain,
            }
        )[:12]
        suffix = Path("enrichments") / selection
        qualification_output = qualification_output / suffix
        corpus_output = corpus_output / suffix
        reports = Path("local/review/enrichments-workflow") / selection
        receipt = reports / "archive.json"
        selector = tuple(value for key in keys for value in ("--document", key))
        qualification = QualificationWorkflowPlanner().plan(
            catalog,
            family_keys=family_keys,
            catalog_root=catalog_root,
            manifest_path=qualification_manifest,
            corpus_count=corpus_count,
            limit=limit,
            corpus_strategy=corpus_strategy,
            corpus_seed=corpus_seed,
            knowledge_domain=knowledge_domain,
            hierarchy_key=hierarchy_key,
            regenerate_docling=regenerate_docling,
            overwrite=overwrite or regenerate_docling,
            fresh=fresh,
            fresh_applicability_policy=fresh_applicability_policy,
            keep_stages=keep_stages,
            qualification_output=qualification_output,
            corpus_output=corpus_output,
        )
        steps = []
        context_steps = []
        for step in qualification.steps:
            # Matrix/detail checkpoints must not be shared with standalone runs
            # or another document/sample selection using the same matrix ID.
            step = replace(
                step,
                output_paths=tuple(
                    path.replace(
                        ".atlas/work/workflow/qualification/",
                        f".atlas/work/workflow/enrichments/{selection}/qualification/",
                        1,
                    )
                    for path in step.output_paths
                ),
            )
            if step.stage is WorkflowStage.MARKDOWN:
                continue  # This task publishes companions, not separate document renderings.
            if step.stage is WorkflowStage.CONTEXT_ENRICHMENT:
                context_steps.append(replace(step, command=(*step.command, "--fail-on-failure")))
                continue
            if step.stage is WorkflowStage.CORPUS_BUILD:
                # Vocabulary/routing sees every selected document after normalization.
                steps.extend(context_steps)
                step = replace(step, command=(*step.command, *selector, "--source-only-context"))
            if step.stage is WorkflowStage.QUALIFICATION_ARCHIVE:
                step = replace(
                    step,
                    command=(*step.command, "--receipt", str(receipt)),
                    output_paths=(str(receipt),),
                )
            steps.append(step)
        plan = WorkflowPlan(
            families=qualification.document_plan.families,
            steps=tuple(steps),
            force=qualification.document_plan.force,
            kept_stages=qualification.document_plan.kept_stages,
            fresh_repetition_stages=qualification.fresh_repetition_stages,
        )
        if restore_enrichments:
            plan = with_knowledge_restore(
                plan,
                manifest=standards_manifest,
                strict_evidence=strict_evidence,
                knowledge_domain=knowledge_domain,
            )
        transfer = ("--manifest", str(standards_manifest), *selector, "--write")
        evidence = ("--strict-evidence",) if strict_evidence else ()
        tail = (
            (
                WorkflowStage.KNOWLEDGE_ADOPT,
                (
                    "document",
                    "adopt-qualification",
                    "--run-receipt",
                    str(receipt),
                    *selector,
                    "--available-only",
                    "--write",
                ),
                "adopt.json",
            ),
            (
                WorkflowStage.KNOWLEDGE_PUBLISH,
                ("atlasdata", "export-enrichments", *transfer),
                "export.json",
            ),
            (
                WorkflowStage.KNOWLEDGE_RESTORE,
                ("atlasdata", "import-enrichments", *transfer, *evidence),
                "reimport.json",
            ),
            (
                WorkflowStage.CBOX_REPORT,
                ("document", "cbox-report", *selector, "--knowledge-domain", knowledge_domain),
                "cbox.json",
            ),
        )
        return replace(
            plan,
            steps=(
                *plan.steps,
                *(
                    WorkflowStep(
                        "knowledge",
                        selection,
                        stage,
                        ("uv", "run", "standards-atlas", *tokens, "--output", str(reports / name)),
                        ArtifactPolicy.DERIVED,
                        output_paths=(
                            str(reports / name),
                            *(
                                tuple(str(bindings[key].enrichments_path) for key in keys)
                                if stage is WorkflowStage.KNOWLEDGE_PUBLISH
                                else ()
                            ),
                        ),
                    )
                    for stage, tokens, name in tail
                ),
            ),
        )
