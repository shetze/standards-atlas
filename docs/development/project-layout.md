# Project layout

The package follows the dependency direction of hexagonal architecture. The directory
layout expresses architectural ownership; it is not merely a grouping convention.

```text
src/standards_atlas/
├── domain/
│   └── model/
├── application/
│   ├── alignment/
│   ├── analysis/
│   ├── catalog/
│   ├── commands/
│   ├── evaluation/
│   ├── model/
│   ├── normalization/
│   ├── ports/
│   ├── qualification/
│   ├── repositories/
│   ├── review/
│   ├── semantic_qualification/
│   ├── services/
│   ├── transformations/
│   └── workflow/
├── adapters/
├── cli/
├── resources/
└── shared/
```

## Package responsibilities

- `domain/` contains canonical aggregates, value objects, invariants, and domain
  concepts. It must not import application, CLI, adapters, or infrastructure.
- `application/` contains use cases and application-owned abstractions. Focused
  capability packages own their respective orchestration and models.
- `application/workflow/` owns workflow planning, execution, recovery, reporting, and
  the small end-to-end composition facade.
- `application/normalization/` owns the ordered normalization pipeline and its
  transformation contracts.
- `application/evaluation/` owns provider-neutral prompt, model, dataset, metric, and
  reporting infrastructure.
- `application/semantic_qualification/` owns standards-specific corpus construction,
  semantic proposals, consensus, review, references, and qualification matrices. It may
  depend on generic evaluation, but generic evaluation must not depend on it.
- `application/qualification/` owns deterministic extraction and normalization
  qualification against checked-in golden corpora. This is distinct from semantic model
  qualification.
- `application/services/` contains focused use cases that have not been promoted to a
  dedicated capability package. Compatibility exports below this tree are noncanonical.
- `application/ports/` and `application/repositories/` declare application needs. They
  must not expose concrete adapter types.
- `adapters/` contains Docling, filesystem, AtlasData, Markdown, Doorstop, LLM, MCP, and
  other technology integrations implementing application ports.
- `cli/apps.py` defines the Typer application tree, `cli/commands/` owns command
  implementations, and `cli/composition.py` wires concrete adapters.
- `resources/` contains packaged taxonomies, task schemas, prompts, corpora metadata,
  and Doorstop templates; it does not own runtime orchestration.
- `shared/` is reserved for narrowly scoped technical utilities that are independent of
  domain and application policy.

## Repository-level directories

- `catalogs/`: declarative standard-family control plane
- `cfg/`: checked-in runtime and evaluation configuration
- `data/`: versioned public AtlasData baselines and publishable data
- `local/` and `.atlas/`: private, generated, or workspace-specific artifacts
- `tests/`: unit, integration, contract, property, architecture, and corpus tests
- `docs/architecture/adr/`: architectural decisions
- `legacy/`: retained historical implementation that is outside the active package

Dependencies point inward: adapters and CLI may depend on application and domain code;
the application layer may depend on the domain; the domain must not import outward. New
code must use canonical capability packages rather than compatibility re-exports.
