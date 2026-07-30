## Unreleased

### Changed

- Split the CLI composition root into focused command modules.
- Separate generic evaluation from semantic qualification services.
- Split workflow planning, execution, and recovery responsibilities.
- Express document normalization as an ordered transformation pipeline.

- Extract named methods and techniques during normalization into a provenance-preserving document index and a separate `methods-and-techniques.json` artifact for future MCP/skill integration.
- Include readable clause references, titles and normalized clause text in consensus review
  documents so HITL decisions can be made without looking up clauses externally.
- Preserve the same clause context in consensus reports and golden-corpus proposals.
- Resolve review context from existing corpus datasets during qualification-matrix recomputation.

### Added

- `workflow run --overwrite --keep <stage>` for regenerating downstream derived artifacts while reusing selected existing stages such as Docling conversion output.
