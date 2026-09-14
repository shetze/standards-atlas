"""Render typed workflow operations as Standards Atlas CLI invocations."""

from __future__ import annotations

from dataclasses import dataclass

from standards_atlas.application.workflow.models import (
    WorkflowOperation,
    WorkflowOperationKind,
)


@dataclass(frozen=True)
class _Binding:
    parameter: str
    token: str | None = None
    repeated: bool = False
    flag: bool = False


@dataclass(frozen=True)
class _Spec:
    path: tuple[str, ...]
    bindings: tuple[_Binding, ...]


def _p(name: str) -> _Binding:
    return _Binding(name)


def _o(name: str, token: str | None = None, *, repeated: bool = False) -> _Binding:
    return _Binding(name, token or f"--{name.replace('_', '-')}", repeated=repeated)


def _f(name: str, token: str | None = None) -> _Binding:
    return _Binding(name, token or f"--{name.replace('_', '-')}", flag=True)


_SPECS: dict[WorkflowOperationKind, _Spec] = {
    WorkflowOperationKind.DOORSTOP_PUBLISH: _Spec(
        ("doorstop", "publish"), (_p("hierarchy"), _o("template"))
    ),
    WorkflowOperationKind.DOCLING_CONVERT: _Spec(
        ("docling", "convert"), (_o("document", "-d"), _p("source"), _f("overwrite"))
    ),
    WorkflowOperationKind.ATLASDATA_ONBOARD_DOCLING: _Spec(
        ("atlasdata", "onboard-docling"),
        (_p("source"), _p("output"), _o("name"), _o("year"), _f("overwrite")),
    ),
    WorkflowOperationKind.ATLASDATA_ONBOARD_DOCLING_PARTS: _Spec(
        ("atlasdata", "onboard-docling-parts"),
        (
            _p("output"),
            _o("parts", "--part", repeated=True),
            _o("name"),
            _o("year"),
            _f("overwrite"),
        ),
    ),
    WorkflowOperationKind.DOCUMENT_IMPORT: _Spec(
        ("document", "import"), (_p("source"), _o("workspace"))
    ),
    WorkflowOperationKind.DOCUMENT_DERIVE_PART: _Spec(
        ("document", "derive-part"),
        (_p("family"), _p("part"), _o("key"), _o("source_workspace"), _o("title")),
    ),
    WorkflowOperationKind.NORMALIZE_DOCUMENT: _Spec(
        ("normalize", "run"),
        (
            _p("document"),
            _o("page_ranges", "--page-range", repeated=True),
            _o("exclude_page_ranges", "--exclude-page-range", repeated=True),
            _o("page_list"),
            _f("overwrite"),
        ),
    ),
    WorkflowOperationKind.REFERENCES_DETECT: _Spec(("references", "detect"), (_p("document"),)),
    WorkflowOperationKind.ALIGN_DOCUMENT: _Spec(
        ("align", "run"), (_p("document"), _f("overwrite"))
    ),
    WorkflowOperationKind.ALIGN_REVIEW_EXPORT: _Spec(
        ("align", "review-export"), (_p("document"), _f("reset_edited"))
    ),
    WorkflowOperationKind.DOCUMENT_ENRICH_CONTENT: _Spec(
        ("document", "enrich-content"), (_p("document"),)
    ),
    WorkflowOperationKind.DOCUMENT_CLASSIFY_TAXONOMY: _Spec(
        ("document", "classify-taxonomy"), (_p("document"),)
    ),
    WorkflowOperationKind.DOCUMENT_ENRICH_CONTEXT: _Spec(
        ("document", "enrich-context"),
        (_p("document"), _o("context_config"), _f("fail_on_failure"), _f("fresh")),
    ),
    WorkflowOperationKind.DOCUMENT_EXPORT_MARKDOWN: _Spec(
        ("document", "export", "markdown"),
        (
            _p("document"),
            _o("target"),
            _o("parts", "--part", repeated=True),
            _o("title"),
        ),
    ),
    WorkflowOperationKind.DOCUMENT_EXPORT_DOORSTOP: _Spec(
        ("document", "export", "doorstop"),
        (
            _p("document"),
            _o("digits"),
            _o("parent"),
            _o("target"),
            _o("parts", "--part", repeated=True),
            _o("title"),
            _f("skip_git_init", "--no-init-git"),
            _f("skip_validation", "--no-validate"),
        ),
    ),
    WorkflowOperationKind.EVALUATION_CORPUS_BUILD: _Spec(
        ("evaluation", "corpus-build"),
        (
            _o("task"),
            _o("version"),
            _o("corpus_id"),
            _o("knowledge_domain"),
            _o("count"),
            _f("all_clauses"),
            _o("strategy"),
            _o("seed"),
            _o("output"),
            _o("documents", "--document", repeated=True),
            _f("source_only_context"),
        ),
    ),
    WorkflowOperationKind.EVALUATION_QUALIFICATION_MATRIX: _Spec(
        ("evaluation", "qualification-matrix"),
        (
            _o("manifest"),
            _o("output"),
            _f("continue_on_matrix_failure", "--no-fail-on-matrix-failure"),
            _o("limit"),
            _o("corpus_root"),
            _f("skip_archive_creation", "--no-create-archive"),
            _f("overwrite"),
            _f("fresh"),
        ),
    ),
    WorkflowOperationKind.EVALUATION_APPLICABILITY_POLICY: _Spec(
        ("evaluation", "applicability-policy-run"),
        (
            _o("manifest"),
            _o("run"),
            _o("corpus_root"),
            _o("output_directory"),
            _f("fresh"),
            _o("qualification_mode"),
        ),
    ),
    WorkflowOperationKind.EVALUATION_APPLICABILITY_DETAIL: _Spec(
        ("evaluation", "applicability-detail-enrich"),
        (_o("manifest"), _o("run"), _o("corpus_root"), _f("fresh")),
    ),
    WorkflowOperationKind.EVALUATION_SEMANTIC_EXTRACTION: _Spec(
        ("evaluation", "semantic-extraction-qualification"),
        (
            _o("manifest"),
            _o("output"),
            _f("continue_on_qualification_failure", "--no-fail-on-qualification-failure"),
            _o("limit"),
            _f("fresh"),
        ),
    ),
    WorkflowOperationKind.EVALUATION_QUALIFICATION_ARCHIVE: _Spec(
        ("evaluation", "qualification-archive"),
        (
            _o("manifest"),
            _o("output"),
            _o("corpus_root"),
            _o("limit"),
            _o("receipt"),
        ),
    ),
    WorkflowOperationKind.PARTIAL_REVIEW_CHECK_HANDOFF: _Spec(
        ("evaluation", "partial-review-check-handoff"), (_o("bundle"),)
    ),
    WorkflowOperationKind.PARTIAL_QUALIFICATION_PREPARE: _Spec(
        ("evaluation", "partial-qualification-prepare"),
        (_o("manifest"), _o("output"), _f("reuse_frozen")),
    ),
    WorkflowOperationKind.PARTIAL_QUALIFICATION_RUN: _Spec(
        ("evaluation", "partial-qualification-run"), (_o("campaign"), _f("execute"))
    ),
    WorkflowOperationKind.PARTIAL_QUALIFICATION_EVALUATE: _Spec(
        ("evaluation", "partial-qualification-evaluate"),
        (_o("campaign"), _o("archive_output")),
    ),
    WorkflowOperationKind.WORKFLOW_ARCHIVE_BASELINE: _Spec(
        ("workflow", "archive-baseline"),
        (
            _o("phase"),
            _o("selection"),
            _o("manifests", "--manifest", repeated=True),
            _o("reports_root"),
            _o("output"),
            _o("documents", "--document", repeated=True),
            _o("corpus_count"),
            _o("limit"),
            _f("strict_context"),
            _f("verify_existing"),
        ),
    ),
    WorkflowOperationKind.DOCUMENT_ADOPT_QUALIFICATION: _Spec(
        ("document", "adopt-qualification"),
        (
            _o("run"),
            _o("run_receipt"),
            _o("documents", "--document", repeated=True),
            _f("available_only"),
            _f("write"),
            _o("output"),
        ),
    ),
    WorkflowOperationKind.ATLASDATA_EXPORT_ENRICHMENTS: _Spec(
        ("atlasdata", "export-enrichments"),
        (
            _o("manifest"),
            _o("documents", "--document", repeated=True),
            _f("available_only"),
            _f("write"),
            _o("output"),
        ),
    ),
    WorkflowOperationKind.ATLASDATA_IMPORT_ENRICHMENTS: _Spec(
        ("atlasdata", "import-enrichments"),
        (
            _o("manifest"),
            _o("documents", "--document", repeated=True),
            _f("available_only"),
            _f("write"),
            _f("strict_evidence"),
            _o("output"),
        ),
    ),
    WorkflowOperationKind.DOCUMENT_CBOX_REPORT: _Spec(
        ("document", "cbox-report"),
        (
            _o("documents", "--document", repeated=True),
            _f("available_only"),
            _o("knowledge_domain"),
            _o("output"),
        ),
    ),
}


class CliWorkflowOperationRenderer:
    """Translate the application operation contract to the current Typer CLI surface."""

    prefix = ("uv", "run", "standards-atlas")

    def render(self, operation: WorkflowOperation) -> tuple[str, ...]:
        spec = _SPECS[operation.kind]
        known = {binding.parameter for binding in spec.bindings}
        supplied = {name for name, _ in operation.parameters}
        unknown = supplied - known
        if unknown:
            raise ValueError(
                f"unsupported parameters for {operation.kind.value}: {', '.join(sorted(unknown))}"
            )
        command = [*self.prefix, *spec.path]
        for binding in spec.bindings:
            value = operation.parameter(binding.parameter)
            if binding.flag:
                if value is True:
                    command.append(binding.token or "")
                continue
            if value is None:
                continue
            if binding.repeated:
                values = value if isinstance(value, tuple) else (str(value),)
                for item in values:
                    command.extend((binding.token or "", str(item)))
                continue
            if binding.token is None:
                command.append(str(value))
            else:
                command.extend((binding.token, str(value)))
        return tuple(command)
