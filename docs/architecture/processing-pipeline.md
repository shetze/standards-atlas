# Processing pipeline

![Processing pipeline](diagrams/svg/processing-pipeline.svg)

The pipeline deliberately separates representations:

1. **Extraction** converts a physical source to Docling-native evidence.
2. **Normalization** creates a stable, lossless semantic input.
3. **Reference detection** records plausible clause anchors without committing to a match.
4. **Alignment** maps candidates to an expected AtlasData structure with confidence and diagnostics.
5. **Review** records human corrections as explicit overrides and produces reviewed alignments.
6. **Construction and enrichment** create canonical clauses and structured content blocks.
7. **Composition** assembles part documents into a family while preserving provenance.
8. **Export** projects the canonical document into a target ecosystem.

Each stage persists an artefact with sufficient metadata to inspect, reproduce, or invalidate its output. Stages do not bypass manual gates merely because a downstream format can be generated.
