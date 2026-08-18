from pathlib import Path

from standards_atlas.adapters.catalog import YamlStandardCatalogReader
from standards_atlas.adapters.workflow import FileSystemWorkflowArtifactStore
from standards_atlas.application.workflow import (
    ArtifactPolicy,
    EndToEndWorkflowService,
    WorkflowExecutor,
    WorkflowPlan,
    WorkflowRecovery,
    WorkflowStage,
    WorkflowStep,
)


def test_plans_multipart_family_with_one_family_export() -> None:
    catalog = YamlStandardCatalogReader().read(Path("manifests/standards.yaml"))
    plan = EndToEndWorkflowService().plan(
        catalog, family_keys=("ISO26262",), catalog_root=Path.cwd()
    )
    assert sum(step.stage == WorkflowStage.DOCLING for step in plan.steps) == 11
    assert sum(step.stage == WorkflowStage.MARKDOWN for step in plan.steps) == 1
    assert sum(step.stage == WorkflowStage.DOORSTOP for step in plan.steps) == 1
    assert any(step.manual_gate for step in plan.steps)


def test_multipart_family_without_atlasdata_uses_docling_onboarding() -> None:
    catalog = YamlStandardCatalogReader().read(Path("manifests/standards.yaml"))
    plan = EndToEndWorkflowService().plan(
        catalog, family_keys=("IEC11889",), catalog_root=Path.cwd()
    )

    docling_steps = [step for step in plan.steps if step.stage == WorkflowStage.DOCLING]
    assert [step.document for step in docling_steps] == [
        "IEC11889-1",
        "IEC11889-2",
    ]

    onboarding_steps = [step for step in plan.steps if step.stage == WorkflowStage.ATLASDATA]
    assert len(onboarding_steps) == 1
    onboarding = onboarding_steps[0]
    assert onboarding.command[:5] == (
        "uv",
        "run",
        "standards-atlas",
        "atlasdata",
        "onboard-docling-parts",
    )
    assert "1=.atlas/docling/IEC11889-1/document.json" in onboarding.command
    assert "2=.atlas/docling/IEC11889-2/document.json" in onboarding.command
    assert onboarding.command[5] == "local/proposed/IEC11889"
    assert onboarding.manual_gate is True
    assert plan.steps[-1] == onboarding


def test_missing_atlasdata_stops_at_onboarding_gate() -> None:
    catalog = YamlStandardCatalogReader().read(Path("manifests/standards.yaml"))
    plan = EndToEndWorkflowService().plan(
        catalog, family_keys=("IEC29100",), catalog_root=Path.cwd()
    )
    assert plan.steps[-1].stage == WorkflowStage.ATLASDATA
    assert plan.steps[-1].manual_gate is True


def test_references_detect_uses_no_override_option() -> None:
    catalog = YamlStandardCatalogReader().read(Path("manifests/standards.yaml"))
    plan = EndToEndWorkflowService().plan(
        catalog, family_keys=("EN50716",), catalog_root=Path.cwd()
    )

    reference_steps = [step for step in plan.steps if step.stage == WorkflowStage.REFERENCES]

    assert reference_steps
    assert all("--override" not in step.command for step in reference_steps)
    assert all("--overwrite" not in step.command for step in reference_steps)
    assert all(
        step.command[-3:] == ("references", "detect", step.document) for step in reference_steps
    )


def test_align_review_export_uses_no_overwrite_option() -> None:
    catalog = YamlStandardCatalogReader().read(Path("manifests/standards.yaml"))
    plan = EndToEndWorkflowService().plan(
        catalog, family_keys=("EN50716",), catalog_root=Path.cwd()
    )

    review_steps = [step for step in plan.steps if step.stage == WorkflowStage.REVIEW]

    assert review_steps
    assert all("--overwrite" not in step.command for step in review_steps)
    assert all("--override" not in step.command for step in review_steps)
    assert all(
        step.command[-3:] == ("align", "review-export", step.document) for step in review_steps
    )


