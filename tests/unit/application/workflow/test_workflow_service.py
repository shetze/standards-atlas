from pathlib import Path

from standards_atlas.adapters.catalog import YamlStandardCatalogReader
from standards_atlas.application.workflow import (
    ArtifactPolicy,
    EndToEndWorkflowService,
    WorkflowStage,
)


def test_plans_multipart_family_with_one_family_export() -> None:
    catalog = YamlStandardCatalogReader().read(Path("catalogs/standards.yaml"))
    plan = EndToEndWorkflowService().plan(
        catalog, family_keys=("ISO26262",), catalog_root=Path.cwd()
    )
    assert sum(step.stage == WorkflowStage.DOCLING for step in plan.steps) == 11
    assert sum(step.stage == WorkflowStage.MARKDOWN for step in plan.steps) == 1
    assert sum(step.stage == WorkflowStage.DOORSTOP for step in plan.steps) == 1
    assert any(step.manual_gate for step in plan.steps)


def test_missing_atlasdata_stops_at_onboarding_gate() -> None:
    catalog = YamlStandardCatalogReader().read(Path("catalogs/standards.yaml"))
    plan = EndToEndWorkflowService().plan(
        catalog, family_keys=("IEC29100",), catalog_root=Path.cwd()
    )
    assert plan.steps[-1].stage == WorkflowStage.ATLASDATA
    assert plan.steps[-1].manual_gate is True


def test_references_detect_uses_no_override_option() -> None:
    catalog = YamlStandardCatalogReader().read(Path("catalogs/standards.yaml"))
    plan = EndToEndWorkflowService().plan(
        catalog, family_keys=("EN50716",), catalog_root=Path.cwd()
    )

    reference_steps = [
        step for step in plan.steps if step.stage == WorkflowStage.REFERENCES
    ]

    assert reference_steps
    assert all("--override" not in step.command for step in reference_steps)
    assert all("--overwrite" not in step.command for step in reference_steps)
    assert all(
        step.command[-3:] == ("references", "detect", step.document)
        for step in reference_steps
    )


def test_align_review_export_uses_no_overwrite_option() -> None:
    catalog = YamlStandardCatalogReader().read(Path("catalogs/standards.yaml"))
    plan = EndToEndWorkflowService().plan(
        catalog, family_keys=("EN50716",), catalog_root=Path.cwd()
    )

    review_steps = [
        step for step in plan.steps if step.stage == WorkflowStage.REVIEW
    ]

    assert review_steps
    assert all("--overwrite" not in step.command for step in review_steps)
    assert all("--override" not in step.command for step in review_steps)
    assert all(
        step.command[-3:] == ("align", "review-export", step.document)
        for step in review_steps
    )


class RecordingRunner:
    def __init__(self) -> None:
        self.commands: list[tuple[str, ...]] = []

    def run(self, command: tuple[str, ...], cwd: Path) -> None:
        self.commands.append(command)


