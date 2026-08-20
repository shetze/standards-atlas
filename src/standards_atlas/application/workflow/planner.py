"""Pure workflow planning without filesystem or process side effects."""

from __future__ import annotations

from pathlib import Path

from standards_atlas.application.catalog import (
    ContentSelection,
    StandardCatalog,
    StandardFamilyDefinition,
)
from standards_atlas.application.workflow.models import (
    ArtifactPolicy,
    WorkflowPlan,
    WorkflowStage,
    WorkflowStep,
)


class WorkflowPlanner:
    def plan(
        self,
        catalog: StandardCatalog,
        *,
        family_keys: tuple[str, ...],
        catalog_root: Path,
        force: bool = False,
        keep_stages: tuple[WorkflowStage, ...] = (),
        hierarchy_key: str | None = None,
    ) -> WorkflowPlan:
        steps: list[WorkflowStep] = []
        hierarchy = catalog.doorstop_hierarchy(hierarchy_key) if hierarchy_key else None
        if hierarchy is not None and tuple(family_keys) != hierarchy.families:
            raise ValueError(
                "family_keys must match the selected Doorstop hierarchy in declared order"
            )
        selected_families = set(family_keys)
        for key in family_keys:
            family = catalog.family(key)
            steps.extend(
                self._family_steps(
                    family,
                    catalog_root,
                    force=force,
                    selected_families=selected_families,
                    hierarchy_key=hierarchy_key,
                )
            )
        if hierarchy is not None:
            steps.append(
                WorkflowStep(
                    hierarchy.key,
                    hierarchy.key,
                    WorkflowStage.DOORSTOP_PUBLISH,
                    (
                        "uv",
                        "run",
                        "standards-atlas",
                        "doorstop",
                        "publish",
                        hierarchy.key,
                        "--template",
                        hierarchy.template,
                    ),
                    ArtifactPolicy.DERIVED,
                    output_paths=(f"local/exports/doorstop/{hierarchy.key}",),
                )
            )
        return WorkflowPlan(
            families=family_keys,
            steps=tuple(steps),
            force=force,
            kept_stages=keep_stages,
        )

    def _family_steps(
        self,
        family: StandardFamilyDefinition,
        root: Path,
        *,
        force: bool,
        selected_families: set[str],
        hierarchy_key: str | None,
    ) -> list[WorkflowStep]:
        documents = (
            [(family.key, family.source.pdf, family.content_selection)]
            if family.source is not None
            else [
                document
                for part in family.parts
                for document in (
                    (
                        part.key,
                        part.source.pdf,
                        part.content_selection or family.content_selection,
                    ),
                    *(
                        (
                            supplement.key,
                            supplement.source.pdf,
                            supplement.content_selection
                            or part.content_selection
                            or family.content_selection,
                        )
                        for supplement in part.supplements
                    ),
                )
            ]
        )
        steps: list[WorkflowStep] = []
        for key, relative_pdf, _ in documents:
            pdf = str((root / relative_pdf).resolve())
            steps.append(
                WorkflowStep(
                    family.key,
                    key,
                    WorkflowStage.DOCLING,
                    (
                        "uv",
                        "run",
                        "standards-atlas",
                        "docling",
                        "convert",
                        "-d",
                        key,
                        pdf,
                    ),
                    ArtifactPolicy.SOURCE,
                    output_paths=(
                        f".atlas/data/docling/{key}/document.json",
                        f".atlas/data/docling/{key}/conversion.json",
                    ),
                )
            )

        if family.atlasdata is None:
            output = f"local/proposed/{family.key}"
            year = str(family.publication_year or 0)
            if family.source is not None:
                command = (
                    "uv",
                    "run",
                    "standards-atlas",
                    "atlasdata",
                    "onboard-docling",
                    f".atlas/data/docling/{family.key}/document.json",
                    output,
                    "--name",
                    family.name,
                    "--year",
                    year,
                )
            else:
                part_args = tuple(
                    value
                    for part in family.parts
                    for identifier, document_key in (
                        (part.part, part.key),
                        *(
                            (f"{part.part}-{supplement.supplement}", supplement.key)
                            for supplement in part.supplements
                        ),
                    )
                    for value in (
                        "--part",
                        f"{identifier}=.atlas/data/docling/{document_key}/document.json",
                    )
                )
                command = (
                    "uv",
                    "run",
                    "standards-atlas",
                    "atlasdata",
                    "onboard-docling-parts",
                    output,
                    *part_args,
                    "--name",
                    family.name,
                    "--year",
                    year,
                )
            steps.append(
                WorkflowStep(
                    family.key,
                    family.key,
                    WorkflowStage.ATLASDATA,
                    self._apply_force_policy(
                        command,
                        policy=ArtifactPolicy.DERIVED,
                        force=force,
                        option="--overwrite",
                    ),
                    ArtifactPolicy.DERIVED,
                    True,
                    output_paths=(f"local/proposed/{family.key}",),
                )
            )
            return steps

        atlas_path = str((root / family.atlasdata.path).resolve())
        steps.append(
            WorkflowStep(
                family.key,
                family.key,
                WorkflowStage.IMPORT,
                ("uv", "run", "standards-atlas", "document", "import", atlas_path),
                ArtifactPolicy.DERIVED,
                output_paths=(f".atlas/data/documents/{family.key}.json",),
            )
        )

        if family.source is None:
            for part in family.parts:
                steps.append(
                    WorkflowStep(
                        family.key,
                        part.key,
                        WorkflowStage.DERIVE,
                        (
                            "uv",
                            "run",
                            "standards-atlas",
                            "document",
                            "derive-part",
                            family.key,
                            part.part,
                            "--key",
                            part.key,
                            *(("--title", part.title) if part.title else ()),
                        ),
                        ArtifactPolicy.DERIVED,
                        output_paths=(f".atlas/data/documents/{part.key}.json",),
                    )
                )
                for supplement in part.supplements:
                    if supplement.atlasdata is not None:
                        supplement_atlas_path = str((root / supplement.atlasdata.path).resolve())
                        steps.append(
                            WorkflowStep(
                                family.key,
                                supplement.key,
                                WorkflowStage.IMPORT,
                                (
                                    "uv",
                                    "run",
                                    "standards-atlas",
                                    "document",
                                    "import",
                                    supplement_atlas_path,
                                ),
                                ArtifactPolicy.DERIVED,
                                output_paths=(f".atlas/data/documents/{supplement.key}.json",),
                            )
                        )
                    else:
                        steps.append(
                            WorkflowStep(
                                family.key,
                                supplement.key,
                                WorkflowStage.DERIVE,
                                (
                                    "uv",
                                    "run",
                                    "standards-atlas",
                                    "document",
                                    "derive-part",
                                    family.key,
                                    f"{part.part}-{supplement.supplement}",
                                    "--key",
                                    supplement.key,
                                    *(("--title", supplement.title) if supplement.title else ()),
                                ),
                                ArtifactPolicy.DERIVED,
                                output_paths=(f".atlas/data/documents/{supplement.key}.json",),
                            )
                        )

        for key, _, content_selection in documents:
            steps.extend(
                [
                    WorkflowStep(
                        family.key,
                        key,
                        WorkflowStage.NORMALIZE,
                        self._apply_force_policy(
                            (
                                "uv",
                                "run",
                                "standards-atlas",
                                "normalize",
                                "run",
                                key,
                                *self._content_selection_args(content_selection),
                            ),
                            policy=ArtifactPolicy.DERIVED,
                            force=force,
                            option="--overwrite",
                        ),
                        ArtifactPolicy.DERIVED,
                        output_paths=(
                            f".atlas/data/normalized/{key}/document.json",
                            f".atlas/data/normalized/{key}/run.json",
                        ),
                    ),
                    WorkflowStep(
                        family.key,
                        key,
                        WorkflowStage.REFERENCES,
                        ("uv", "run", "standards-atlas", "references", "detect", key),
                        ArtifactPolicy.DERIVED,
                        output_paths=(f".atlas/data/reference-candidates/{key}/document.json",),
                    ),
                    WorkflowStep(
                        family.key,
                        key,
                        WorkflowStage.ALIGN,
                        self._apply_force_policy(
                            ("uv", "run", "standards-atlas", "align", "run", key),
                            policy=ArtifactPolicy.DERIVED,
                            force=force,
                            option="--overwrite",
                        ),
                        ArtifactPolicy.DERIVED,
                        output_paths=(f".atlas/data/alignments/{key}/alignment.json",),
                    ),
                    WorkflowStep(
                        family.key,
                        key,
                        WorkflowStage.REVIEW,
                        (
                            "uv",
                            "run",
                            "standards-atlas",
                            "align",
                            "review-export",
                            key,
                            *(("--reset-edited",) if force else ()),
                        ),
                        ArtifactPolicy.REVIEW,
                        True,
                        output_paths=(
                            f"local/review/alignment/{key}/review.generated.md",
                            f"local/review/alignment/{key}/review.edited.md",
                        ),
                    ),
                    WorkflowStep(
                        family.key,
                        key,
                        WorkflowStage.ENRICH,
                        ("uv", "run", "standards-atlas", "document", "enrich-content", key),
                        ArtifactPolicy.DERIVED,
                        output_paths=(f".atlas/work/workflow/enrich/{key}.complete",),
                    ),
                    WorkflowStep(
                        family.key,
                        key,
                        WorkflowStage.TAXONOMY,
                        ("uv", "run", "standards-atlas", "document", "classify-taxonomy", key),
                        ArtifactPolicy.DERIVED,
                        output_paths=(f".atlas/work/workflow/taxonomy/{key}.complete",),
                    ),
                    WorkflowStep(
                        family.key,
                        key,
                        WorkflowStage.ONTOLOGY,
                        (
                            "uv",
                            "run",
                            "standards-atlas",
                            "document",
                            "classify-ontology",
                            key,
                            "--llm-config",
                            "cfg/llm.yaml",
                        ),
                        ArtifactPolicy.DERIVED,
                        output_paths=(f".atlas/work/workflow/ontology/{key}.complete",),
                    ),
                ]
            )
        if family.source is None:
            part_keys = tuple(key for key, _, _ in documents)
            steps.append(
                WorkflowStep(
                    family.key,
                    family.key,
                    WorkflowStage.COMPOSE,
                    (
                        "uv",
                        "run",
                        "standards-atlas",
                        "document",
                        "compose-family",
                        family.key,
                        *(value for key in part_keys for value in ("--part", key)),
                    ),
                    ArtifactPolicy.DERIVED,
                    output_paths=(f".atlas/work/workflow/compose/{family.key}.complete",),
                )
            )
        if family.exports.markdown:
            steps.append(
                WorkflowStep(
                    family.key,
                    family.key,
                    WorkflowStage.MARKDOWN,
                    (
                        "uv",
                        "run",
                        "standards-atlas",
                        "document",
                        "export",
                        "markdown",
                        family.key,
                        "--target",
                        f"local/exports/markdown/{hierarchy_key or family.key}",
                    ),
                    ArtifactPolicy.DERIVED,
                    output_globs=(
                        f"local/exports/markdown/{hierarchy_key or family.key}/{family.key}*.md",
                    ),
                )
            )
        if family.exports.doorstop.enabled:
            doorstop_parent = self._doorstop_parent(family, selected_families)
            steps.append(
                WorkflowStep(
                    family.key,
                    family.key,
                    WorkflowStage.DOORSTOP,
                    (
                        "uv",
                        "run",
                        "standards-atlas",
                        "document",
                        "export",
                        "doorstop",
                        family.key,
                        "--digits",
                        str(family.exports.doorstop.identifier.width),
                        *(("--parent", doorstop_parent) if doorstop_parent else ()),
                        "--target",
                        f".atlas/work/doorstop/{hierarchy_key or family.key}/{family.key}",
                        "--no-init-git",
                    ),
                    ArtifactPolicy.DERIVED,
                    output_paths=(
                        f".atlas/work/doorstop/{hierarchy_key or family.key}/{family.key}",
                    ),
                )
            )
        return steps

    @staticmethod
    def _doorstop_parent(
        family: StandardFamilyDefinition,
        selected_families: set[str],
    ) -> str | None:
        structural_relations = (
            "supersedes",
            "consolidates",
            "depends-on",
            "derived-from",
            "specializes",
            "adapts",
            "sector-specialization-of",
        )
        for relation_type in structural_relations:
            for relation in family.relations:
                if relation.type.value == relation_type and relation.target in selected_families:
                    return "".join(
                        character for character in relation.target.upper() if character.isalnum()
                    )
        return None

    @staticmethod
    def _content_selection_args(
        selection: ContentSelection | None,
    ) -> tuple[str, ...]:
        if selection is None:
            return ()
        arguments: list[str] = []
        for page_range in selection.page_ranges:
            arguments.extend(
                (
                    "--page-range",
                    f"{page_range.start}:{page_range.end or ''}",
                )
            )
        for page_range in selection.exclude_page_ranges:
            arguments.extend(
                (
                    "--exclude-page-range",
                    f"{page_range.start}:{page_range.end or ''}",
                )
            )
        if selection.page_list:
            arguments.extend(("--page-list", selection.page_list))
        return tuple(arguments)

    @staticmethod
    def _apply_force_policy(
        command: tuple[str, ...],
        *,
        policy: ArtifactPolicy,
        force: bool,
        option: str | None = None,
    ) -> tuple[str, ...]:
        if not force or policy is not ArtifactPolicy.DERIVED or option is None:
            return command
        return (*command, option)
