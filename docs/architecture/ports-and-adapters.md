# Ports and adapters

![Ports and adapters](diagrams/svg/ports-and-adapters.svg)

The CLI invokes application services. Services depend on domain types and ports, while adapters implement storage and external-format behavior.

Current adapter responsibilities include:

- Docling PDF conversion and native artefact reading
- YAML catalog reading
- AtlasData parsing, lifecycle handling, onboarding, and TOC generation
- filesystem persistence of engineering documents and intermediate artefacts
- Markdown export
- Doorstop export

This boundary prevents target-specific identifiers, serialization details, and tool behavior from leaking into the core model. A new importer or exporter should implement a port and translate at the edge rather than extend the domain with format-specific fields.