class RecordingRunner:
    def __init__(self) -> None:
        self.commands: list[tuple[str, ...]] = []

    def run(self, command: tuple[str, ...], cwd: Path) -> None:
        self.commands.append(command)


def test_execute_collects_all_review_gates_instead_of_stopping_at_first(tmp_path: Path) -> None:
    catalog = YamlStandardCatalogReader().read(Path("manifests/standards.yaml"))
    plan = EndToEndWorkflowService().plan(
        catalog,
        family_keys=("EN50716", "EN50657"),
        catalog_root=Path.cwd(),
    )
    runner = RecordingRunner()

    result = EndToEndWorkflowService(
        executor=WorkflowExecutor(WorkflowRecovery(FileSystemWorkflowArtifactStore()))
    ).execute(
        plan,
        project_root=tmp_path,
        runner=runner,
    )

    assert result.completed is False
    assert result.blocked_documents == ("EN50657", "EN50716")
    assert sum(step.stage == WorkflowStage.REVIEW for step in result.executed_steps) == 2
    assert all(step.stage != WorkflowStage.ENRICH for step in result.executed_steps)
    assert all(
        step.stage not in {WorkflowStage.MARKDOWN, WorkflowStage.DOORSTOP}
        for step in result.executed_steps
    )


def test_continue_after_review_executes_remaining_pipeline(tmp_path: Path) -> None:
    catalog = YamlStandardCatalogReader().read(Path("manifests/standards.yaml"))
    plan = EndToEndWorkflowService().plan(
        catalog,
        family_keys=("EN50716",),
        catalog_root=Path.cwd(),
    )
    runner = RecordingRunner()

    result = EndToEndWorkflowService(
        executor=WorkflowExecutor(WorkflowRecovery(FileSystemWorkflowArtifactStore()))
    ).execute(
        plan,
        project_root=tmp_path,
        runner=runner,
        continue_after_review=True,
    )

    assert result.completed is True
    assert any(step.stage == WorkflowStage.ENRICH for step in result.executed_steps)
    assert any(step.stage == WorkflowStage.MARKDOWN for step in result.executed_steps)
    assert any(step.stage == WorkflowStage.DOORSTOP for step in result.executed_steps)


def test_enrich_content_uses_no_overwrite_option() -> None:
    catalog = YamlStandardCatalogReader().read(Path("manifests/standards.yaml"))
    plan = EndToEndWorkflowService().plan(
        catalog, family_keys=("EN50716",), catalog_root=Path.cwd()
    )

    enrich_steps = [step for step in plan.steps if step.stage == WorkflowStage.ENRICH]

    assert enrich_steps
    assert all("--overwrite" not in step.command for step in enrich_steps)
    assert all("--override" not in step.command for step in enrich_steps)
    assert all(
        step.command[-3:] == ("document", "enrich-content", step.document) for step in enrich_steps
    )


def test_force_only_replaces_supported_derived_artifacts() -> None:
    catalog = YamlStandardCatalogReader().read(Path("manifests/standards.yaml"))
    plan = EndToEndWorkflowService().plan(
        catalog,
        family_keys=("EN50716",),
        catalog_root=Path.cwd(),
        force=True,
    )

    replaceable = {WorkflowStage.NORMALIZE, WorkflowStage.ALIGN}
    for step in plan.steps:
        if step.stage in replaceable:
            assert step.artifact_policy is ArtifactPolicy.DERIVED
            assert "--overwrite" in step.command
        else:
            assert "--overwrite" not in step.command
            assert "--override" not in step.command


def test_force_never_overwrites_docling_source_artifacts() -> None:
    catalog = YamlStandardCatalogReader().read(Path("manifests/standards.yaml"))
    plan = EndToEndWorkflowService().plan(
        catalog,
        family_keys=("EN50716",),
        catalog_root=Path.cwd(),
        force=True,
    )

    docling_steps = [step for step in plan.steps if step.stage == WorkflowStage.DOCLING]

    assert docling_steps
    assert all(step.artifact_policy is ArtifactPolicy.SOURCE for step in docling_steps)
    assert all("--overwrite" not in step.command for step in docling_steps)


