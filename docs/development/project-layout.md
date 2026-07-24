# Project layout

The package follows the dependency direction of hexagonal architecture.

- `src/standards_atlas/domain/`: canonical types, invariants, and value objects
- `src/standards_atlas/application/`: use cases, services, workflow planning, and ports
- `src/standards_atlas/adapters/`: Docling, AtlasData, filesystem, Markdown, Doorstop, catalog, and artefact repositories
- `src/standards_atlas/cli/`: Typer command surface and presentation
- `catalogs/`: declarative standard-family control plane
- `data/`: versioned public AtlasData baselines
- `.atlas/`: local private and derived artefacts
- `tests/`: unit, integration, regression, and corpus tests
- `docs/architecture/adr/`: architectural decisions

Dependencies point inward: adapters and CLI may depend on application and domain code; the domain must not import adapters.
