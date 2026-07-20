from __future__ import annotations

import subprocess
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from standards_atlas.application.catalog import ContentSelection, StandardCatalog, StandardFamilyDefinition


class ArtifactPolicy(StrEnum):
    SOURCE = "source"
    DERIVED = "derived"
    REVIEW = "review"


class WorkflowStage(StrEnum):
    DOCLING = "docling"
    ATLASDATA = "atlasdata"
    IMPORT = "import"
    DERIVE = "derive"
    NORMALIZE = "normalize"
    REFERENCES = "references"
    ALIGN = "align"
    REVIEW = "review"
    ENRICH = "enrich"
    MARKDOWN = "markdown"
    DOORSTOP = "doorstop"


@dataclass(frozen=True)
class WorkflowStep:
    family: str
    document: str
    stage: WorkflowStage
    command: tuple[str, ...]
    artifact_policy: ArtifactPolicy
    manual_gate: bool = False


@dataclass(frozen=True)
class WorkflowPlan:
    families: tuple[str, ...]
    steps: tuple[WorkflowStep, ...]


@dataclass(frozen=True)
class WorkflowExecutionResult:
    executed_steps: tuple[WorkflowStep, ...]
    blocked_documents: tuple[str, ...]
    blocked_families: tuple[str, ...]

    @property
    def completed(self) -> bool:
        return not self.blocked_documents and not self.blocked_families


class CommandRunner(Protocol):
    def run(self, command: tuple[str, ...], cwd: Path) -> None: ...


class SubprocessCommandRunner:
    def run(self, command: tuple[str, ...], cwd: Path) -> None:
        subprocess.run(command, cwd=cwd, check=True)  # noqa: S603