def test_force_adds_overwrite_to_atlasdata_onboarding_only() -> None:
    catalog = YamlStandardCatalogReader().read(Path("manifests/standards.yaml"))
    plan = EndToEndWorkflowService().plan(
        catalog,
        family_keys=("IEC29100",),
        catalog_root=Path.cwd(),
        force=True,
    )

    onboarding = [step for step in plan.steps if step.stage == WorkflowStage.ATLASDATA]
    assert len(onboarding) == 1
    assert onboarding[0].command[-1] == "--overwrite"


def test_normal_plan_contains_no_unnecessary_overwrite_options() -> None:
    catalog = YamlStandardCatalogReader().read(Path("manifests/standards.yaml"))
    plan = EndToEndWorkflowService().plan(
        catalog,
        family_keys=("EN50716", "IEC29100"),
        catalog_root=Path.cwd(),
    )

    assert all("--overwrite" not in step.command for step in plan.steps)
    assert all("--override" not in step.command for step in plan.steps)


def test_review_exports_are_protected_artifacts() -> None:
    catalog = YamlStandardCatalogReader().read(Path("manifests/standards.yaml"))
    plan = EndToEndWorkflowService().plan(
        catalog,
        family_keys=("EN50716",),
        catalog_root=Path.cwd(),
        force=True,
    )

    review_steps = [step for step in plan.steps if step.stage == WorkflowStage.REVIEW]

    assert review_steps
    assert all(step.artifact_policy is ArtifactPolicy.REVIEW for step in review_steps)
    assert all("--overwrite" not in step.command for step in review_steps)


def test_iec61508_normalization_uses_catalog_page_selection() -> None:
    catalog = YamlStandardCatalogReader().read(Path("manifests/standards.yaml"))
    plan = EndToEndWorkflowService().plan(
        catalog, family_keys=("IEC61508",), catalog_root=Path.cwd()
    )
    normalize_steps = {
        step.document: step.command for step in plan.steps if step.stage == WorkflowStage.NORMALIZE
    }

    assert normalize_steps["IEC61508-0"][-2:] == (
        "--page-list",
        "7,9,11,13,15,17,19,21,23,25,27,29,31,33,35",
    )
    assert normalize_steps["IEC61508-1"][-2:] == ("--page-range", "1:63")
    assert normalize_steps["IEC61508-2"][-2:] == ("--page-range", "1:91")
    assert normalize_steps["IEC61508-3"][-2:] == ("--page-range", "1:113")
    assert normalize_steps["IEC61508-3-1"][-2:] == ("--page-range", "8:12")
    assert normalize_steps["IEC61508-4"][-2:] == ("--page-range", "1:34")
    assert normalize_steps["IEC61508-5"][-2:] == ("--page-range", "1:48")
    assert normalize_steps["IEC61508-6"][-2:] == ("--page-range", "1:113")
    assert normalize_steps["IEC61508-7"][-2:] == ("--page-range", "1:138")


def test_catalog_source_paths_are_below_local_sources() -> None:
    catalog = YamlStandardCatalogReader().read(Path("manifests/standards.yaml"))
    for family in catalog.families:
        sources = (
            [family.source] if family.source is not None else [part.source for part in family.parts]
        )
        assert all(str(source.pdf).startswith("local/sources/standards/") for source in sources)


def test_content_selection_emits_page_list_and_exclusions() -> None:
    from standards_atlas.application.catalog import ContentSelection, PageRange

    args = EndToEndWorkflowService._content_selection_args(
        ContentSelection(
            page_ranges=(PageRange(start=1, end=20),),
            exclude_page_ranges=(PageRange(start=2, end=4),),
            page_list="1,3,5,11-13,15",
        )
    )
    assert args == (
        "--page-range",
        "1:20",
        "--exclude-page-range",
        "2:4",
        "--page-list",
        "1,3,5,11-13,15",
    )


