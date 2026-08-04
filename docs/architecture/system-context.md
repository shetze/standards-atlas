# System context

![System context](diagrams/svg/system-context.svg)

The context diagram identifies actors, external systems, and protected-content boundaries. Internal application services and repositories are intentionally delegated to the component, class, pipeline, and deployment views.

Standards Atlas sits between controlled source publications and downstream engineering ecosystems.

Inputs include private PDFs, public AtlasData baselines, YAML catalogs, and human review decisions. The platform produces canonical engineering documents and projections such as Markdown or Doorstop. Source PDFs remain authoritative; generated artefacts retain links to their origin and transformation history.

Users interact through the CLI. Application services coordinate domain operations through ports. Adapters integrate Docling, filesystem repositories, AtlasData, Markdown, and Doorstop. External tools may consume exports but do not define the internal model.