def test_execute_collects_all_review_gates_instead_of_stopping_at_first() -> None:
    catalog = YamlStandardCatalogReader().read(Path("catalogs/standards.yaml"))
    plan = EndToEndWorkflowService().plan(
        catalog,
        family_keys=("EN50716", "EN50657"),
        catalog_root=Path.cwd(),
    )
    runner = RecordingRunner()

    result = EndToEndWorkflowService().execute(
        plan,
        project_root=Path.cwd(),
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


def test_continue_after_review_executes_remaining_pipeline() -> None:
    catalog = YamlStandardCatalogReader().read(Path("catalogs/standards.yaml"))
    plan = EndToEndWorkflowService().plan(
        catalog,
        family_keys=("EN50716",),
        catalog_root=Path.cwd(),
    )
    runner = RecordingRunner()

    result = EndToEndWorkflowService().execute(
        plan,
        project_root=Path.cwd(),
        runner=runner,
        continue_after_review=True,
    )

    assert result.completed is True
    assert any(step.stage == WorkflowStage.ENRICH for step in result.executed_steps)
    assert any(step.stage == WorkflowStage.MARKDOWN for step in result.executed_steps)
    assert any(step.stage == WorkflowStage.DOORSTOP for step in result.executed_steps)


def test_enrich_content_uses_no_overwrite_option() -> None:
    catalog = YamlStandardCatalogReader().read(Path("catalogs/standards.yaml"))
    plan = EndToEndWorkflowService().plan(
        catalog, family_keys=("EN50716",), catalog_root=Path.cwd()
    )

    enrich_steps = [step for step in plan.steps if step.stage == WorkflowStage.ENRICH]

    assert enrich_steps
    assert all("--overwrite" not in step.command for step in enrich_steps)
    assert all("--override" not in step.command for step in enrich_steps)
    assert all(
        step.command[-3:] == ("document", "enrich-content", step.document)
        for step in enrich_steps
    )


def test_force_only_replaces_supported_derived_artifacts() -> None:
    catalog = YamlStandardCatalogReader().read(Path("catalogs/standards.yaml"))
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
    catalog = YamlStandardCatalogReader().read(Path("catalogs/standards.yaml"))
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
    catalog = YamlStandardCatalogReader().read(Path("catalogs/standards.yaml"))
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
    catalog = YamlStandardCatalogReader().read(Path("catalogs/standards.yaml"))
    plan = EndToEndWorkflowService().plan(
        catalog,
        family_keys=("EN50716", "IEC29100"),
        catalog_root=Path.cwd(),
    )

    assert all("--overwrite" not in step.command for step in plan.steps)
    assert all("--override" not in step.command for step in plan.steps)


def test_review_exports_are_protected_artifacts() -> None:
    catalog = YamlStandardCatalogReader().read(Path("catalogs/standards.yaml"))
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
    catalog = YamlStandardCatalogReader().read(Path("catalogs/standards.yaml"))
    plan = EndToEndWorkflowService().plan(
        catalog, family_keys=("IEC61508",), catalog_root=Path.cwd()
    )
    normalize_steps = {
        step.document: step.command
        for step in plan.steps
        if step.stage == WorkflowStage.NORMALIZE
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


def test_catalog_source_paths_are_below_workspace_standards() -> None:
    catalog = YamlStandardCatalogReader().read(Path("catalogs/standards.yaml"))
    for family in catalog.families:
        sources = (
            [family.source]
            if family.source is not None
            else [part.source for part in family.parts]
        )
        assert all(
            str(source.pdf).startswith(".atlas/standards/")
            for source in sources
        )


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
        "--page-range", "1:20",
        "--exclude-page-range", "2:4",
        "--page-list", "1,3,5,11-13,15",
    )


def test_iec61508_supplement_is_planned_as_own_document() -> None:
    catalog = YamlStandardCatalogReader().read(Path("catalogs/standards.yaml"))
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
    catalog = YamlStandardCatalogReader().read(Path("catalogs/standards.yaml"))
    plan = EndToEndWorkflowService().plan(
        catalog,
        family_keys=("IEC61508",),
        catalog_root=Path.cwd(),
    )

    derive_steps = [step for step in plan.steps if step.stage == WorkflowStage.DERIVE]
    derive_commands = {step.document: step.command for step in derive_steps}

    assert derive_commands["IEC61508-3"][:7] == (
        "uv", "run", "standards-atlas", "document", "derive-part", "IEC61508", "3"
    )
    assert "IEC61508-3-1" not in derive_commands

    supplement_import = next(
        step for step in plan.steps
        if step.document == "IEC61508-3-1" and step.stage == WorkflowStage.IMPORT
    )
    assert supplement_import.command[:5] == (
        "uv", "run", "standards-atlas", "document", "import"
    )
    assert supplement_import.command[-1].endswith("data/IEC61508-3-1")

def test_supplement_is_imported_before_reference_detection() -> None:
    catalog = YamlStandardCatalogReader().read(Path("catalogs/standards.yaml"))
    plan = EndToEndWorkflowService().plan(
        catalog,
        family_keys=("IEC61508",),
        catalog_root=Path.cwd(),
    )

    import_index = next(
        index for index, step in enumerate(plan.steps)
        if step.document == "IEC61508-3-1" and step.stage == WorkflowStage.IMPORT
    )
    references_index = next(
        index for index, step in enumerate(plan.steps)
        if step.document == "IEC61508-3-1" and step.stage == WorkflowStage.REFERENCES
    )

    assert import_index < references_index