def test_iec61508_supplement_is_planned_as_own_document() -> None:
    catalog = YamlStandardCatalogReader().read(Path("manifests/standards.yaml"))
    plan = EndToEndWorkflowService().plan(
        catalog,
        family_keys=("IEC61508",),
        catalog_root=Path.cwd(),
    )

    supplement_steps = [step for step in plan.steps if step.document == "IEC61508-3-1"]

    assert supplement_steps
    assert {step.stage for step in supplement_steps} >= {
        WorkflowStage.DOCLING,
        WorkflowStage.NORMALIZE,
        WorkflowStage.REFERENCES,
        WorkflowStage.ALIGN,
        WorkflowStage.REVIEW,
        WorkflowStage.ENRICH,
    }
    assert any("iec61508-3-1{ed1.0}en.pdf" in argument for argument in supplement_steps[0].command)


def test_parts_are_derived_but_supplement_with_own_atlasdata_is_imported() -> None:
    catalog = YamlStandardCatalogReader().read(Path("manifests/standards.yaml"))
    plan = EndToEndWorkflowService().plan(
        catalog,
        family_keys=("IEC61508",),
        catalog_root=Path.cwd(),
    )

    derive_steps = [step for step in plan.steps if step.stage == WorkflowStage.DERIVE]
    derive_commands = {step.document: step.command for step in derive_steps}

    assert derive_commands["IEC61508-3"][:7] == (
        "uv",
        "run",
        "standards-atlas",
        "document",
        "derive-part",
        "IEC61508",
        "3",
    )
    assert "IEC61508-3-1" not in derive_commands

    supplement_import = next(
        step
        for step in plan.steps
        if step.document == "IEC61508-3-1" and step.stage == WorkflowStage.IMPORT
    )
    assert supplement_import.command[:5] == ("uv", "run", "standards-atlas", "document", "import")
    assert supplement_import.command[-1].endswith("data/IEC61508-3-1")


def test_supplement_is_imported_before_reference_detection() -> None:
    catalog = YamlStandardCatalogReader().read(Path("manifests/standards.yaml"))
    plan = EndToEndWorkflowService().plan(
        catalog,
        family_keys=("IEC61508",),
        catalog_root=Path.cwd(),
    )

    import_index = next(
        index
        for index, step in enumerate(plan.steps)
        if step.document == "IEC61508-3-1" and step.stage == WorkflowStage.IMPORT
    )
    references_index = next(
        index
        for index, step in enumerate(plan.steps)
        if step.document == "IEC61508-3-1" and step.stage == WorkflowStage.REFERENCES
    )

    assert import_index < references_index


def test_multi_part_family_is_composed_before_exports() -> None:
    catalog = YamlStandardCatalogReader().read(Path("manifests/standards.yaml"))
    plan = EndToEndWorkflowService().plan(
        catalog, family_keys=("IEC61508",), catalog_root=Path.cwd()
    )

    compose = [step for step in plan.steps if step.stage == WorkflowStage.COMPOSE]
    assert len(compose) == 1
    assert compose[0].document == "IEC61508"
    assert compose[0].command[:6] == (
        "uv",
        "run",
        "standards-atlas",
        "document",
        "compose-family",
        "IEC61508",
    )
    export_indices = [
        index
        for index, step in enumerate(plan.steps)
        if step.stage in {WorkflowStage.MARKDOWN, WorkflowStage.DOORSTOP}
    ]
    assert export_indices
    assert plan.steps.index(compose[0]) < min(export_indices)


def test_doorstop_parent_prefers_specific_catalog_relationships() -> None:
    catalog = YamlStandardCatalogReader().read(Path("manifests/standards.yaml"))
    plan = EndToEndWorkflowService().plan(
        catalog,
        family_keys=("IEC61508", "EN50128", "EN50657", "EN50716"),
        catalog_root=Path.cwd(),
    )

    expected_parents = {
        "EN50128": "IEC61508",
        "EN50657": "EN50128",
        "EN50716": "EN50657",
    }
    for family, expected_parent in expected_parents.items():
        export = next(
            step
            for step in plan.steps
            if step.stage == WorkflowStage.DOORSTOP and step.family == family
        )
        parent_index = export.command.index("--parent")
        assert export.command[parent_index + 1] == expected_parent


