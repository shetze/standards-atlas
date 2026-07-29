# ADR-0038: Package and install Doorstop publication templates

## Status

Accepted

## Context

Doorstop renders the structural HTML from Bottle templates during `doorstop publish`. Replacing the
`template` directory in an already published tree only changes static assets such as CSS; it cannot
replace the navigation markup already embedded in the generated HTML pages.

Standards Atlas needs reproducible publication layouts with a navigable, collapsible table of
contents in the left column. The selected layout must therefore be an input to the deterministic
publish step.

## Decision

Standards Atlas packages supported Doorstop templates below:

```text
src/standards_atlas/resources/doorstop_templates/
```

The initially supported template keys are:

- `atlas-clean`
- `technical-blueprint`
- `midnight-focus`

Each `doorstop_hierarchy` selects one template; `atlas-clean` is the default. Before invoking
Doorstop, the publish adapter identifies the single root Doorstop document and installs the selected
resource as its `template/` directory. Doorstop is then invoked with the packaged `doorstop.css`
template selector.

The generated output remains below:

```text
local/exports/doorstop/<hierarchy-key>/
```

## Consequences

- Template source files are versioned with Standards Atlas and included in installed wheels.
- HTML structure, JavaScript navigation and visual decoration are generated in one publish run.
- Workflow plans record the selected template explicitly in the publish command.
- Unknown templates and ambiguous Doorstop roots fail before publication.
- A style can be changed in the catalog without changing the workflow invocation.
