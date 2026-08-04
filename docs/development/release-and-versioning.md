# Release and versioning

This document defines the maintainer workflow for versioning Standards Atlas, communicating compatibility changes, and collecting the evidence required for a release.

## Version scope

The project version identifies the released Python package and CLI. It does not imply that every persisted artifact, catalog, evaluation task, taxonomy, prompt, or export format has the same schema version. Those contracts carry independent version or identity information where required.

Use semantic versioning as a communication model:

- **Major** — intentionally incompatible public interfaces or architectural migration baseline.
- **Minor** — backward-compatible functionality, new commands, adapters, or optional schema capabilities.
- **Patch** — compatible fixes and documentation corrections without a new capability contract.

Before a stable `1.0` baseline, minor releases may contain breaking changes. Such changes still require explicit changelog and migration notes; pre-release status is not permission for silent breakage.

## Independently versioned contracts

The following may evolve independently from the package version:

- normalized-document and canonical artifact schemas;
- catalogs and authored configuration;
- taxonomies and structural-classification schemes;
- evaluation tasks, corpora, prompts, and result schemas;
- MCP protocol configuration and exposed tool contracts;
- publication projections and templates.

A release must record which contract versions it reads and writes. The package version alone is not sufficient evidence of artifact compatibility.

## Release readiness

A release candidate should satisfy the following gates:

1. Unit, integration, property, and relevant qualification tests pass.
2. Ruff and other configured static checks pass.
3. CLI help and documented examples match the implementation.
4. Persisted-contract changes have migration or regeneration guidance.
5. Architecture changes have an ADR or an updated current architecture document.
6. Generated SVGs match changed editable diagram sources.
7. The changelog names user-visible changes, breaking changes, and known limitations.
8. Local/private test data is absent from the release artifact.
9. Package contents and entry points are tested from a built distribution, not only from the source tree.

Qualification evidence is proportional to impact. A documentation-only patch does not require a model qualification run. A change to normalization, construction, retrieval, classification, or evaluation logic requires the relevant regression or golden-corpus evidence.

## Release procedure

### Prepare

- choose the release version;
- update `pyproject.toml` and any authoritative version source;
- move unreleased changelog entries into the release section with a date;
- review compatibility implications using the [evolution policy](../architecture/evolution-and-compatibility.md);
- verify that roadmap claims do not present unimplemented work as released functionality.

### Verify

Run the repository-defined checks, normally including:

```bash
uv run ruff check .
uv run pytest
uv build
```

Run additional workflow, export, MCP, LLM, or qualification checks when the changed areas require them. Record commands and relevant result artifacts in the release evidence or pull request.

### Package review

Inspect the source distribution and wheel for:

- expected package modules and templates;
- no `local/`, copyrighted source documents, credentials, model caches, or generated private evaluation data;
- required licenses, README, and metadata;
- working CLI entry point after installation in a clean environment.

### Tag and publish

Create an annotated version tag only from the reviewed release commit. Publish through the project’s approved release channel. Signing and registry procedures depend on the deployment environment and should be automated when a release pipeline is introduced.

### Post-release

- verify installation and `standards-atlas --version` from the published artifact;
- preserve the release evidence and qualification references;
- open follow-up issues for explicitly deferred limitations;
- start a new unreleased changelog section.

## Changelog policy

The changelog is user-oriented, not a commit log. Group entries by impact such as Added, Changed, Fixed, Deprecated, Removed, Security, and Documentation. Include:

- commands or behavior users must change;
- persisted artifacts requiring migration or regeneration;
- changed defaults;
- security-relevant changes;
- important qualification limitations.

Internal refactoring belongs in the changelog only when it affects extension points, deployment, diagnostics, or supported interfaces.

## Breaking-change note template

A breaking change should state:

```text
Affected surface:
Previous behavior or contract:
New behavior or contract:
Reason:
Migration or regeneration steps:
Detection and failure mode:
Last compatible release:
```

## Release evidence

Release evidence may include CI runs, test reports, golden-corpus reports, qualification matrices, artifact schema fixtures, and manual review records. Evidence that contains licensed source text or local annotations remains in the private workspace and is referenced by digest or controlled location rather than copied into public release notes.

## Related documentation

- [Evolution and compatibility](../architecture/evolution-and-compatibility.md)
- [Testing and qualification](testing-and-qualification.md)
- [Documentation style guide](documentation-style-guide.md)
- [Security and copyright](../architecture/security-and-copyright.md)
- [Changelog](../../CHANGELOG.md)