def _write_alignment_statistics(
    root: Path,
    document: str,
    *,
    missing: int = 0,
    conflicting: int = 0,
) -> None:
    path = root / ".atlas" / "alignments" / document / "alignment.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '{"metadata":{"statistics":{"missing":'
        + str(missing)
        + ',"conflicting":'
        + str(conflicting)
        + "}}}\n",
        encoding="utf-8",
    )


def test_clean_alignment_exports_review_and_continues_automatically(tmp_path: Path) -> None:
    from standards_atlas.application.workflow import WorkflowPlan, WorkflowStep

    _write_alignment_statistics(tmp_path, "CLEAN")
    plan = WorkflowPlan(
        families=("FAMILY",),
        steps=(
            WorkflowStep(
                "FAMILY",
                "CLEAN",
                WorkflowStage.REVIEW,
                ("review-export", "CLEAN"),
                ArtifactPolicy.REVIEW,
                True,
                output_paths=(
                    ".atlas/alignments/CLEAN/review.generated.md",
                    ".atlas/alignments/CLEAN/review.edited.md",
                ),
            ),
            WorkflowStep(
                "FAMILY",
                "CLEAN",
                WorkflowStage.ENRICH,
                ("enrich", "CLEAN"),
                ArtifactPolicy.DERIVED,
            ),
        ),
    )
    runner = RecordingRunner()

    result = EndToEndWorkflowService(
        executor=WorkflowExecutor(WorkflowRecovery(FileSystemWorkflowArtifactStore()))
    ).execute(plan, project_root=tmp_path, runner=runner)

    assert result.completed is True
    assert result.blocked_documents == ()
    assert runner.commands == [("review-export", "CLEAN"), ("enrich", "CLEAN")]


def test_only_missing_or_conflicting_documents_block_their_pipeline(tmp_path: Path) -> None:
    from standards_atlas.application.workflow import WorkflowPlan, WorkflowStep

    _write_alignment_statistics(tmp_path, "CLEAN")
    _write_alignment_statistics(tmp_path, "MISSING", missing=2)
    _write_alignment_statistics(tmp_path, "CONFLICT", conflicting=1)
    steps = []
    for document in ("CLEAN", "MISSING", "CONFLICT"):
        steps.extend(
            (
                WorkflowStep(
                    "FAMILY",
                    document,
                    WorkflowStage.REVIEW,
                    ("review-export", document),
                    ArtifactPolicy.REVIEW,
                    True,
                ),
                WorkflowStep(
                    "FAMILY",
                    document,
                    WorkflowStage.ENRICH,
                    ("enrich", document),
                    ArtifactPolicy.DERIVED,
                ),
            )
        )
    plan = WorkflowPlan(families=("FAMILY",), steps=tuple(steps))
    runner = RecordingRunner()

    result = EndToEndWorkflowService(
        executor=WorkflowExecutor(WorkflowRecovery(FileSystemWorkflowArtifactStore()))
    ).execute(plan, project_root=tmp_path, runner=runner)

    assert result.blocked_documents == ("CONFLICT", "MISSING")
    assert ("enrich", "CLEAN") in runner.commands
    assert ("enrich", "MISSING") not in runner.commands
    assert ("enrich", "CONFLICT") not in runner.commands
    assert sum(command[0] == "review-export" for command in runner.commands) == 3


