# R1 / review-handoff integration fix — validation record

## Source and diagnosis

Baseline: `standards-atlas-current-202609140528.zip`.

- Snapshot commit: `fd457c913afe085e8ffa4de5b9709845e15d3c72`.
- Snapshot SHA-256: `98fe6c04c5785cc88c0c2d75af19d11cb8bbf6edc178cf876aaa6bd22b9d8dc9`.

This snapshot contains both the R1 partial implementation and the Slice-4 review-handoff
implementation. However, `application/schema/baseline.py`, `docs/reference/schema-contracts.md`
and `CHANGELOG.md` are byte-identical to the earlier Slice-4 patch, replacing their R1 changes.
The partial request, observation and report code and the failing tests still contain R1.
An import-order cleanup in `partial_audit.py` is retained unchanged.

Consequently, the registry admits schema 1.0 while the R1 readers, writers and tests require
current-only 1.1. This produces all seven reported failures: three reader-window assertions,
three deprecation warnings raised as errors instead of unsupported-version errors, and one
report-envelope assertion reached too late because the version check admitted an obsolete report.

## Correction and boundaries

Only the `readable` tuples of `partial-request-plan`, `partial-semantic-observation` and
`partial-cascade-report` change from `("1.0", "1.1")` to `("1.1",)`.
The family set, current writer versions and artifact locations are unchanged. All 54 other
policies are identical to the supplied snapshot, including the Slice-4 review publication,
manifest, campaign, Workbench-evidence, archive and handoff contracts.

The schema reference and changelog merge both slices instead of replacing one with the other.
Existing R1 and handoff tests, warning filters and exception assertions are unmodified.
No compatibility fallback, migration, prompt, model invocation, human annotation, quality gate,
release rule, lockfile or productive artifact is changed. R2-R4 are not included.

## Reproducible checks

Before applying the correction, these four test functions (including their parametrizations)
reproduce the user's seven failing cases:

```bash
python -m pytest -q \
  tests/unit/application/semantic_qualification/test_partial_schema_refactoring.py::test_r1_families_have_no_legacy_reader_window \
  tests/unit/application/semantic_qualification/test_partial_schema_refactoring.py::test_resume_and_offline_revalidation_do_not_upgrade_old_artifacts \
  tests/unit/application/semantic_qualification/test_partial_schema_refactoring.py::test_bad_reports_block_replay_and_resume_without_mutation_or_model_calls \
  tests/unit/application/semantic_qualification/test_partial_slice51.py::test_planned_completion_is_not_measured_zero_and_obsolete_report_is_rejected
```

Result before the fix: **7 failed, 14 passed, 1 warning**.

After correction, both complete affected test modules pass:

```bash
python -m pytest -q \
  tests/unit/application/semantic_qualification/test_partial_schema_refactoring.py \
  tests/unit/application/semantic_qualification/test_partial_slice51.py
```

Result: **125 passed, no warnings**.

The full available suite was then run with `python -m pytest -q -ra`:

**2,967 passed, 14 skipped, 289 warnings; no failures** (203.33 seconds).

All remaining warnings belong to `partial-qualification-manifest` (264),
`partial-qualification-campaign` (20), `partial-review-publication` (1) and
`qualification-matrix-manifest` (4). None belong to the three R1 families.
Those other schema migrations remain scoped to R2/R3.

A fresh extraction of the supplied snapshot, with the patch ZIP applied, was tested with:

```bash
python -m pytest -q -ra \
  tests/architecture \
  tests/unit/application/schema \
  tests/unit/application/semantic_qualification/test_partial_schema_refactoring.py \
  tests/unit/application/semantic_qualification/test_partial_slice51.py \
  tests/unit/application/semantic_qualification/test_review_handoff.py
```

**215 passed, 89 warnings; no skips or failures** (40.45 seconds).
All 89 warnings concern the unchanged Handoff-side manifest/publication/campaign contracts.
The existing Handoff regressions run alongside the current-only partial regression tests.

Full-suite skips concern optional Docling, Hypothesis and MCP dependencies, two private
qualification fixtures and six opt-in Chromium tests. They are recorded separately rather
than counted as successfully exercised transports or external runtimes.

The test groups overlap and must not be added. Skips are not passes.

## Environment and limitations

Tests use Python 3.13.5 and pytest 9.0.2 with the installed local dependencies.
No productive corpus qualification or live Codex/LLM session was run.
Ruff is not installed; its installation failed because `pypi.org` could not be resolved.
Python syntax, line lengths, whitespace, registry preservation, documentation targets and ZIP
integrity are checked separately and are not represented as a successful Ruff run.

## Packaging

The patch contains four root-relative files: the registry, the merged schema reference and
changelog, and this validation record. It has no deletions. Apply it to the supplied combined
snapshot; do not reapply either older slice ZIP over its shared files.

All four ZIP members match the reviewed working tree. The 1,505 unaffected source files
match the original snapshot byte-for-byte in both the working and patched fresh trees.
The Handoff section of the schema reference is preserved verbatim. All four local Markdown
link targets in the changed documentation resolve. Python syntax, modified-file line lengths,
`git diff --check` and ZIP member integrity checks pass.

No tests or assertion patterns have been modified to obtain the passing results. The existing
regressions both reproduce the supplied failure and verify the correction.