class EndToEndWorkflowService:
    def plan(
        self,
        catalog: StandardCatalog,
        *,
        family_keys: tuple[str, ...],
        catalog_root: Path,
        force: bool = False,
    ) -> WorkflowPlan:
        steps: list[WorkflowStep] = []
        for key in family_keys:
            family = catalog.family(key)
            steps.extend(self._family_steps(family, catalog_root, force=force))
        return WorkflowPlan(families=family_keys, steps=tuple(steps))

    def execute(
        self,
        plan: WorkflowPlan,
        *,
        project_root: Path,
        runner: CommandRunner | None = None,
        continue_after_review: bool = False,
    ) -> WorkflowExecutionResult:
        command_runner = runner or SubprocessCommandRunner()
        executed: list[WorkflowStep] = []
        blocked_documents: set[str] = set()
        blocked_families: set[str] = set()

        for step in plan.steps:
            if not continue_after_review:
                if step.family in blocked_families:
                    continue
                if step.document in blocked_documents:
                    continue
                if step.stage in {WorkflowStage.MARKDOWN, WorkflowStage.DOORSTOP}:
                    family_documents = {
                        candidate.document
                        for candidate in plan.steps
                        if candidate.family == step.family
                        and candidate.stage == WorkflowStage.REVIEW
                    }
                    if family_documents & blocked_documents:
                        continue

            command_runner.run(step.command, project_root)
            executed.append(step)

            if step.manual_gate and not continue_after_review:
                if step.stage == WorkflowStage.ATLASDATA:
                    blocked_families.add(step.family)
                else:
                    blocked_documents.add(step.document)

        return WorkflowExecutionResult(
            executed_steps=tuple(executed),
            blocked_documents=tuple(sorted(blocked_documents)),
            blocked_families=tuple(sorted(blocked_families)),
        )

    def _family_steps(
        self,
        family: StandardFamilyDefinition,
        root: Path,
        *,
        force: bool,
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
                        "uv", "run", "standards-atlas", "docling", "convert",
                        "-d", key, pdf,
                    ),
                    ArtifactPolicy.SOURCE,
                )
            )

        if family.atlasdata is None:
            output = f"data/{family.key}"
            year = str(family.publication_year or 0)
            if family.source is not None:
                command = (
                    "uv", "run", "standards-atlas", "atlasdata", "onboard-docling",
                    f".atlas/docling/{family.key}/document.json", output,
                    "--name", family.name, "--year", year,
                )
            else:
                part_args = tuple(
                    value
                    for part in family.parts
                    for identifier, document_key in (
                        (part.part, part.key),
                        *((f"{part.part}-{supplement.supplement}", supplement.key)
                          for supplement in part.supplements),
                    )
                    for value in (
                        "--part",
                        f"{identifier}=.atlas/docling/{document_key}/document.json",
                    )
                )
                command = (
                    "uv", "run", "standards-atlas", "atlasdata", "onboard-docling-parts",
                    output, *part_args, "--name", family.name, "--year", year,
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
                            "uv", "run", "standards-atlas", "document", "derive-part",
                            family.key, part.part, "--key", part.key,
                            *( ("--title", part.title) if part.title else () ),
                        ),
                        ArtifactPolicy.DERIVED,
                    )
                )
                for supplement in part.supplements:
                    if supplement.atlasdata is not None:
                        supplement_atlas_path = str(
                            (root / supplement.atlasdata.path).resolve()
                        )
                        steps.append(
                            WorkflowStep(
                                family.key,
                                supplement.key,
                                WorkflowStage.IMPORT,
                                (
                                    "uv", "run", "standards-atlas", "document",
                                    "import", supplement_atlas_path,
                                ),
                                ArtifactPolicy.DERIVED,
                            )
                        )
                    else:
                        steps.append(
                            WorkflowStep(
                                family.key,
                                supplement.key,
                                WorkflowStage.DERIVE,
                                (
                                    "uv", "run", "standards-atlas", "document",
                                    "derive-part", family.key,
                                    f"{part.part}-{supplement.supplement}",
                                    "--key", supplement.key,
                                    *(
                                        ("--title", supplement.title)
                                        if supplement.title else ()
                                    ),
                                ),
                                ArtifactPolicy.DERIVED,
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
                                "uv", "run", "standards-atlas", "normalize", "run", key,
                                *self._content_selection_args(content_selection),
                            ),
                            policy=ArtifactPolicy.DERIVED,
                            force=force,
                            option="--overwrite",
                        ),
                        ArtifactPolicy.DERIVED,
                    ),
                    WorkflowStep(
                        family.key,
                        key,
                        WorkflowStage.REFERENCES,
                        ("uv", "run", "standards-atlas", "references", "detect", key),
                        ArtifactPolicy.DERIVED,
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
                    ),
                    WorkflowStep(
                        family.key,
                        key,
                        WorkflowStage.REVIEW,
                        ("uv", "run", "standards-atlas", "align", "review-export", key),
                        ArtifactPolicy.REVIEW,
                        True,
                    ),
                    WorkflowStep(
                        family.key,
                        key,
                        WorkflowStage.ENRICH,
                        ("uv", "run", "standards-atlas", "document", "enrich-content", key),
                        ArtifactPolicy.DERIVED,
                    ),
                ]
            )
        if family.exports.markdown:
            steps.append(
                WorkflowStep(
                    family.key,
                    family.key,
                    WorkflowStage.MARKDOWN,
                    (
                        "uv", "run", "standards-atlas", "document", "export", "markdown",
                        family.key,
                    ),
                    ArtifactPolicy.DERIVED,
                )
            )
        if family.exports.doorstop.enabled:
            steps.append(
                WorkflowStep(
                    family.key,
                    family.key,
                    WorkflowStage.DOORSTOP,
                    (
                        "uv", "run", "standards-atlas", "document", "export", "doorstop",
                        family.key,
                        "--digits",
                        str(family.exports.doorstop.identifier.width),
                    ),
                    ArtifactPolicy.DERIVED,
                )
            )
        return steps

    @staticmethod
    def _content_selection_args(
        selection: ContentSelection | None,
    ) -> tuple[str, ...]:
        if selection is None:
            return ()
        arguments: list[str] = []
        for page_range in selection.page_ranges:
            arguments.extend((
                "--page-range",
                f"{page_range.start}:{page_range.end or ''}",
            ))
        for page_range in selection.exclude_page_ranges:
            arguments.extend((
                "--exclude-page-range",
                f"{page_range.start}:{page_range.end or ''}",
            ))
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