def test_existing_step_outputs_are_not_generated_again(tmp_path: Path) -> None:
    from standards_atlas.application.workflow import WorkflowPlan, WorkflowStep

    output = tmp_path / ".atlas" / "normalized" / "DOC" / "document.json"
    output.parent.mkdir(parents=True)
    output.write_text("existing\n", encoding="utf-8")
    step = WorkflowStep(
        "FAMILY",
        "DOC",
        WorkflowStage.NORMALIZE,
        ("normalize", "DOC"),
        ArtifactPolicy.DERIVED,
        output_paths=(".atlas/normalized/DOC/document.json",),
    )
    runner = RecordingRunner()

    result = EndToEndWorkflowService(
        executor=WorkflowExecutor(WorkflowRecovery(FileSystemWorkflowArtifactStore()))
    ).execute(
        WorkflowPlan(families=("FAMILY",), steps=(step,)),
        project_root=tmp_path,
        runner=runner,
    )

    assert result.completed is True
    assert result.executed_steps == ()
    assert runner.commands == []
    assert output.read_text(encoding="utf-8") == "existing\n"


def test_force_removes_existing_outputs_before_regeneration(tmp_path: Path) -> None:
    from standards_atlas.application.workflow import WorkflowPlan, WorkflowStep

    output = tmp_path / ".atlas" / "normalized" / "DOC" / "document.json"
    output.parent.mkdir(parents=True)
    output.write_text("old\n", encoding="utf-8")

    class ReplacingRunner:
        def __init__(self) -> None:
            self.called = False

        def run(self, command: tuple[str, ...], cwd: Path) -> None:
            self.called = True
            assert not output.exists()
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text("new\n", encoding="utf-8")

    step = WorkflowStep(
        "FAMILY",
        "DOC",
        WorkflowStage.NORMALIZE,
        ("normalize", "DOC"),
        ArtifactPolicy.DERIVED,
        output_paths=(".atlas/normalized/DOC/document.json",),
    )
    runner = ReplacingRunner()

    result = EndToEndWorkflowService(
        executor=WorkflowExecutor(WorkflowRecovery(FileSystemWorkflowArtifactStore()))
    ).execute(
        WorkflowPlan(families=("FAMILY",), steps=(step,), force=True),
        project_root=tmp_path,
        runner=runner,
    )

    assert result.completed is True
    assert runner.called is True
    assert output.read_text(encoding="utf-8") == "new\n"


def test_overwrite_can_keep_existing_docling_output(tmp_path: Path) -> None:
    from standards_atlas.application.workflow import WorkflowPlan, WorkflowStep

    docling_output = tmp_path / ".atlas" / "docling" / "DOC" / "document.json"
    docling_output.parent.mkdir(parents=True)
    docling_output.write_text("existing docling\n", encoding="utf-8")
    source = tmp_path / "DOC.pdf"
    source.write_bytes(b"pdf")

    # Use a non-Docling step here to isolate the stage-preservation policy from
    # Docling repository metadata validation.
    step = WorkflowStep(
        "FAMILY",
        "DOC",
        WorkflowStage.DOCLING,
        ("noop",),
        ArtifactPolicy.DERIVED,
        output_paths=(".atlas/docling/DOC/document.json",),
    )
    runner = RecordingRunner()

    result = EndToEndWorkflowService(
        executor=WorkflowExecutor(WorkflowRecovery(FileSystemWorkflowArtifactStore()))
    ).execute(
        WorkflowPlan(
            families=("FAMILY",),
            steps=(step,),
            force=True,
            kept_stages=(WorkflowStage.DOCLING,),
        ),
        project_root=tmp_path,
        runner=runner,
    )

    assert result.executed_steps == ()
    assert runner.commands == []
    assert docling_output.read_text(encoding="utf-8") == "existing docling\n"


def test_force_resets_editable_review_exports() -> None:
    catalog = YamlStandardCatalogReader().read(Path("manifests/standards.yaml"))
    plan = EndToEndWorkflowService().plan(
        catalog,
        family_keys=("EN50716",),
        catalog_root=Path.cwd(),
        force=True,
    )

    review = next(step for step in plan.steps if step.stage == WorkflowStage.REVIEW)

    assert review.command[-1] == "--reset-edited"
    assert review.output_paths == (
        ".atlas/alignments/EN50716/review.generated.md",
        ".atlas/alignments/EN50716/review.edited.md",
    )


