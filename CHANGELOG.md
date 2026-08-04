## Unreleased

### Changed

- Define compatibility, migration, regeneration, deprecation, and release policies for maintained contracts.
- Extend security documentation with assets, actors, trust boundaries, threats, and mandatory controls.
- Define the staged target architecture for reviewed cross-domain relationship mapping.
- Establish documentation lifecycle, ownership, review-trigger, and removal rules.
- Consolidate the catalog format and getting-started documentation into one canonical reference each.
- Archive the semantic-model next-steps document as historical rationale after ADR 0050 and ADR 0051 implementation.
- Mark superseded ADR provisions explicitly and update the Knowledge Domain architecture description.
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


### Added
- Multi-dimensional `StructuralProfile` replaced legacy semantic roles.
- Internal cross-clause references are resolved during Markdown export and rendered as links when target clauses are available.
- Domain-aware structural taxonomy with normative/informative inheritance.
- Background MCP/LLM lifecycle management improvements and qualification-matrix reliability fixes.
