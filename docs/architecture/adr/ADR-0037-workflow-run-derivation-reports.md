# ADR-0037: Workflow run derivation reports

## Status

Accepted

## Context

Standards Atlas derives published and internal artifacts through a deterministic sequence of
catalog-driven workflow steps. The generated files are inspectable, but the workspace did not
previously contain a single immutable record that connected a completed run with its inputs,
commands, reused artifacts and resulting file hashes.

This makes it unnecessarily difficult to demonstrate which exact processing plan produced a
particular local publication or internal artifact set.

## Decision

Every successfully completed `workflow run` writes a run report below:

```text
.atlas/workflow/runs/<run-id>/
├── report.json
└── report.md
```

The JSON document is the canonical machine-readable report. The Markdown document is a derived
human-readable view of the same information.

A report records:

- Standards Atlas and Python versions;
- Git revision and dirty-worktree state when available;
- catalog path and SHA-256;
- selected families and optional Doorstop hierarchy;
- canonical workflow-plan SHA-256;
- every planned command and its artifact policy;
- whether each step was executed or reused;
- all files found below the declared step outputs;
- file sizes and SHA-256 digests.

Reports are created only when the workflow result is complete. A run paused at an AtlasData or
alignment review gate does not receive a completion report.

The run identifier combines the UTC completion time with the first eight characters of the plan
hash. Existing report directories are never overwritten.

## Consequences

Completed workflows have a durable and independently inspectable derivation record. Incremental
runs remain auditable because reused outputs are explicitly identified and hashed. The report can
support later qualification, provenance, reproducibility and comparison tooling.

The report demonstrates the exact observed inputs, plan and outputs. It does not by itself prove
that external tools such as Docling or Doorstop are deterministic; their versions and additional
environment details may be added to later schema versions.