def test_functional_safety_hierarchy_includes_iso26262_and_publishes_last() -> None:
    catalog = YamlStandardCatalogReader().read(Path("manifests/standards.yaml"))
    hierarchy = catalog.doorstop_hierarchy("functional-safety")

    assert hierarchy.root == "IEC61508"
    assert "ISO26262" in hierarchy.families

    plan = EndToEndWorkflowService().plan(
        catalog,
        family_keys=hierarchy.families,
        catalog_root=Path.cwd(),
        hierarchy_key=hierarchy.key,
    )

    assert plan.steps[-1].stage == WorkflowStage.DOORSTOP_PUBLISH
    assert plan.steps[-1].command[-2:] == ("--template", "atlas-clean")
    assert plan.steps[-1].output_paths == ("local/exports/doorstop/functional-safety",)
    doorstop_steps = [step for step in plan.steps if step.stage == WorkflowStage.DOORSTOP]
    assert doorstop_steps
    assert all(
        step.output_paths[0].startswith(".atlas/doorstop/functional-safety/")
        for step in doorstop_steps
    )
    markdown_steps = [step for step in plan.steps if step.stage == WorkflowStage.MARKDOWN]
    assert markdown_steps
    assert all(
        step.output_globs[0].startswith("local/exports/markdown/functional-safety/")
        for step in markdown_steps
    )


def test_incomplete_docling_extraction_is_repaired_with_overwrite(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    source.write_bytes(b"%PDF-1.4\n")
    metadata = tmp_path / ".atlas" / "docling" / "TEST" / "conversion.json"
    metadata.parent.mkdir(parents=True)
    metadata.write_text("{}\n", encoding="utf-8")
    step = WorkflowStep(
        family="TEST",
        document="TEST",
        stage=WorkflowStage.DOCLING,
        command=(
            "uv",
            "run",
            "standards-atlas",
            "docling",
            "convert",
            "-d",
            "TEST",
            str(source),
        ),
        artifact_policy=ArtifactPolicy.SOURCE,
        output_paths=(
            ".atlas/docling/TEST/document.json",
            ".atlas/docling/TEST/conversion.json",
        ),
    )
    runner = RecordingRunner()

    service = EndToEndWorkflowService(
        executor=WorkflowExecutor(WorkflowRecovery(FileSystemWorkflowArtifactStore()))
    )
    result = service.execute(
        WorkflowPlan(families=("TEST",), steps=(step,)),
        project_root=tmp_path,
        runner=runner,
        continue_after_review=True,
    )

    assert result.completed is True
    assert runner.commands == [(*step.command, "--overwrite")]


def test_current_docling_extraction_is_reused(tmp_path: Path) -> None:
    from standards_atlas.adapters.docling.repository import sha256_file

    source = tmp_path / "source.pdf"
    source.write_bytes(b"%PDF-1.4\n")
    root = tmp_path / ".atlas" / "docling" / "TEST"
    root.mkdir(parents=True)
    (root / "document.json").write_text("{}\n", encoding="utf-8")
    (root / "conversion.json").write_text(
        '{"source_sha256": "' + sha256_file(source) + '"}\n',
        encoding="utf-8",
    )
    step = WorkflowStep(
        family="TEST",
        document="TEST",
        stage=WorkflowStage.DOCLING,
        command=(
            "uv",
            "run",
            "standards-atlas",
            "docling",
            "convert",
            "-d",
            "TEST",
            str(source),
        ),
        artifact_policy=ArtifactPolicy.SOURCE,
        output_paths=(
            ".atlas/docling/TEST/document.json",
            ".atlas/docling/TEST/conversion.json",
        ),
    )
    runner = RecordingRunner()

    service = EndToEndWorkflowService(
        executor=WorkflowExecutor(WorkflowRecovery(FileSystemWorkflowArtifactStore()))
    )
    result = service.execute(
        WorkflowPlan(families=("TEST",), steps=(step,)),
        project_root=tmp_path,
        runner=runner,
        continue_after_review=True,
    )

    assert result.completed is True
    assert runner.commands == []
    assert result.executed_steps == ()
